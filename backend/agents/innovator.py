import json
import re

from backend.llm.client import chat_completion
from backend.rag.chromadb_client import query_papers
from backend.sse.event_emitter import emit

TOP_K_PAPERS = 5


def _determine_round(state: dict) -> int:
    """Determines which round Innovator is in based on existing outputs."""
    n = sum(1 for r in state.get("round_outputs", []) if r["agent"] == "Innovator")
    return {0: 1, 1: 3}.get(n, 4)


def _strictness_note(retry_count: int) -> str:
    if retry_count == 1:
        return (
            "\nSTRICTNESS NOTE (Retry 1): Reduce speculative claims. "
            "Every claim you make must be directly traceable to a provided paper."
        )
    if retry_count >= 2:
        return (
            "\nSTRICTNESS NOTE (Retry 2 — Maximum): Make ONLY claims with direct paper support. "
            "If you cannot cite a paper for it, do not say it."
        )
    return ""


# ------------------------------------------------------------------ #
# Round-specific system prompts
# ------------------------------------------------------------------ #

_SYSTEM_R1 = """You are the Innovator agent on the Autonomous Research Council.
Round 1 — Opening Argument.
Your role: propose a refined, evidence-backed research direction for the given hypothesis.

Rules:
- Ground every major claim in one of the provided papers.
- Be bold but defensible — no overreach without evidence.
- Structure your output as valid JSON only (no markdown fences).

Output schema:
{
  "content": "Your full argument as flowing prose (3-5 paragraphs).",
  "claims": ["Discrete auditable factual claim 1.", "..."],
  "citations": [{"title": "...", "url": "...", "relevance_score": 87.3}]
}
Each 'claims' entry is a single sentence stating one verifiable fact.
Each 'citations' entry must correspond to one of the provided papers."""

_SYSTEM_R3 = """You are the Innovator agent on the Autonomous Research Council.
Round 3 — Chaos Response.
A real-world constraint has been injected into the debate. You must now adapt your
research proposal to incorporate this constraint constructively.

Rules:
- Acknowledge the constraint directly.
- Show how the methodology can be adapted to work within it.
- Maintain any valid claims from Round 1; update methodology as needed.
- Ground new claims in the provided papers.
- Output valid JSON only (no markdown fences).

Output schema:
{
  "content": "Your adapted proposal addressing the chaos constraint (3-4 paragraphs).",
  "claims": ["Discrete auditable factual claim 1.", "..."],
  "citations": [{"title": "...", "url": "...", "relevance_score": 87.3}]
}"""

_SYSTEM_R4 = """You are the Innovator agent on the Autonomous Research Council.
Round 4 — Defense.
You must now defend your position against all Skeptic objections, address outstanding
Citation Flags, and incorporate the chaos constraint into a final consolidated methodology.

Rules:
- Address every Skeptic objection from Round 2 explicitly.
- Acknowledge every outstanding hard Citation Flag — either find support or retract the claim.
- Show how your final methodology handles the chaos constraint.
- Ground all retained claims in the provided papers.
- Output valid JSON only (no markdown fences).

Output schema:
{
  "content": "Your defense and final methodology (4-5 paragraphs).",
  "claims": ["Discrete auditable factual claim 1.", "..."],
  "citations": [{"title": "...", "url": "...", "relevance_score": 87.3}]
}"""

_ROUND_PROMPTS = {1: _SYSTEM_R1, 3: _SYSTEM_R3, 4: _SYSTEM_R4}


def run_innovator(state: dict) -> dict:
    """
    Multi-round Innovator node. Handles Rounds 1, 3, and 4.

    Round determination: counts existing Innovator outputs in state.
      0 outputs → Round 1 (initial proposal)
      1 output  → Round 3 (chaos response)
      2 outputs → Round 4 (defense)

    Returns state patch:
        {
            "current_round": int,
            "round_outputs": [appended RoundOutput]
        }
    """
    round_num = _determine_round(state)
    retry_count: int = state.get("retry_count", 0)
    session_id: str = state["session_id"]
    hypothesis: str = state["hypothesis"]

    # Retrieve top-k papers for all Innovator rounds
    papers = query_papers(session_id, hypothesis, n_results=TOP_K_PAPERS)
    papers_context = "\n\n".join(
        f"[Paper {i+1}]\nTitle: {p['title']}\nURL: {p['url']}\n"
        f"Relevance: {p['relevance_score']}\nAbstract: {p['abstract'][:500]}"
        for i, p in enumerate(papers)
    )

    emit(session_id, "round_start", {"round": round_num, "agent": "Innovator"})

    system_prompt = _ROUND_PROMPTS[round_num] + _strictness_note(retry_count)

    user_prompt = _build_user_prompt(round_num, state, hypothesis, papers_context)

    raw = chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.5,
        max_tokens=1500,
    )
    parsed = _parse_json(raw)

    round_output = {
        "agent": "Innovator",
        "round": round_num,
        "content": parsed.get("content", ""),
        "claims": parsed.get("claims", []),
        "citations": parsed.get("citations", []),
    }

    summary = (round_output["content"][:150] + "...") if len(round_output["content"]) > 150 else round_output["content"]
    emit(session_id, "round_complete", {"round": round_num, "agent": "Innovator", "summary": summary})

    print(f"[Innovator] Round {round_num} complete. "
          f"{len(round_output['claims'])} claims, "
          f"{len(round_output['citations'])} citations.")

    return {
        "current_round": round_num,
        "round_outputs": state.get("round_outputs", []) + [round_output],
    }


def _build_user_prompt(round_num: int, state: dict, hypothesis: str, papers_context: str) -> str:
    if round_num == 1:
        return (
            f"Hypothesis to develop:\n{hypothesis}\n\n"
            f"Available papers from the Knowledge Forge:\n{papers_context}\n\n"
            "Propose your refined research direction backed by these papers."
        )

    if round_num == 3:
        chaos = state.get("chaos_constraint", "")
        r1 = next((r for r in state["round_outputs"] if r["agent"] == "Innovator" and r["round"] == 1), {})
        return (
            f"Hypothesis: {hypothesis}\n\n"
            f"Your Round 1 proposal:\n{r1.get('content', '')}\n\n"
            f"⚡ CHAOS CONSTRAINT INJECTED:\n{chaos}\n\n"
            f"Available papers:\n{papers_context}\n\n"
            "Adapt your proposal to incorporate this constraint."
        )

    if round_num == 4:
        chaos = state.get("chaos_constraint", "")
        r2_skeptic = next((r for r in state["round_outputs"] if r["agent"] == "Skeptic" and r["round"] == 2), {})
        hard_flags = [f for f in state.get("citation_flags", []) if f["agent"] == "Innovator" and f["severity"] == "hard"]
        flags_text = "\n".join(f"  - \"{f['claim']}\" — {f['reason']}" for f in hard_flags) if hard_flags else "  None"

        return (
            f"Hypothesis: {hypothesis}\n\n"
            f"Skeptic's Round 2 objections:\n{r2_skeptic.get('content', '')}\n\n"
            f"Outstanding hard Citation Flags against you:\n{flags_text}\n\n"
            f"Chaos constraint to address:\n{chaos}\n\n"
            f"Available papers:\n{papers_context}\n\n"
            "Defend your position, address all objections and flags, and present your final methodology."
        )

    return f"Hypothesis: {hypothesis}\n\nPapers:\n{papers_context}"


def _parse_json(raw: str) -> dict:
    try:
        return json.loads(raw, strict=False)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group(), strict=False)
        raise ValueError(f"Innovator LLM returned unparseable output:\n{raw}")
