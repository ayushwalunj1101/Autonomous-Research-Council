"""
JSON schemas for every structured LLM reply, plus normalizers that coerce replies into
the exact types the rest of the pipeline expects.

Schemas avoid numeric/length constraints (minimum, maxItems, ...) because not every
provider's structured-output mode supports them; ranges are enforced by the normalizers.
"""

import re
from typing import Any


def _obj(properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required if required is not None else list(properties),
        "additionalProperties": False,
    }


_STR = {"type": "string"}
_INT = {"type": "integer"}
_STR_LIST = {"type": "array", "items": _STR}
_INT_LIST = {"type": "array", "items": _INT}

_CLAIM = _obj({"text": _STR, "paper_ids": _INT_LIST})

ORCHESTRATOR = _obj({"keywords": _STR_LIST, "hypothesis": _STR, "domain": _STR})

DEBATE_TURN = _obj({"content": _STR, "claims": {"type": "array", "items": _CLAIM}})

INNOVATOR_REPAIR = _obj({
    "content": _STR,
    "resolutions": {
        "type": "array",
        "items": _obj({
            "flag_id": _INT,
            "action": {"type": "string", "enum": ["retract", "revise"]},
            "revised_claim": _STR,
            "paper_ids": _INT_LIST,
        }),
    },
})

FABRICATION_CHECK = _obj({
    "fabricated_claims": {"type": "array", "items": _obj({"claim": _STR, "reason": _STR})},
})

VERDICTS = ["supported", "partial", "unsupported", "contradicted"]

CLAIM_VERIFICATION = _obj({
    "verdicts": {
        "type": "array",
        "items": _obj({
            "claim_id": _INT,
            "verdict": {"type": "string", "enum": VERDICTS},
            "paper_id": _INT,
            "quote": _STR,
            "reason": _STR,
        }),
    },
})

CHAOS_SELECTION = _obj({"constraint_index": _INT, "reason": _STR})

_SCORE_FIELDS = ["novelty_score", "feasibility_score", "research_gap_score", "overall_confidence"]

CHAIRMAN_SCORES = _obj({
    **{f: _INT for f in _SCORE_FIELDS},
    "score_rationale": _obj({"novelty": _STR, "feasibility": _STR, "research_gap": _STR, "overall": _STR}),
})

CHAIRMAN = _obj({
    **CHAIRMAN_SCORES["properties"],
    "refined_hypothesis": _STR,
    "strengths": _STR_LIST,
    "weaknesses": _STR_LIST,
    "chaos_response_summary": _STR,
    "proposed_methodology": _STR_LIST,
    "top_papers": {"type": "array", "items": _obj({"paper_id": _INT, "summary": _STR})},
})


# --------------------------------------------------------------------------- #
# Normalizers
# --------------------------------------------------------------------------- #

_TEXT_KEYS = ("text", "claim", "content", "description", "step", "summary", "title", "value")


def as_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        for key in _TEXT_KEYS:
            if isinstance(value.get(key), str) and value[key].strip():
                return value[key].strip()
        return " ".join(as_str(v) for v in value.values() if isinstance(v, (str, int, float))).strip()
    if isinstance(value, (list, tuple)):
        return "\n\n".join(s for s in (as_str(v) for v in value) if s)
    return str(value).strip()


def as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        lines = [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", ln).strip() for ln in value.splitlines()]
        return [ln for ln in lines if ln]
    if isinstance(value, (list, tuple)):
        return [s for s in (as_str(v) for v in value) if s]
    text = as_str(value)
    return [text] if text else []


def as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value)
        if match:
            return int(round(float(match.group())))
    return None


def as_int_list(value: Any) -> list[int]:
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple)) else [value]
    out: list[int] = []
    for item in items:
        n = as_int(item)
        if n is not None and n not in out:
            out.append(n)
    return out


def as_score(value: Any) -> int | None:
    """0-100 integer score. Accepts 80, 80.0, "80", "80/100", "80%", and 0-1 fractions."""
    if isinstance(value, str) and "/" in value:
        num, _, den = value.partition("/")
        n, d = as_int(num), as_int(den)
        if n is not None and d:
            return max(0, min(100, round(100 * n / d)))
    if isinstance(value, float) and 0.0 < value <= 1.0:
        return round(value * 100)
    n = as_int(value)
    if n is None:
        return None
    return max(0, min(100, n))


def normalize_claims(value: Any) -> list[dict]:
    """[{text, paper_ids}] from lists of strings, dicts with odd keys, or a single string."""
    claims: list[dict] = []
    items = value if isinstance(value, (list, tuple)) else as_str_list(value)
    for item in items:
        if isinstance(item, dict):
            text = as_str(item.get("text") or item.get("claim") or item)
            ids = as_int_list(item.get("paper_ids") or item.get("papers") or item.get("paper_id"))
        else:
            text = as_str(item)
            ids = as_int_list(re.findall(r"\[(?:Paper\s*)?(\d+)\]", text))
        if text:
            claims.append({"text": text, "paper_ids": ids})
    return claims


def normalize_debate_turn(parsed: dict) -> dict:
    return {
        "content": as_str(parsed.get("content")),
        "claims": normalize_claims(parsed.get("claims")),
    }
