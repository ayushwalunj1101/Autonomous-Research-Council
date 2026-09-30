"""
Tolerant JSON extraction for LLM replies.

Handles the failure modes seen in experiments/*.log:
  - prose before/after the JSON object, or the answer written twice ("Extra data")
  - ```json fenced blocks
  - trailing commas before } or ]
  - truncated output (reported as LLMJSONError(truncated=True) so the caller can
    retry with a larger max_tokens instead of silently accepting half an answer)
"""

import json
import re

_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")
_MAX_CANDIDATES = 40


class LLMJSONError(ValueError):
    def __init__(self, message: str, truncated: bool = False):
        super().__init__(message)
        self.truncated = truncated


def _decode_object_at(text: str, start: int) -> dict | None:
    decoder = json.JSONDecoder(strict=False)
    try:
        obj, _end = decoder.raw_decode(text, start)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _candidates(text: str) -> list[dict]:
    """Every JSON object that decodes cleanly starting at some '{' in text."""
    found: list[dict] = []
    starts = [m.start() for m in re.finditer(r"\{", text)][:_MAX_CANDIDATES]
    for start in starts:
        obj = _decode_object_at(text, start)
        if obj is not None:
            found.append(obj)
    return found


def _looks_truncated(text: str) -> bool:
    """True when the text opens more braces/brackets than it closes (outside strings)."""
    depth = 0
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
    return in_string or depth > 0


def parse_llm_json(raw: str | None, required_keys: tuple[str, ...] = ()) -> dict:
    """
    Extracts the JSON object from an LLM reply.

    When several objects decode (e.g. a nested citation object and the full answer),
    the first one containing all required_keys wins; otherwise the largest one.
    Raises LLMJSONError with a short, user-safe message.
    """
    if raw is None or not raw.strip():
        raise LLMJSONError("empty response")

    text = raw.strip()
    fenced = _FENCE_RE.search(text)
    sources = [fenced.group(1).strip(), text] if fenced else [text]

    for source in sources:
        for attempt in (source, _TRAILING_COMMA_RE.sub(r"\1", source)):
            try:
                obj = json.loads(attempt, strict=False)
                if isinstance(obj, dict) and all(k in obj for k in required_keys):
                    return obj
            except json.JSONDecodeError:
                pass

            candidates = _candidates(attempt)
            if required_keys:
                for obj in candidates:
                    if all(k in obj for k in required_keys):
                        return obj
            elif candidates:
                return max(candidates, key=lambda o: len(json.dumps(o)))

    if _looks_truncated(text):
        raise LLMJSONError("response was cut off before the JSON was complete", truncated=True)
    if required_keys:
        raise LLMJSONError(f"no JSON object with keys {list(required_keys)} found")
    raise LLMJSONError("no valid JSON object found")
