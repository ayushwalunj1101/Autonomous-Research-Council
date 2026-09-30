"""
Centralised LLM client. Every agent calls chat_json() (structured replies) or
chat_completion() (free text) instead of managing its own OpenAI client.

Providers (ARC_LLM_PROVIDER):
  openrouter  — default when OPENROUTER_API_KEY is set; model from ARC_MODEL / ARC_MODEL_<AGENT>
  groq        — free tier, model ARC_GROQ_MODEL (llama-3.3-70b-versatile)
  mock        — offline deterministic replies (tests, UI work)
  replay      — replays a recorded logs/<session>.jsonl call log

Reliability features:
  - JSON-schema structured outputs (OpenRouter, with provider.require_parameters) or JSON mode (Groq)
  - finish_reason == "length" is detected and retried with a larger max_tokens
  - unparseable replies get one repair round-trip before failing
  - transient errors (timeouts, 429, 5xx) are retried by the SDK, then sent to ARC_LLM_FALLBACK
  - cancellation + per-session budget are checked before every call; every call is logged
"""

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    OpenAI,
    RateLimitError,
)

from backend.config import env_secret, get_settings, model_for
from backend.llm import mock_provider
from backend.llm.json_utils import LLMJSONError, parse_llm_json
from backend.llm.usage import Timer, check_budget, record_call
from backend.runtime import check_cancelled

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

_MAX_TOKENS_CAP = 8000
_JSON_ATTEMPTS = 3

_clients: dict[str, OpenAI] = {}
_clients_lock = threading.Lock()
# Models that rejected json_schema structured outputs -> use JSON mode instead
_no_structured: set[str] = set()
# Error texts that mean "this model/provider cannot do structured output" (anything else,
# e.g. context length or a bad model id, must not disable structured output for good)
_STRUCTURED_ERROR_HINTS = ("response_format", "json_schema", "structured", "no endpoints found")


class LLMError(RuntimeError):
    """Provider-level failure with a short, user-safe message."""


class LLMOutputError(LLMError):
    """The model's reply could not be turned into the expected JSON."""


@dataclass
class LLMResult:
    text: str
    finish_reason: str | None
    provider: str
    model: str


# --------------------------------------------------------------------------- #
# Provider plumbing
# --------------------------------------------------------------------------- #

def _client(provider: str) -> OpenAI:
    settings = get_settings()
    with _clients_lock:
        if provider not in _clients:
            if provider == "openrouter":
                key = env_secret("OPENROUTER_API_KEY")
                if not key:
                    raise LLMError("OPENROUTER_API_KEY is not set. Add it to .env or set ARC_LLM_PROVIDER=groq.")
                _clients[provider] = OpenAI(
                    api_key=key, base_url=OPENROUTER_BASE_URL,
                    timeout=settings.llm_timeout_s, max_retries=2,
                )
            elif provider == "groq":
                key = env_secret("GROQ_API_KEY")
                if not key:
                    raise LLMError("GROQ_API_KEY is not set. Add it to .env or set ARC_LLM_PROVIDER=openrouter.")
                # Fewer SDK retries when another provider can take over
                retries = 1 if _fallback_provider("groq") else 2
                _clients[provider] = OpenAI(
                    api_key=key, base_url=GROQ_BASE_URL,
                    timeout=settings.llm_timeout_s, max_retries=retries,
                )
            else:
                raise LLMError(f"Unknown LLM provider '{provider}'.")
        return _clients[provider]


def _fallback_provider(primary: str) -> str | None:
    fallback = get_settings().llm_fallback
    if not fallback and primary == "groq" and env_secret("OPENROUTER_API_KEY"):
        fallback = "openrouter"  # historical behaviour: Groq rate limits spill to OpenRouter
    if fallback in ("", "none", primary):
        return None
    return fallback


def _model_for(provider: str, agent: str) -> str:
    if provider == "groq":
        return get_settings().groq_model
    if provider in ("mock", "replay"):
        return provider
    return model_for(agent)


def active_model(agent: str) -> str:
    """Human-readable model identifier the given agent currently uses (shown in reports)."""
    provider = get_settings().llm_provider
    if provider in ("mock", "replay"):
        return provider
    model = _model_for(provider, agent)
    return model if provider == "openrouter" else f"{provider}:{model}"


def _usage_numbers(resp) -> tuple[int, int, float | None]:
    usage = getattr(resp, "usage", None)
    if usage is None:
        return 0, 0, None
    cost = getattr(usage, "cost", None)
    try:
        cost = float(cost) if cost is not None else None
    except (TypeError, ValueError):
        cost = None
    return int(usage.prompt_tokens or 0), int(usage.completion_tokens or 0), cost


def _response_format(provider: str, model: str, schema: dict | None, schema_name: str) -> dict | None:
    if schema is None:
        return None
    if provider == "openrouter" and model not in _no_structured:
        return {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        }
    return {"type": "json_object"}


def _call_openai_compatible(
    provider: str, model: str, messages: list[dict], temperature: float,
    max_tokens: int, schema: dict | None, schema_name: str,
):
    client = _client(provider)
    kwargs: dict = dict(model=model, messages=messages, temperature=temperature, max_tokens=max_tokens)
    response_format = _response_format(provider, model, schema, schema_name)
    if response_format:
        kwargs["response_format"] = response_format
    if provider == "openrouter":
        extra_body: dict = {"usage": {"include": True}}
        if response_format and response_format["type"] == "json_schema":
            # Only route to providers that honour structured outputs
            extra_body["provider"] = {"require_parameters": True}
        kwargs["extra_body"] = extra_body
        kwargs["extra_headers"] = {"X-Title": "Autonomous Research Council"}

    try:
        return client.chat.completions.create(**kwargs)
    except (BadRequestError, NotFoundError) as exc:
        body = str(exc).lower()
        if provider == "groq" and "json_validate_failed" in body:
            # Groq JSON mode rejected the model's own output — surface it as a parse failure.
            # openai>=2 stores the inner "error" object as exc.body; older SDKs the full body.
            err = exc.body if isinstance(getattr(exc, "body", None), dict) else {}
            inner = err.get("error") if isinstance(err.get("error"), dict) else {}
            failed = err.get("failed_generation") or inner.get("failed_generation") or ""
            return _FakeResponse(str(failed), "stop")
        if (response_format and response_format["type"] == "json_schema"
                and any(hint in body for hint in _STRUCTURED_ERROR_HINTS)):
            print(f"[LLM] {model} rejected json_schema output ({exc.status_code}); retrying in JSON mode")
            _no_structured.add(model)
            return _call_openai_compatible(provider, model, messages, temperature, max_tokens, schema, schema_name)
        if response_format and "response_format" in body:
            print(f"[LLM] {model} rejected JSON mode; retrying without response_format")
            return _call_openai_compatible(provider, model, messages, temperature, max_tokens, None, schema_name)
        raise


class _FakeResponse:
    """Minimal stand-in for an OpenAI response (Groq json_validate_failed, mock, replay)."""

    def __init__(self, text: str, finish_reason: str, prompt_tokens: int = 0, completion_tokens: int = 0):
        message = type("Message", (), {"content": text})()
        choice = type("Choice", (), {"message": message, "finish_reason": finish_reason})()
        self.choices = [choice]
        self.usage = type("Usage", (), {
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "cost": None,
        })()


class _Replay:
    """Serves recorded replies from a JSONL call log, in order, per agent."""

    def __init__(self, path: str):
        self._queues: dict[str, list[str]] = {}
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry.get("error"):
                    continue
                self._queues.setdefault(entry["agent"], []).append(entry.get("raw", ""))
        self._lock = threading.Lock()

    def next(self, agent: str) -> str:
        with self._lock:
            queue = self._queues.get(agent) or []
            if not queue:
                raise LLMError(f"Replay log has no more recorded replies for {agent}.")
            return queue.pop(0)


_replay: _Replay | None = None
_mock_samples: dict[str, int] = {}


def _call_provider(
    provider: str, agent: str, messages: list[dict], temperature: float,
    max_tokens: int, schema: dict | None, schema_name: str,
):
    global _replay
    if provider == "mock":
        key = f"{agent}:{schema_name}"
        sample = _mock_samples.get(key, 0)
        _mock_samples[key] = sample + 1
        text, finish = mock_provider.respond(schema_name, messages, sample=sample)
        prompt_chars = sum(len(m.get("content", "")) for m in messages)
        return _FakeResponse(text, finish, prompt_chars // 4, len(text) // 4)
    if provider == "replay":
        if _replay is None:
            _replay = _Replay(get_settings().replay_file)
        return _FakeResponse(_replay.next(agent), "stop")
    model = _model_for(provider, agent)
    return _call_openai_compatible(provider, model, messages, temperature, max_tokens, schema, schema_name)


_TRANSIENT = (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)


def _short_provider_error(provider: str, exc: Exception) -> str:
    if isinstance(exc, APIStatusError):
        code = exc.status_code
        if code == 401:
            return f"{provider} rejected the API key (401). Check your .env."
        if code == 402:
            return f"{provider} reports insufficient credits (402). Top up or switch ARC_MODEL."
        if code == 429:
            return f"{provider} rate limit reached (429). Wait a minute or configure ARC_LLM_FALLBACK."
        return f"{provider} returned HTTP {code}."
    if isinstance(exc, APITimeoutError):
        return f"{provider} timed out."
    if isinstance(exc, APIConnectionError):
        return f"Could not reach {provider} (network error)."
    return f"{provider} failed: {type(exc).__name__}"


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def complete(
    messages: list[dict],
    *,
    agent: str,
    session_id: str | None = None,
    temperature: float = 0.5,
    max_tokens: int = 1500,
    schema: dict | None = None,
    schema_name: str = "response",
    attempt: int = 1,
) -> LLMResult:
    """One LLM call with cancellation, budget, fallback and logging. Returns the raw reply."""
    check_cancelled(session_id)
    check_budget(session_id)

    primary = get_settings().llm_provider
    providers = [primary]
    fallback = _fallback_provider(primary)
    if fallback:
        providers.append(fallback)

    last_error: Exception | None = None
    for provider in providers:
        model = _model_for(provider, agent)
        with Timer() as timer:
            try:
                resp = _call_provider(provider, agent, messages, temperature, max_tokens, schema, schema_name)
            except _TRANSIENT as exc:
                last_error = exc
                record_call(session_id=session_id, agent=agent, provider=provider, model=model,
                            messages=messages, raw="", finish_reason=None, prompt_tokens=0,
                            completion_tokens=0, reported_cost=0.0, latency_s=0.0,
                            attempt=attempt, error=_short_provider_error(provider, exc))
                if provider != providers[-1]:
                    print(f"[LLM] {_short_provider_error(provider, exc)} Falling back to {providers[-1]}.")
                continue
            except APIStatusError as exc:
                raise LLMError(_short_provider_error(provider, exc)) from exc

        if not getattr(resp, "choices", None):
            extra = getattr(resp, "model_extra", None) or {}
            raise LLMError(f"{provider} returned no choices: {extra.get('error') or 'empty response'}")

        choice = resp.choices[0]
        text = (choice.message.content or "").strip()
        finish_reason = getattr(choice, "finish_reason", None)
        prompt_tokens, completion_tokens, cost = _usage_numbers(resp)
        record_call(session_id=session_id, agent=agent, provider=provider, model=model,
                    messages=messages, raw=text, finish_reason=finish_reason,
                    prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                    reported_cost=cost, latency_s=timer.elapsed, attempt=attempt)
        return LLMResult(text=text, finish_reason=finish_reason, provider=provider, model=model)

    raise LLMError(_short_provider_error(providers[-1], last_error) if last_error else "LLM call failed.")


def chat_completion(
    messages: list[dict],
    *,
    agent: str = "LLM",
    session_id: str | None = None,
    temperature: float = 0.5,
    max_tokens: int = 1500,
) -> str:
    """Free-text completion (no JSON). Returns the stripped reply text."""
    return complete(messages, agent=agent, session_id=session_id,
                    temperature=temperature, max_tokens=max_tokens).text


def _follow_up(previous: str, request: str) -> list[dict]:
    """Repair turn; an empty assistant message is omitted (several providers reject it)."""
    turns = [{"role": "assistant", "content": previous[:6000]}] if previous.strip() else []
    return turns + [{"role": "user", "content": request}]


def chat_json(
    messages: list[dict],
    *,
    agent: str,
    schema: dict,
    schema_name: str,
    session_id: str | None = None,
    temperature: float = 0.4,
    max_tokens: int = 2000,
    required_keys: tuple[str, ...] = (),
    validate: Callable[[dict], str | None] | None = None,
) -> dict:
    """
    Structured completion. Retries with a larger token budget when the reply was cut off,
    and asks the model to resend valid JSON when it was malformed. Raises LLMOutputError
    with a short message after _JSON_ATTEMPTS attempts.

    validate(parsed) may return a problem description (e.g. "the claims list was empty");
    the model is then asked to fix it like a malformed reply. If every attempt parses but
    fails validation, the last parsed reply is returned rather than failing the session.
    """
    tokens = max_tokens
    convo = list(messages)
    last_error = "no reply"
    best_parsed: dict | None = None
    for attempt in range(1, _JSON_ATTEMPTS + 1):
        result = complete(convo, agent=agent, session_id=session_id, temperature=temperature,
                          max_tokens=tokens, schema=schema, schema_name=schema_name, attempt=attempt)
        try:
            parsed = parse_llm_json(result.text, required_keys=required_keys)
            problem = validate(parsed) if validate else None
            if not problem:
                return parsed
            best_parsed = parsed
            last_error = problem
            print(f"[LLM] {agent} reply incomplete (attempt {attempt}/{_JSON_ATTEMPTS}): {problem}")
            convo = list(messages) + _follow_up(result.text, (
                f"Your reply is incomplete: {problem}. Reply again with the complete JSON object "
                "that matches the requested schema: no prose, no code fences."
            ))
        except LLMJSONError as exc:
            last_error = str(exc)
            truncated = exc.truncated or result.finish_reason == "length"
            print(f"[LLM] {agent} reply unusable (attempt {attempt}/{_JSON_ATTEMPTS}): {exc}")
            if truncated and tokens < _MAX_TOKENS_CAP:
                tokens = min(tokens * 2, _MAX_TOKENS_CAP)
                convo = list(messages)  # start over with more room rather than continuing a fragment
            else:
                convo = list(messages) + _follow_up(result.text, (
                    f"Your previous reply could not be parsed ({exc}). Reply again with only the "
                    "complete JSON object that matches the requested schema: no prose, no code fences."
                ))
    if best_parsed is not None:
        print(f"[LLM] {agent}: using the last reply despite: {last_error}")
        return best_parsed
    raise LLMOutputError(f"The {agent} reply could not be read as JSON after {_JSON_ATTEMPTS} attempts ({last_error}).")


def reset_clients() -> None:
    """Drops cached clients/replay state (tests switch providers via env vars)."""
    global _replay
    with _clients_lock:
        _clients.clear()
    _no_structured.clear()
    _mock_samples.clear()
    _replay = None
