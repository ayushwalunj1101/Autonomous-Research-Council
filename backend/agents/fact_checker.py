import json
import re

from backend.llm.client import chat_completion
from backend.rag.chromadb_client import query_papers
from backend.sse.event_emitter import emit

# Relevance thresholds — tightened at higher retry counts
_THRESHOLDS = {
    0: (45.0, 60.0),   # normal: hard < 45, soft < 60
    1: (55.0, 70.0),   # retry 1: stricter
    2: (65.0, 80.0),   # retry 2: maximum
}


def _get_thresholds(retry_count: int) -> tuple[float, float]:
    return _THRESHOLDS.get(min(retry_count, 2), _THRESHOLDS[2])


# ------------------------------------------------------------------ #
# Innovator audit — claims vs ChromaDB
# ------------------------------------------------------------------ #

def _audit_innovator_claims(
    session_id: str,
    claims: list[str],
    round_num: int,
    retry_count: int,
) -> list[dict]:
    hard_threshold, soft_threshold = _get_thresholds(retry_count)
    flags: list[dict] = []

    for claim in claims:
        results = query_papers(session_id, claim, n_results=3)
        best_score = max((p["relevance_score"] for p in results), default=0.0)

        if best_score < hard_threshold:
            flags.append({
                "claim": claim,
                "agent": "Innovator",
                "round": round_num,
                "reason": f"No supporting paper found in ChromaDB (best relevance: {best_score:.1f})",
                "severity": "hard",
            })
        elif best_score < soft_threshold:
            flags.append({
                "claim": claim,
                "agent": "Innovator",
                "round": round_num,
                "reason": f"Weak paper support only (best relevance: {best_score:.1f})",
                "severity": "soft",
            })

    return flags


# ------------------------------------------------------------------ #
# Skeptic audit — fabrication check via LLM
# ------------------------------------------------------------------ #

_FABRICATION_SYSTEM_PROMPT = """You are the Fact-Checker agent on the Autonomous Research Council.
Audit the Skeptic's objections for fabricated or dishonest claims.

The Skeptic may only attack on logic — no citing papers, no invented statistics.
Flag any objection that:
  - Invents a specific statistic, percentage, or study not present in the debate context
  - Claims a paper was retracted or discredited without basis
  - Introduces a concrete external fact the Skeptic could not know without a database

Do NOT flag opinions, logical arguments, or reasonable inferences.

Output valid JSON only (no markdown fences):
{
  "fabricated_claims": [
    {"claim": "The exact objection text.", "reason": "Why this is fabricated."}
  ]
}
If nothing is fabricated, return: {"fabricated_claims": []}"""


def _audit_skeptic(state: dict, last_output: dict) -> list[dict]:
    innovator_output = next(
        (r for r in state.get("round_outputs", []) if r["agent"] == "Innovator" and r["round"] == 1),
        None,
    )
    innovator_context = innovator_output["content"] if innovator_output else ""

    claims_text = "\n".join(f"- {c}" for c in last_output.get("claims", []))
    user_prompt = (
        f"Innovator's argument (debate context the Skeptic had access to):\n"
        f"{innovator_context}\n\n"
        f"Skeptic's objections to audit:\n{claims_text}"
    )

    raw = chat_completion(
        messages=[
            {"role": "system", "content": _FABRICATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=800,
    )
    parsed = _parse_json(raw)

    return [
        {
            "claim": item.get("claim", ""),
            "agent": "Skeptic",
            "round": last_output["round"],
            "reason": item.get("reason", "Fabricated external fact"),
            "severity": "hard",
        }
        for item in parsed.get("fabricated_claims", [])
    ]


# ------------------------------------------------------------------ #
# R4 full audit — re-audits ALL Innovator claims across all rounds
# ------------------------------------------------------------------ #

def _audit_r4_full(state: dict) -> list[dict]:
    """
    Final full audit pass (Round 4). Re-audits every Innovator claim
    across all rounds. Only emits new flags for claims not already hard-flagged.
    """
    session_id: str = state["session_id"]
    retry_count: int = state.get("retry_count", 0)

    existing_hard: set[str] = {
        f["claim"]
        for f in state.get("citation_flags", [])
        if f["agent"] == "Innovator" and f["severity"] == "hard"
    }

    new_flags: list[dict] = []
    for output in state.get("round_outputs", []):
        if output["agent"] != "Innovator":
            continue
        rnd = output["round"]
        for claim in output.get("claims", []):
            if claim in existing_hard:
                continue
            results = query_papers(session_id, claim, n_results=3)
            best_score = max((p["relevance_score"] for p in results), default=0.0)
            hard_threshold, _ = _get_thresholds(retry_count)
            if best_score < hard_threshold:
                new_flags.append({
                    "claim": claim,
                    "agent": "Innovator",
                    "round": rnd,
                    "reason": f"Final audit: no supporting paper (best relevance: {best_score:.1f})",
                    "severity": "hard",
                })
                existing_hard.add(claim)

    return new_flags


# ------------------------------------------------------------------ #
# Main node
# ------------------------------------------------------------------ #

def run_fact_checker(state: dict) -> dict:
    """
    Audits the most recent RoundOutput. Behaviour depends on which
    agent produced it and the current round:

    After Innovator (rounds 1, 3):
      - Claims audited against ChromaDB by relevance threshold.
      - Thresholds tightened on retries.

    After Skeptic (rounds 2, 3):
      - LLM checks for fabricated external facts in objections.

    Round 4 final audit (called after innovator_defense):
      - Full re-audit of ALL Innovator claims across all rounds.

    Returns state patch:
        {"citation_flags": existing_flags + new_flags}
    """
    round_outputs: list[dict] = state.get("round_outputs", [])
    if not round_outputs:
        return {"citation_flags": state.get("citation_flags", [])}

    last_output = round_outputs[-1]
    agent = last_output["agent"]
    round_num = last_output["round"]
    retry_count: int = state.get("retry_count", 0)
    session_id: str = state["session_id"]

    print(f"[Fact-Checker] Auditing {agent} Round {round_num} "
          f"({len(last_output.get('claims', []))} claims, retry={retry_count})...")

    if agent == "Innovator" and round_num == 4:
        new_flags = _audit_r4_full(state)
    elif agent == "Innovator":
        new_flags = _audit_innovator_claims(
            session_id, last_output.get("claims", []), round_num, retry_count
        )
    elif agent == "Skeptic":
        new_flags = _audit_skeptic(state, last_output)
    else:
        new_flags = []

    hard = sum(1 for f in new_flags if f["severity"] == "hard")
    soft = sum(1 for f in new_flags if f["severity"] == "soft")
    print(f"[Fact-Checker] Round {round_num} audit: {hard} hard, {soft} soft flags.")

    # Emit citation_flag SSE event for every hard flag raised
    for f in new_flags:
        if f["severity"] == "hard":
            emit(session_id, "citation_flag", {"claim": f["claim"], "agent": f["agent"]})

    return {"citation_flags": state.get("citation_flags", []) + new_flags}


def _parse_json(raw: str) -> dict:
    try:
        return json.loads(raw, strict=False)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group(), strict=False)
        raise ValueError(f"Fact-Checker LLM returned unparseable output:\n{raw}")
