import json
import re

from backend.llm.client import chat_completion
from backend.scoring.ragas_scorer import compute_ragas_score
from backend.sse.event_emitter import emit


_SYSTEM_PROMPT = """You are the Chairman of the Autonomous Research Council.
Your role: read the full debate transcript and produce a definitive research evaluation.

You will receive:
- The research hypothesis
- All debate rounds (Innovator, Skeptic, chaos responses, defense)
- Citation Flags raised by the Fact-Checker
- A pre-computed RAGAS faithfulness score and low-confidence flag

Produce a single valid JSON object — no markdown fences, no extra text.
Be precise, balanced, and evidence-driven. Your JSON is the single source of truth
for the entire output layer (infographics, report, PDF).

Required output schema:
{
  "novelty_score": <int 0-100>,
  "feasibility_score": <int 0-100>,
  "research_gap_score": <int 0-100>,
  "overall_confidence": <int 0-100>,
  "ragas_score": <float — use the value provided to you exactly>,
  "low_confidence_flag": <bool — use the value provided to you exactly>,
  "refined_hypothesis": "<1-2 sentence refined version of the hypothesis>",
  "strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "weaknesses": ["<weakness 1>", "<weakness 2>", "<weakness 3>"],
  "chaos_constraint": "<the constraint that was injected>",
  "chaos_response_summary": "<2-3 sentences on how the constraint was addressed>",
  "proposed_methodology": ["Step 1: ...", "Step 2: ...", "Step 3: ..."],
  "top_papers": [
    {"title": "<paper title>", "relevance_score": <int 0-100>, "summary": "<1 sentence>"}
  ],
  "references": ["<full citation string 1>", "<full citation string 2>"]
}

Rules:
- novelty/feasibility/research_gap/overall_confidence must reflect your honest assessment.
- strengths and weaknesses must each have 3-5 items.
- proposed_methodology must have 4-6 steps.
- top_papers must have exactly 5 entries drawn from papers cited during the debate.
- references must list all papers cited during the debate.
- Do NOT change ragas_score or low_confidence_flag — copy them exactly as provided."""


def _build_context(state: dict, ragas_score: float, low_confidence_flag: bool) -> str:
    """Assembles the full debate transcript into a single context string."""
    lines: list[str] = []

    lines.append(f"RESEARCH HYPOTHESIS:\n{state['hypothesis']}\n")

    # Round outputs — grouped by round number then agent
    for output in state.get("round_outputs", []):
        agent = output["agent"]
        rnd = output["round"]
        lines.append(f"ROUND {rnd} — {agent.upper()}:")
        lines.append(output["content"])
        if output.get("citations"):
            cite_list = ", ".join(c.get("title", "") for c in output["citations"])
            lines.append(f"  Citations: {cite_list}")
        lines.append("")

        # Append flags for this round/agent immediately after
        round_flags = [
            f for f in state.get("citation_flags", [])
            if f["round"] == rnd and f["agent"] == agent
        ]
        if round_flags:
            lines.append(f"  CITATION FLAGS (Round {rnd} — {agent}):")
            for f in round_flags:
                lines.append(f"  [{f['severity'].upper()}] \"{f['claim']}\" — {f['reason']}")
            lines.append("")

    chaos = state.get("chaos_constraint")
    if chaos:
        lines.append(f"CHAOS CONSTRAINT (Round 3):\n{chaos}\n")

    lines.append(f"RAGAS FAITHFULNESS SCORE: {ragas_score}")
    lines.append(f"LOW CONFIDENCE FLAG: {str(low_confidence_flag).lower()}")

    return "\n".join(lines)


def run_chairman(state: dict) -> dict:
    """
    Round 5 — Synthesizes all prior rounds and produces the final evaluation JSON.

    Steps:
      1. Computes RAGAS faithfulness score from round_outputs + citation_flags.
      2. Determines low_confidence_flag (RAGAS < 0.7 after max retries).
      3. Builds full debate context string.
      4. Calls Groq LLM → structured evaluation JSON.
      5. Injects ragas_score + low_confidence_flag into JSON (overwrite LLM values).

    Returns state patch:
        {
            "current_round": 5,
            "ragas_score": float,
            "low_confidence_flag": bool,
            "evaluation_json": dict
        }
    """
    round_outputs: list[dict] = state.get("round_outputs", [])
    citation_flags: list[dict] = state.get("citation_flags", [])
    retry_count: int = state.get("retry_count", 0)

    session_id: str = state["session_id"]

    ragas_score = compute_ragas_score(round_outputs, citation_flags)
    low_confidence_flag = ragas_score < 0.7 and retry_count >= 2

    emit(session_id, "ragas_score", {"score": ragas_score, "passed": ragas_score >= 0.7})

    print(f"[Chairman] RAGAS score: {ragas_score:.4f} | "
          f"Low confidence: {low_confidence_flag} | Retry: {retry_count}")

    context = _build_context(state, ragas_score, low_confidence_flag)
    user_prompt = (
        f"{context}\n\n"
        "Now produce your definitive research evaluation JSON."
    )

    raw = chat_completion(
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=2000,
    )
    evaluation = _parse_json(raw)

    # Enforce correct ragas_score and low_confidence_flag — never trust LLM for these
    evaluation["ragas_score"] = ragas_score
    evaluation["low_confidence_flag"] = low_confidence_flag

    print(f"[Chairman] Evaluation complete. "
          f"Novelty={evaluation.get('novelty_score')} "
          f"Feasibility={evaluation.get('feasibility_score')} "
          f"Overall={evaluation.get('overall_confidence')}")

    return {
        "current_round": 5,
        "ragas_score": ragas_score,
        "low_confidence_flag": low_confidence_flag,
        "evaluation_json": evaluation,
    }


def _parse_json(raw: str) -> dict:
    try:
        return json.loads(raw, strict=False)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group(), strict=False)
        raise ValueError(f"Chairman LLM returned unparseable output:\n{raw}")
