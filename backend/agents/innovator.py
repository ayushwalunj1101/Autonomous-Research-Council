from backend.agents.common import (
    cost_so_far,
    map_claims,
    paper_context,
    require_turn,
    resolve_markers,
    retrieve,
    summarize,
    truncate,
    unresolved_hard_flags,
)
from backend.llm.client import chat_json
from backend.llm.schemas import DEBATE_TURN, INNOVATOR_REPAIR, as_int, as_int_list, as_str, normalize_debate_turn
from backend.sse.event_emitter import emit

TOP_K_PAPERS = 5
MAX_PAPERS_IN_PROMPT = 6


def _determine_round(state: dict) -> int:
    """Determines which round Innovator is in based on existing (non-repair) outputs."""
    n = sum(
        1 for r in state.get("round_outputs", [])
        if r["agent"] == "Innovator" and r.get("stage", "debate") == "debate"
    )
    return {0: 1, 1: 3}.get(n, 4)


def _strictness_note(retry_count: int) -> str:
    if retry_count == 1:
        return (
            "\nSTRICTNESS NOTE (Retry 1): Reduce speculative claims. "
            "Every claim you make must be directly traceable to a provided paper."
        )
    if retry_count >= 2:
        return (
            "\nSTRICTNESS NOTE (Retry 2 - Maximum): Make ONLY claims with direct paper support. "
            "If you cannot cite a paper for it, do not say it."
        )
    return ""


# ------------------------------------------------------------------ #
# Round-specific system prompts
# ------------------------------------------------------------------ #

_OUTPUT_RULES = """
Papers are numbered [1], [2], ... Cite them ONLY by number, e.g. "as shown in [2]".
Never write paper titles or URLs yourself.

Respond with a JSON object only:
{
  "content": "Your argument as flowing prose, citing papers as [n].",
  "claims": [{"text": "One discrete, verifiable factual claim.", "paper_ids": [2]}]
}
Each claim is a single sentence stating one checkable fact, with the numbers of the
papers that support it (empty list if none do). 4-8 claims."""

_SYSTEM_R1 = """You are the Innovator agent on the Autonomous Research Council.
Round 1 - Opening Argument.
Your role: propose a refined, evidence-backed research direction for the given hypothesis.

Rules:
- Ground every major claim in one of the provided papers.
- Be bold but defensible - no overreach without evidence.
- Keep the argument to 3-5 paragraphs.""" + _OUTPUT_RULES

_SYSTEM_R3 = """You are the Innovator agent on the Autonomous Research Council.
Round 3 - Chaos Response.
A real-world constraint has been injected into the debate. You must now adapt your
research proposal to incorporate this constraint constructively.

Rules:
- Acknowledge the constraint directly.
- Show how the methodology can be adapted to work within it.
- Maintain any valid claims from Round 1; update methodology as needed.
- Ground new claims in the provided papers.
- Keep the argument to 3-4 paragraphs.""" + _OUTPUT_RULES

_SYSTEM_R4 = """You are the Innovator agent on the Autonomous Research Council.
Round 4 - Defense.
You must now defend your position against all Skeptic objections, address outstanding
Citation Flags, and incorporate the chaos constraint into a final consolidated methodology.

Rules:
- Address every Skeptic objection from Rounds 2 and 3 explicitly.
- Acknowledge every outstanding Citation Flag - either find support in the papers or retract the claim.
- Show how your final methodology handles the chaos constraint.
- Stay consistent with your own earlier rounds unless you explicitly revise a position.
- Keep the defense to 4-5 paragraphs.""" + _OUTPUT_RULES

_ROUND_PROMPTS = {1: _SYSTEM_R1, 3: _SYSTEM_R3, 4: _SYSTEM_R4}

_SYSTEM_REPAIR = """You are the Innovator agent on the Autonomous Research Council.
Repair round - the Fact-Checker could not verify some of your claims against the
retrieved papers, so the council's faithfulness score is below threshold.

For EACH flagged claim (F1, F2, ...) choose exactly one action:
- "revise": restate the claim so the numbered papers directly support it, and list those paper numbers.
  Only revise if a paper genuinely supports the narrower statement.
- "retract": withdraw the claim because no provided paper supports it.

Papers are numbered [1], [2], ... Cite them only by number; never write titles or URLs.

Respond with a JSON object only:
{
  "content": "2-4 sentences explaining what you revised or retracted and why.",
  "resolutions": [{"flag_id": 1, "action": "revise", "revised_claim": "...", "paper_ids": [2]},
                  {"flag_id": 2, "action": "retract", "revised_claim": "", "paper_ids": []}]
}"""


def _output(state: dict, agent: str, round_num: int) -> dict:
    return next(
        (r for r in state.get("round_outputs", [])
         if r["agent"] == agent and r["round"] == round_num and r.get("stage", "debate") == "debate"),
        {},
    )


def _build_user_prompt(round_num: int, state: dict, hypothesis: str, papers_context: str) -> str:
    if round_num == 1:
        return (
            f"Hypothesis to develop:\n{hypothesis}\n\n"
            f"Available papers from the Knowledge Forge:\n{papers_context}\n\n"
            "Propose your refined research direction backed by these papers."
        )

    if round_num == 3:
        chaos = state.get("chaos_constraint") or ""
        r1 = _output(state, "Innovator", 1)
        return (
            f"Hypothesis: {hypothesis}\n\n"
            f"Your Round 1 proposal:\n{truncate(r1.get('content', ''), 3000)}\n\n"
            f"CHAOS CONSTRAINT INJECTED:\n{chaos}\n\n"
            f"Available papers:\n{papers_context}\n\n"
            "Adapt your proposal to incorporate this constraint."
        )

    chaos = state.get("chaos_constraint") or ""
    r1 = _output(state, "Innovator", 1)
    r3 = _output(state, "Innovator", 3)
    s2 = _output(state, "Skeptic", 2)
    s3 = _output(state, "Skeptic", 3)
    flags = unresolved_hard_flags(state.get("citation_flags", []))
    flags_text = "\n".join(f'  - "{f["claim"]}" - {f["reason"]}' for f in flags) if flags else "  None"
    return (
        f"Hypothesis: {hypothesis}\n\n"
        f"Your Round 1 proposal:\n{truncate(r1.get('content', ''), 2000)}\n\n"
        f"Your Round 3 adaptation:\n{truncate(r3.get('content', ''), 2000)}\n\n"
        f"Skeptic's Round 2 objections:\n{truncate(s2.get('content', ''), 2500)}\n\n"
        f"Skeptic's Round 3 response to the constraint:\n{truncate(s3.get('content', ''), 2000)}\n\n"
        f"Outstanding Citation Flags against you:\n{flags_text}\n\n"
        f"Chaos constraint to address:\n{chaos}\n\n"
        f"Available papers:\n{papers_context}\n\n"
        "Defend your position, address all objections and flags, and present your final methodology."
    )


def _queries(round_num: int, state: dict, hypothesis: str) -> list[str]:
    if round_num == 1:
        return [hypothesis]
    if round_num == 3:
        return [hypothesis, f"{hypothesis} {state.get('chaos_constraint') or ''}"]
    objections = _output(state, "Skeptic", 2).get("claims", [])[:2]
    return [hypothesis, *objections]


def run_innovator(state: dict) -> dict:
    """
    Multi-round Innovator node. Handles Rounds 1, 3, and 4.

    Round determination: counts existing Innovator debate outputs in state.
      0 outputs -> Round 1 (initial proposal)
      1 output  -> Round 3 (chaos response)
      2 outputs -> Round 4 (defense)

    Returns state patch: {"current_round", "round_outputs"}
    """
    round_num = _determine_round(state)
    retry_count: int = state.get("retry_count", 0)
    session_id: str = state["session_id"]
    hypothesis: str = state["hypothesis"]

    papers = retrieve(session_id, _queries(round_num, state, hypothesis),
                      k_each=TOP_K_PAPERS, limit=MAX_PAPERS_IN_PROMPT)

    emit(session_id, "round_start", {"round": round_num, "agent": "Innovator", "stage": "debate"})

    parsed = chat_json(
        messages=[
            {"role": "system", "content": _ROUND_PROMPTS[round_num] + _strictness_note(retry_count)},
            {"role": "user", "content": _build_user_prompt(round_num, state, hypothesis, paper_context(papers))},
        ],
        agent="Innovator",
        session_id=session_id,
        schema=DEBATE_TURN,
        schema_name="debate_turn",
        temperature=0.5,
        max_tokens=3000,
        required_keys=("content", "claims"),
        validate=require_turn("factual claim", "4-8"),
    )
    turn = normalize_debate_turn(parsed)
    claims, claim_citations, citations = map_claims(turn, papers)

    round_output = {
        "agent": "Innovator",
        "round": round_num,
        "stage": "debate",
        "content": resolve_markers(turn["content"], papers),
        "claims": [resolve_markers(c, papers) for c in claims],
        "claim_citations": claim_citations,
        "citations": citations,
    }

    emit(session_id, "round_complete", {
        "round": round_num, "agent": "Innovator", "stage": "debate",
        "summary": summarize(round_output["content"]),
        "content": round_output["content"],
        "claims": len(claims), "citations": len(citations),
        "cost_usd": cost_so_far(session_id),
    })

    print(f"[Innovator] Round {round_num} complete. {len(claims)} claims, {len(citations)} citations.")

    return {
        "current_round": round_num,
        "round_outputs": state.get("round_outputs", []) + [round_output],
    }


# ------------------------------------------------------------------ #
# Targeted repair (replaces re-running the whole debate on retry)
# ------------------------------------------------------------------ #

def run_innovator_repair(state: dict) -> dict:
    """
    Retry node: the Innovator revises or retracts each unresolved hard-flagged claim.

    Retracted and revised claims are marked resolved on their flags (so they leave the
    RAGAS denominator); revised claims are appended as a new "repair" RoundOutput that the
    Fact-Checker then verifies like any other claims.
    """
    session_id: str = state["session_id"]
    hypothesis: str = state["hypothesis"]
    attempt: int = state.get("retry_count", 1)
    all_flags: list[dict] = [dict(f) for f in state.get("citation_flags", [])]
    targets = unresolved_hard_flags(all_flags)

    emit(session_id, "round_start", {"round": 4, "agent": "Innovator", "stage": "repair", "attempt": attempt})

    if not targets:
        return {}

    papers = retrieve(session_id, [f["claim"] for f in targets], k_each=3, limit=8)
    flag_lines = "\n".join(f"F{i}: {f['claim']}  [flagged: {f['reason']}]" for i, f in enumerate(targets, 1))
    parsed = chat_json(
        messages=[
            {"role": "system", "content": _SYSTEM_REPAIR},
            {"role": "user", "content": (
                f"Hypothesis: {hypothesis}\n\nFlagged claims:\n{flag_lines}\n\n"
                f"Available papers:\n{paper_context(papers)}\n\n"
                "Resolve every flagged claim."
            )},
        ],
        agent="Innovator",
        session_id=session_id,
        schema=INNOVATOR_REPAIR,
        schema_name="innovator_repair",
        temperature=0.3,
        max_tokens=2500,
        required_keys=("resolutions",),
    )

    def same_text(a: str, b: str) -> bool:
        return " ".join(a.lower().split()).rstrip(".") == " ".join(b.lower().split()).rstrip(".")

    revised_claims: list[dict] = []
    retracted = 0
    unchanged = 0
    for item in parsed.get("resolutions") or []:
        if not isinstance(item, dict):
            continue
        idx = as_int(item.get("flag_id"))
        if idx is None or not 1 <= idx <= len(targets):
            continue
        target = targets[idx - 1]  # a reference into all_flags
        if target.get("resolved"):
            continue  # the model answered the same flag twice
        action = as_str(item.get("action")).lower()
        revised = as_str(item.get("revised_claim"))
        if action == "revise" and revised:
            if same_text(revised, target["claim"]):
                unchanged += 1  # restating the claim is not a repair; the flag stays open
                continue
            revised_claims.append({"text": revised, "paper_ids": as_int_list(item.get("paper_ids"))})
            target["resolved"] = "revised"
            target["revised_to"] = revised
        else:
            target["resolved"] = "retracted"
            retracted += 1

    claims, claim_citations, citations = map_claims(
        {"content": as_str(parsed.get("content")), "claims": revised_claims}, papers
    )
    round_output = {
        "agent": "Innovator",
        "round": 4,
        "stage": "repair",
        "attempt": attempt,
        "content": resolve_markers(as_str(parsed.get("content")), papers),
        "claims": [resolve_markers(c, papers) for c in claims],
        "claim_citations": claim_citations,
        "citations": citations,
    }

    emit(session_id, "round_complete", {
        "round": 4, "agent": "Innovator", "stage": "repair", "attempt": attempt,
        "summary": summarize(round_output["content"]) or f"Revised {len(claims)} and retracted {retracted} claims.",
        "content": round_output["content"],
        "claims": len(claims), "retracted": retracted, "citations": len(citations),
        "cost_usd": cost_so_far(session_id),
    })
    print(f"[Innovator] Repair {attempt}: {len(claims)} revised, {retracted} retracted, {unchanged} unchanged.")

    return {
        "round_outputs": state.get("round_outputs", []) + [round_output],
        "citation_flags": all_flags,
    }
