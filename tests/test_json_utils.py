"""Parser tests built from the failure modes recorded in experiments/*.log."""

import pytest

from backend.llm.json_utils import LLMJSONError, parse_llm_json

KEYS = ("content", "claims")


def test_plain_json():
    assert parse_llm_json('{"content": "x", "claims": []}', KEYS) == {"content": "x", "claims": []}


def test_fenced_json():
    raw = 'Here you go:\n```json\n{"content": "x", "claims": ["a"]}\n```\nThanks'
    assert parse_llm_json(raw, KEYS)["claims"] == ["a"]


def test_prose_then_json_like_the_skeptic_logs():
    raw = "The Innovator's argument is weak.\n\nMore prose here.\n\n" + '{"content": "c", "claims": ["x"]}'
    assert parse_llm_json(raw, KEYS)["content"] == "c"


def test_extra_data_two_objects_back_to_back():
    # json.loads raised "Extra data: line 9 column 1" in retry3.log; the greedy regex then
    # grabbed both objects and failed again.
    raw = '{"fabricated_claims": []}\n\n{"note": "second object"}'
    assert parse_llm_json(raw, ("fabricated_claims",)) == {"fabricated_claims": []}


def test_trailing_commas():
    raw = '{"content": "x", "claims": ["a", "b",],}'
    assert parse_llm_json(raw, KEYS)["claims"] == ["a", "b"]


def test_prefers_object_with_required_keys_over_nested_one():
    raw = 'See {"title": "t", "url": "u"} and then {"content": "full", "claims": []}'
    assert parse_llm_json(raw, KEYS)["content"] == "full"


def test_control_characters_inside_strings():
    raw = '{"content": "line one\nline two\ttab", "claims": []}'
    assert "line two" in parse_llm_json(raw, KEYS)["content"]


def test_truncated_mid_url_is_reported_as_truncated():
    # 12 of the 16 cut-off replies ended exactly like this in the experiment logs
    raw = (
        '{\n  "content": "Retrieval helps biomedical QA.",\n  "claims": [\n    "claim one"\n  ],\n'
        '  "citations": [\n    {\n      "title": "Efficient and Reproducible Biomedical QA",\n'
        '      "url": "http://arxiv.org/abs/2'
    )
    with pytest.raises(LLMJSONError) as err:
        parse_llm_json(raw, KEYS)
    assert err.value.truncated


def test_truncated_after_prose_duplicate():
    raw = "Long critique paragraph.\n\n" + '{\n  "content": "Long critique paragraph.",\n  "claims": [\n    "The argument relies on'
    with pytest.raises(LLMJSONError) as err:
        parse_llm_json(raw, KEYS)
    assert err.value.truncated


def test_empty_and_none():
    for raw in ("", "   ", None):
        with pytest.raises(LLMJSONError):
            parse_llm_json(raw)


def test_missing_required_keys_is_an_error():
    with pytest.raises(LLMJSONError):
        parse_llm_json('{"something": "else"}', KEYS)


def test_degenerate_repetition_output():
    with pytest.raises(LLMJSONError):
        parse_llm_json("!" * 500, KEYS)
