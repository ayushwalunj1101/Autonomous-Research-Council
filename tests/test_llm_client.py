import httpx
import pytest
from openai import APIConnectionError

from backend.llm import client
from backend.llm.client import LLMOutputError, chat_json
from backend.llm.schemas import DEBATE_TURN
from backend.llm.usage import record_call, session_cost
from backend.runtime import BudgetExceeded, SessionCancelled, clear_session, request_cancel

MESSAGES = [{"role": "system", "content": "You are the Innovator agent."},
            {"role": "user", "content": "[1] A paper\nAbstract: x\n\nPropose."}]


def _call(**kw):
    return chat_json(MESSAGES, agent="Innovator", schema=DEBATE_TURN, schema_name="debate_turn",
                     required_keys=("content", "claims"), **kw)


class _Scripted:
    """Replaces the provider call with scripted (text, finish_reason) replies."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.max_tokens_seen = []
        self.message_counts = []

    def __call__(self, provider, agent, messages, temperature, max_tokens, schema, schema_name):
        self.max_tokens_seen.append(max_tokens)
        self.message_counts.append(len(messages))
        text, finish = self.replies.pop(0)
        return client._FakeResponse(text, finish, 100, 50)


def test_mock_provider_returns_valid_turn():
    parsed = _call(session_id="t-mock")
    assert parsed["content"] and len(parsed["claims"]) == 3


def test_truncated_reply_is_retried_with_more_tokens(monkeypatch):
    scripted = _Scripted([('{"content": "cut', "length"), ('{"content": "ok", "claims": []}', "stop")])
    monkeypatch.setattr(client, "_call_provider", scripted)
    assert _call(max_tokens=1000)["content"] == "ok"
    assert scripted.max_tokens_seen == [1000, 2000]
    # A truncated reply restarts the conversation instead of continuing a fragment
    assert scripted.message_counts == [2, 2]


def test_malformed_reply_gets_a_repair_round_trip(monkeypatch):
    scripted = _Scripted([("Sure! Here is my answer: {not json}", "stop"),
                          ('{"content": "fixed", "claims": []}', "stop")])
    monkeypatch.setattr(client, "_call_provider", scripted)
    assert _call()["content"] == "fixed"
    assert scripted.message_counts == [2, 4]  # original + assistant reply + repair request


def test_gives_up_after_three_attempts_with_short_message(monkeypatch):
    scripted = _Scripted([("garbage " * 400, "stop")] * 3)
    monkeypatch.setattr(client, "_call_provider", scripted)
    with pytest.raises(LLMOutputError) as err:
        _call()
    message = str(err.value)
    assert "Innovator" in message and len(message) < 200  # no raw model output in user-facing errors


def test_empty_claims_are_sent_back_for_completion(monkeypatch):
    from backend.agents.common import require_turn

    scripted = _Scripted([('{"content": "A long defense [1].", "claims": []}', "stop"),
                          ('{"content": "A long defense [1].", "claims": [{"text": "X holds.", "paper_ids": [1]}]}', "stop")])
    monkeypatch.setattr(client, "_call_provider", scripted)
    parsed = _call(validate=require_turn("factual claim", "4-8"))
    assert parsed["claims"][0]["text"] == "X holds."
    assert scripted.message_counts == [2, 4]


def test_validation_never_satisfied_keeps_last_parsed_reply(monkeypatch):
    from backend.agents.common import require_turn

    scripted = _Scripted([('{"content": "c", "claims": []}', "stop")] * 3)
    monkeypatch.setattr(client, "_call_provider", scripted)
    parsed = _call(validate=require_turn("factual claim", "4-8"))
    assert parsed == {"content": "c", "claims": []}  # degraded, but the session is not killed


def test_mock_fault_injection_recovers(monkeypatch):
    monkeypatch.setenv("ARC_MOCK_FAULTS", "truncate:debate_turn,prose:debate_turn")
    first = _call(session_id="t-fault")
    second = _call(session_id="t-fault")
    assert first["claims"] and second["claims"]


def test_budget_guard_blocks_calls(monkeypatch):
    monkeypatch.setenv("ARC_SESSION_BUDGET_USD", "0.01")
    from backend.config import reset_settings
    reset_settings()
    record_call(session_id="t-budget", agent="x", provider="openrouter", model="anthropic/claude-sonnet-5.5",
                messages=[], raw="", finish_reason="stop", prompt_tokens=0, completion_tokens=0,
                reported_cost=0.02, latency_s=0.1, attempt=1)
    assert session_cost("t-budget") >= 0.02
    with pytest.raises(BudgetExceeded):
        _call(session_id="t-budget")


def test_cancellation_stops_before_the_call():
    request_cancel("t-cancel")
    try:
        with pytest.raises(SessionCancelled):
            _call(session_id="t-cancel")
    finally:
        clear_session("t-cancel")


def test_transient_error_falls_back_to_second_provider(monkeypatch):
    monkeypatch.setenv("ARC_LLM_PROVIDER", "groq")
    monkeypatch.setenv("ARC_LLM_FALLBACK", "mock")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key")
    from backend.config import reset_settings
    reset_settings()

    def boom(*args, **kwargs):
        raise APIConnectionError(request=httpx.Request("POST", "https://api.groq.com"))

    monkeypatch.setattr(client, "_call_openai_compatible", boom)
    parsed = _call(session_id="t-fallback")
    assert parsed["claims"]


def test_openrouter_request_uses_structured_outputs(monkeypatch):
    monkeypatch.setenv("ARC_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("ARC_MODEL", "anthropic/claude-sonnet-5.5")
    from backend.config import reset_settings
    reset_settings()
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return client._FakeResponse('{"content": "c", "claims": []}', "stop", 10, 5)

    class FakeClient:
        chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr(client, "_client", lambda provider: FakeClient())
    _call(session_id="t-structured")
    assert captured["model"] == "anthropic/claude-sonnet-5.5"
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["response_format"]["json_schema"]["strict"] is True
    assert captured["extra_body"]["provider"] == {"require_parameters": True}
    assert captured["extra_body"]["usage"] == {"include": True}


def _bad_request(message: str, body: dict):
    from openai import BadRequestError

    response = httpx.Response(400, request=httpx.Request("POST", "https://api.example.com/v1/chat/completions"))
    return BadRequestError(message, response=response, body=body)


@pytest.mark.parametrize("body", [
    {"code": "json_validate_failed", "failed_generation": '{"content": "salvaged", "claims": []}'},  # openai>=2
    {"error": {"code": "json_validate_failed", "failed_generation": '{"content": "salvaged", "claims": []}'}},
])
def test_groq_failed_generation_is_recovered(monkeypatch, body):
    monkeypatch.setenv("ARC_LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key")
    from backend.config import reset_settings
    reset_settings()

    class FakeCompletions:
        def create(self, **kwargs):
            raise _bad_request("Error code: 400 - json_validate_failed", body)

    class FakeClient:
        chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr(client, "_client", lambda provider: FakeClient())
    assert _call()["content"] == "salvaged"


def _openrouter_env(monkeypatch):
    monkeypatch.setenv("ARC_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("ARC_MODEL", "some/model")
    from backend.config import reset_settings
    reset_settings()


def test_unrelated_400_does_not_disable_structured_output(monkeypatch):
    _openrouter_env(monkeypatch)

    class FakeCompletions:
        def create(self, **kwargs):
            raise _bad_request("This model's maximum context length is 8192 tokens", {"message": "context length"})

    class FakeClient:
        chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr(client, "_client", lambda provider: FakeClient())
    with pytest.raises(client.LLMError):
        _call()
    assert "some/model" not in client._no_structured


def test_schema_rejection_falls_back_to_json_mode(monkeypatch):
    _openrouter_env(monkeypatch)
    formats = []

    class FakeCompletions:
        def create(self, **kwargs):
            formats.append(kwargs.get("response_format", {}).get("type"))
            if formats[-1] == "json_schema":
                raise _bad_request("No endpoints found that can handle the requested parameters", {})
            return client._FakeResponse('{"content": "ok", "claims": []}', "stop", 5, 5)

    class FakeClient:
        chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr(client, "_client", lambda provider: FakeClient())
    assert _call()["content"] == "ok"
    assert formats == ["json_schema", "json_object"] and "some/model" in client._no_structured


def test_empty_reply_repair_turn_has_no_empty_assistant_message(monkeypatch):
    seen = []

    def provider(provider_name, agent, messages, temperature, max_tokens, schema, schema_name):
        seen.append(messages)
        text = "" if len(seen) == 1 else '{"content": "ok", "claims": []}'
        return client._FakeResponse(text, "stop", 1, 1)

    monkeypatch.setattr(client, "_call_provider", provider)
    assert _call()["content"] == "ok"
    assert all(m.get("content") for m in seen[1] if m["role"] == "assistant")
