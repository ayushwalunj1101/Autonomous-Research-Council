from backend.agents.common import (
    cost_so_far,
    map_claims,
    paper_context,
    require_turn,
    resolve_markers,
    retrieve,
    summarize,
    truncate,
)
from backend.config import get_settings
from backend.llm.client import chat_json
from backend.llm.schemas import DEBATE_TURN, normalize_debate_turn
from backend.sse.event_emitter import emit

EVIDENCE_PAPERS = 4


def _determine_round(state: dict) -> int:
    """Determines which round Skeptic is in based on existing outputs."""
    n = sum(1 for r in state.get("round_outputs", []) if r["agent"] == "Skeptic")
    return 2 if n == 0 else 3


def _strictness_note(retry_count: int) -> str:
    if retry_count == 1:
        return (
            "\nSTRICTNESS NOTE (Retry 1): Be rigorous. Only raise objections grounded in "
            "clear logical reasoning. Do not fabricate external facts or statistics."
        )
    if retry_count >= 2:
        return (
            "\nSTRICTNESS NOTE (Retry 2 - Maximum): Every objection must be a direct, "
            "traceable logical flaw in the argument. No speculation."
        )
    return ""


_OUTPUT_LOGIC = """
Respond with a JSON object only:
{
  "content": "Your critique as flowing prose.",
  "claims": [{"text": "One discrete objection stated as a single sentence.", "paper_ids": []}]
}
'paper_ids' must always be an empty list. 3-6 objections."""

_OUTPUT_EVIDENCE = """
You may also cite the numbered counter-evidence papers [1], [2], ... by number only
(never write titles or URLs). Every factual statement about the literature must cite one.

Respond with a JSON object only:
{
  "content": "Your critique as flowing prose, citing papers as [n] where used.",
  "claims": [{"text": "One discrete objection stated as a single sentence.", "paper_ids": [1]}]
}
3-6 objections; use an empty paper_ids list for purely logical objections."""

_RULES_LOGIC = """- You have NO access to external papers or databases. Do NOT cite papers.
- Do NOT invent statistics, retractions, or external facts."""

_RULES_EVIDENCE = """- You may use ONLY the numbered counter-evidence papers provided; cite them by number.
- Do NOT invent statistics, retractions, or facts that are not in those papers."""


def _system_r2(evidence: bool) -> str:
    return f"""You are the Skeptic agent on the Autonomous Research Council.
Round 2 - Logical Rebuttal.
Your role: attack the Innovator's argument rigorously.

STRICT RULES:
{_RULES_EVIDENCE if evidence else _RULES_LOGIC}
- Attack on: logical fallacies, methodology gaps, missing counterarguments,
  overreaching conclusions, unsupported leaps of reasoning.
- If Citation Flags were raised against the Innovator, exploit those weaknesses.
- Be rigorous and adversarial, but logically honest.
- Keep the critique to 3-5 paragraphs.""" + (_OUTPUT_EVIDENCE if evidence else _OUTPUT_LOGIC)


def _system_r3(evidence: bool) -> str:
    return f"""You are the Skeptic agent on the Autonomous Research Council.
Round 3 - Chaos Response.
A real-world constraint has been injected into the debate. You must now respond to
how this constraint affects the Innovator's proposal - and your own critique.

STRICT RULES:
{_RULES_EVIDENCE if evidence else _RULES_LOGIC}
- Use the constraint to reinforce your existing objections or raise new logical ones.
- Show how the constraint makes the Innovator's proposal harder to execute.
- Keep the response to 2-3 paragraphs.""" + (_OUTPUT_EVIDENCE if evidence else _OUTPUT_LOGIC)


def flags_seen_by_skeptic(state: dict) -> str:
    """The Round 1 citation-flag text shown to the Skeptic (also given to the fabrication audit)."""
    flags = [f for f in state.get("citation_flags", []) if f["round"] == 1 and f["agent"] == "Innovator"]
    if not flags:
        return ""
    lines = "\n".join(f"  [{f['severity'].upper()}] \"{f['claim']}\" - {f['reason']}" for f in flags)
    return f"\nCitation Flags raised against Innovator:\n{lines}\n"


def _innovator_output(state: dict, round_num: int) -> dict:
    return next(
        (r for r in state.get("round_outputs", [])
         if r["agent"] == "Innovator" and r["round"] == round_num and r.get("stage", "debate") == "debate"),
        {},
    )


def _build_r2_prompt(state: dict, hypothesis: str, evidence_context: str) -> str:
    innovator_r1 = _innovator_output(state, 1)
    evidence = f"\nCounter-evidence papers:\n{evidence_context}\n" if evidence_context else ""
    return (
        f"Research hypothesis under debate:\n{hypothesis}\n\n"
        f"Innovator's Round 1 argument:\n{truncate(innovator_r1.get('content', ''), 4000)}\n"
        f"{flags_seen_by_skeptic(state)}{evidence}\n"
        "Deliver your critique."
    )


def _build_r3_prompt(state: dict, hypothesis: str, evidence_context: str) -> str:
    chaos = state.get("chaos_constraint") or ""
    innovator_r3 = _innovator_output(state, 3)
    r2_self = next(
        (r for r in state.get("round_outputs", []) if r["agent"] == "Skeptic" and r["round"] == 2),
        {},
    )
    evidence = f"Counter-evidence papers:\n{evidence_context}\n\n" if evidence_context else ""
    return (
        f"Hypothesis: {hypothesis}\n\n"
        f"Your Round 2 critique:\n{truncate(r2_self.get('content', ''), 3000)}\n\n"
        f"CHAOS CONSTRAINT INJECTED:\n{chaos}\n\n"
        f"Innovator's Round 3 chaos response:\n{truncate(innovator_r3.get('content', ''), 3000)}\n\n"
        f"{evidence}"
        "Respond to the constraint - show how it compounds the Innovator's challenges."
    )


def run_skeptic(state: dict) -> dict:
    """
    Multi-round Skeptic node. Handles Rounds 2 and 3.

    Round determination: counts existing Skeptic outputs in state.
      0 outputs -> Round 2 (initial rebuttal)
      1 output  -> Round 3 (chaos response)

    With ARC_SKEPTIC_EVIDENCE=1 the Skeptic also receives papers retrieved for the
    hypothesis' limitations and may cite them; otherwise it argues from logic alone.

    Returns state patch: {"current_round", "round_outputs"}
    """
    round_num = _determine_round(state)
    retry_count: int = state.get("retry_count", 0)
    hypothesis: str = state["hypothesis"]
    session_id: str = state["session_id"]
    evidence = get_settings().skeptic_evidence

    emit(session_id, "round_start", {"round": round_num, "agent": "Skeptic", "stage": "debate"})

    papers: list[dict] = []
    if evidence:
        queries = [f"limitations and failure cases of {hypothesis}", f"challenges of {hypothesis}"]
        if round_num == 3:
            queries.append(f"{state.get('chaos_constraint') or ''} limitations")
        papers = retrieve(session_id, queries, k_each=3, limit=EVIDENCE_PAPERS)
    evidence_context = paper_context(papers) if papers else ""

    if round_num == 2:
        system_prompt = _system_r2(evidence) + _strictness_note(retry_count)
        user_prompt = _build_r2_prompt(state, hypothesis, evidence_context)
    else:
        system_prompt = _system_r3(evidence) + _strictness_note(retry_count)
        user_prompt = _build_r3_prompt(state, hypothesis, evidence_context)

    parsed = chat_json(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        agent="Skeptic",
        session_id=session_id,
        schema=DEBATE_TURN,
        schema_name="debate_turn",
        temperature=0.6,
        max_tokens=2500,
        required_keys=("content", "claims"),
        validate=require_turn("objection", "3-6"),
    )
    turn = normalize_debate_turn(parsed)
    if not evidence:
        for claim in turn["claims"]:
            claim["paper_ids"] = []  # logic-only Skeptic never cites
    claims, claim_citations, citations = map_claims(turn, papers)

    round_output = {
        "agent": "Skeptic",
        "round": round_num,
        "stage": "debate",
        "content": resolve_markers(turn["content"], papers),
        "claims": [resolve_markers(c, papers) for c in claims],
        "claim_citations": claim_citations,
        "citations": citations,
    }

    emit(session_id, "round_complete", {
        "round": round_num, "agent": "Skeptic", "stage": "debate",
        "summary": summarize(round_output["content"]),
        "content": round_output["content"],
        "claims": len(claims), "citations": len(citations),
        "cost_usd": cost_so_far(session_id),
    })

    print(f"[Skeptic] Round {round_num} complete. {len(claims)} objections.")

    return {
        "current_round": round_num,
        "round_outputs": state.get("round_outputs", []) + [round_output],
    }
