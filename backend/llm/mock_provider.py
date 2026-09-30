"""
Offline stand-in for a real LLM (ARC_LLM_PROVIDER=mock).

Produces deterministic, schema-valid replies derived from the prompt so the whole
pipeline (graph, repair loop, SSE, PDF, exports, UI) can run without API calls.
Every Innovator turn includes one claim marked "(unverified)", which the mock
Fact-Checker rejects — so the first attempt lands below RAGAS 0.7 and the targeted
repair path is exercised on every mock run.

ARC_MOCK_FAULTS injects one bad reply per schema, e.g. "truncate:debate_turn,prose:chairman".
"""

import itertools
import json
import os
import re
import threading

_counter = itertools.count()
_faults_used: set[str] = set()
_fault_lock = threading.Lock()

_BIOMED = re.compile(r"patient|clinical|disease|medical|drug|therapy|cancer|health|gene", re.I)
_STOP = {"the", "a", "an", "of", "in", "on", "for", "and", "to", "with", "can", "is", "are",
         "that", "than", "by", "at", "as", "from", "into", "using", "use", "reduce", "improve"}


def _user_text(messages: list[dict]) -> str:
    return "\n".join(m.get("content", "") for m in messages if m.get("role") == "user")


def _paper_numbers(text: str) -> list[int]:
    return sorted({int(n) for n in re.findall(r"^\s*\[(\d+)\]", text, re.M)})


def _numbered(text: str, prefix: str) -> list[tuple[int, str]]:
    return [(int(n), body.strip()) for n, body in re.findall(rf"^{prefix}(\d+):\s*(.+)$", text, re.M)]


def _orchestrator(text: str) -> dict:
    body = text.split("User input:", 1)[-1].strip()
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]{3,}", body) if w.lower() not in _STOP]
    keywords, seen = [], set()
    for w in words:
        if w.lower() not in seen:
            seen.add(w.lower())
            keywords.append(w.lower())
    first = re.split(r"(?<=[.!?])\s", body)[0][:300]
    return {
        "keywords": keywords[:4] or ["machine learning"],
        "hypothesis": first if len(first) > 20 else f"{first} improves outcomes over current baselines.",
        "domain": "biomedical" if _BIOMED.search(body) else "computer science",
    }


def _debate_turn(text: str, system: str) -> dict:
    papers = _paper_numbers(text) or [1]
    p1, p2 = papers[0], papers[1] if len(papers) > 1 else papers[0]
    who = "Skeptic" if "Skeptic agent" in system else "Innovator"
    if who == "Skeptic":
        return {
            "content": "The argument generalises from a narrow set of benchmarks and does not "
                       "separate the method's effect from confounders such as dataset size.",
            "claims": [
                {"text": "The evaluation does not control for dataset size.", "paper_ids": []},
                {"text": "The proposal assumes transfer across domains without justification.", "paper_ids": []},
            ],
        }
    tag = next(_counter)
    return {
        "content": f"Building on [{p1}] and [{p2}], the proposal refines the hypothesis and "
                   "outlines an evaluation plan grounded in the retrieved literature.",
        "claims": [
            {"text": f"Prior work reports gains on standard benchmarks (turn {tag}).", "paper_ids": [p1]},
            {"text": f"The approach has been evaluated under distribution shift (turn {tag}).", "paper_ids": [p2]},
            {"text": f"The method removes the need for any labelled data (unverified, turn {tag}).", "paper_ids": []},
        ],
    }


def _repair(text: str) -> dict:
    papers = _paper_numbers(text) or [1]
    resolutions = []
    for flag_id, claim in _numbered(text, "F"):
        claim = claim.split("  [flagged")[0]
        if flag_id % 2:
            resolutions.append({"flag_id": flag_id, "action": "revise",
                                "revised_claim": claim.replace("unverified", "narrowed") + " in the cited setting.",
                                "paper_ids": [papers[0]]})
        else:
            resolutions.append({"flag_id": flag_id, "action": "retract", "revised_claim": "", "paper_ids": []})
    return {"content": "Unsupported claims were revised to match the cited evidence or retracted.",
            "resolutions": resolutions}


def _verification(text: str) -> dict:
    verdicts = []
    for claim_id, claim in _numbered(text, "C"):
        cited = re.search(r"candidate papers:\s*\[?(\d+)", claim)
        paper_id = int(cited.group(1)) if cited else 1
        if "unverified" in claim:
            verdicts.append({"claim_id": claim_id, "verdict": "unsupported", "paper_id": 0,
                             "quote": "", "reason": "No retrieved abstract makes this claim."})
        else:
            verdicts.append({"claim_id": claim_id, "verdict": "supported", "paper_id": paper_id,
                             "quote": "results improve on standard benchmarks",
                             "reason": "The abstract reports this directly."})
    return {"verdicts": verdicts}


def _scores(sample: int) -> dict:
    jitter = [0, 5, -5][sample % 3]
    return {
        "novelty_score": 62 + jitter,
        "feasibility_score": 71 - jitter,
        "research_gap_score": 58 + jitter,
        "overall_confidence": 66,
        "score_rationale": {
            "novelty": "Closest retrieved paper covers a related but narrower setting.",
            "feasibility": "Standard datasets and compute suffice after the chaos adaptation.",
            "research_gap": "Two papers call for this evaluation explicitly.",
            "overall": "Most claims are supported; one was retracted during repair.",
        },
    }


def _chairman(text: str, sample: int) -> dict:
    papers = _paper_numbers(text) or [1]
    return {
        **_scores(sample),
        "refined_hypothesis": "A narrowed version of the hypothesis holds under the cited evaluation settings.",
        "strengths": ["Grounded in recent literature", "Clear evaluation plan", "Adapts to the injected constraint"],
        "weaknesses": ["Limited to benchmark settings", "Transfer across domains untested", "Small effect sizes"],
        "chaos_response_summary": "The Innovator reduced scope and reused open benchmarks to satisfy the constraint.",
        "proposed_methodology": [
            "Step 1: Data collection — assemble open benchmark datasets",
            "Step 2: Baselines — reproduce the strongest published baselines",
            "Step 3: Method — implement the proposed approach",
            "Step 4: Evaluation — test under distribution shift",
        ],
        "top_papers": [{"paper_id": n, "summary": "Directly relevant evidence for the hypothesis."} for n in papers[:5]],
    }


def _apply_fault(schema_name: str, payload: str) -> str:
    faults = [f.strip() for f in os.environ.get("ARC_MOCK_FAULTS", "").split(",") if f.strip()]
    for fault in faults:
        kind, _, target = fault.partition(":")
        if target != schema_name:
            continue
        with _fault_lock:
            if fault in _faults_used:
                continue
            _faults_used.add(fault)
        if kind == "truncate":
            return payload[: len(payload) // 2]
        if kind == "prose":
            return "Here is my answer.\n\n" + payload + "\n\nHope this helps! {not json}"
    return payload


def respond(schema_name: str, messages: list[dict], sample: int = 0) -> tuple[str, str]:
    """Returns (reply_text, finish_reason)."""
    text = _user_text(messages)
    system = messages[0].get("content", "") if messages else ""
    if schema_name == "orchestrator":
        data = _orchestrator(text)
    elif schema_name == "debate_turn":
        data = _debate_turn(text, system)
    elif schema_name == "innovator_repair":
        data = _repair(text)
    elif schema_name == "fabrication_check":
        data = {"fabricated_claims": []}
    elif schema_name == "claim_verification":
        data = _verification(text)
    elif schema_name == "chaos_selection":
        data = {"constraint_index": 1, "reason": "Most relevant to the proposed methodology."}
    elif schema_name == "chairman":
        data = _chairman(text, sample)
    elif schema_name == "chairman_scores":
        data = _scores(sample)
    else:
        data = {"content": "ok"}
    payload = _apply_fault(schema_name, json.dumps(data))
    finish = "length" if payload and not payload.rstrip().endswith("}") and payload.startswith("{") else "stop"
    return payload, finish


def reset_faults() -> None:
    with _fault_lock:
        _faults_used.clear()
