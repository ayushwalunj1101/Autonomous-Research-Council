import json

from backend.agents.common import truncate
from backend.config import get_settings
from backend.llm.client import LLMError, active_model, chat_json
from backend.llm.schemas import CHAIRMAN, CHAIRMAN_SCORES
from backend.llm.usage import budget_fraction_used
from backend.runtime import BudgetExceeded
from backend.rag.chromadb_client import list_papers
from backend.scoring.evaluation import build_evaluation, build_signals, claim_audit
from backend.scoring.ragas_scorer import compute_ragas_score
from backend.sse.event_emitter import emit

RAGAS_THRESHOLD = 0.7
# Skip the extra scoring samples once most of the session budget is spent
_SAMPLING_BUDGET_FRACTION = 0.8

_RUBRIC = """SCORING RUBRIC — use the full 0-100 range; do not default to round "safe" numbers.
novelty_score (how new the refined hypothesis is relative to the retrieved papers):
  85-100 no retrieved paper tests this idea or combination; 60-84 new angle on studied ground;
  30-59 incremental over close prior work; 0-29 an existing paper already tests it.
  Anchor on NEAREST PAPER SIMILARITY: >= 75 usually means novelty below 60.
feasibility_score (can it be executed, especially under the chaos constraint):
  85-100 standard data/methods, constraint handled convincingly; 60-84 feasible with
  identifiable risks; 30-59 major unresolved obstacles; 0-29 not executable as proposed.
research_gap_score (how clearly the literature leaves this question open):
  85-100 papers explicitly call for it; 60-84 gap implied by limitations sections;
  30-59 partially answered already; 0-29 answered.
overall_confidence (how far the council's conclusion can be trusted):
  must fall below 50 when RAGAS < 0.7 or when claims were contradicted; weigh unresolved
  Skeptic objections.
Give a one-sentence rationale per score that cites the evidence you used."""

_SYSTEM_PROMPT = f"""You are the Chairman of the Autonomous Research Council.
Your role: read the full debate transcript and produce a definitive research evaluation.

You will receive:
- The research hypothesis
- All debate rounds (Innovator, Skeptic, chaos responses, defense, repair rounds)
- The Fact-Checker's verdict on every Innovator claim, and Citation Flags
- Evidence signals computed from the paper corpus, and the RAGAS faithfulness score
- The numbered list of retrieved papers

{_RUBRIC}

Other rules:
- strengths and weaknesses must each have 3-5 items.
- proposed_methodology must have 4-6 steps, each formatted "Step N: Title — description".
- top_papers: choose up to 5 of the numbered papers most relevant to the refined hypothesis
  (refer to them by number only) with a one-sentence summary each.
- chaos_response_summary: 2-3 sentences on how the constraint was addressed.

Respond with a JSON object only:
{{
  "novelty_score": <int>, "feasibility_score": <int>, "research_gap_score": <int>, "overall_confidence": <int>,
  "score_rationale": {{"novelty": "...", "feasibility": "...", "research_gap": "...", "overall": "..."}},
  "refined_hypothesis": "<1-2 sentence refined version of the hypothesis>",
  "strengths": ["..."], "weaknesses": ["..."],
  "chaos_response_summary": "...",
  "proposed_methodology": ["Step 1: ...", "..."],
  "top_papers": [{{"paper_id": <number from the list>, "summary": "<1 sentence>"}}]
}}"""

_SCORES_PROMPT = f"""You are an independent reviewer on the Autonomous Research Council.
Read the debate transcript and score the hypothesis. Judge independently; do not assume
any earlier scores.

{_RUBRIC}

Respond with a JSON object only:
{{"novelty_score": <int>, "feasibility_score": <int>, "research_gap_score": <int>, "overall_confidence": <int>,
  "score_rationale": {{"novelty": "...", "feasibility": "...", "research_gap": "...", "overall": "..."}}}}"""


def _build_context(state: dict, ragas_score: float, signals: dict, numbered_papers: list[dict]) -> str:
    """Assembles the debate transcript, claim verdicts and evidence signals into one context string."""
    lines: list[str] = [f"RESEARCH HYPOTHESIS:\n{state['hypothesis']}\n"]
    audits = state.get("claim_audits", [])

    for output in state.get("round_outputs", []):
        agent, rnd = output["agent"], output["round"]
        stage = output.get("stage", "debate")
        label = f"REPAIR {output.get('attempt', '')} — INNOVATOR" if stage == "repair" else f"ROUND {rnd} — {agent.upper()}"
        lines.append(f"{label}:")
        lines.append(truncate(output.get("content", ""), 3500))
        for claim in output.get("claims", []):
            record = next((a for a in audits if a["claim"] == claim and a["round"] == rnd
                           and (a.get("stage") or "debate") == stage), None)
            verdict = f" [{record['verdict'].upper()}]" if record else ""
            lines.append(f"  - claim{verdict}: {claim}")
        lines.append("")

    flags = [f for f in state.get("citation_flags", []) if not f.get("resolved")]
    if flags:
        lines.append("OUTSTANDING CITATION FLAGS:")
        for f in flags:
            lines.append(f"  [{f['severity'].upper()}] ({f['agent']} R{f['round']}) \"{f['claim']}\" — {f['reason']}")
        lines.append("")
    resolved = [f for f in state.get("citation_flags", []) if f.get("resolved")]
    if resolved:
        lines.append("CLAIMS RESOLVED IN REPAIR ROUNDS:")
        for f in resolved:
            lines.append(f"  {f['resolved'].upper()}: \"{f['claim']}\"" + (f" -> \"{f.get('revised_to')}\"" if f.get("revised_to") else ""))
        lines.append("")

    chaos = state.get("chaos_constraint")
    if chaos:
        lines.append(f"CHAOS CONSTRAINT (Round 3):\n{chaos}\n")

    lines.append("EVIDENCE SIGNALS (computed from the corpus, not by an LLM):")
    lines.append(f"  NEAREST PAPER SIMILARITY to the hypothesis: {signals['nearest_paper_similarity']} / 100")
    lines.append(f"  Papers with similarity >= 60: {signals['close_papers']} of {signals['papers_total']}")
    lines.append(f"  Claim verdicts (standing claims): {json.dumps(signals['verdict_counts'])}")
    lines.append(f"  Claims retracted: {signals['retracted']}, revised: {signals['revised']}")
    lines.append(f"  Skeptic objections: {signals['skeptic_objections']}, fabrication flags: {signals['fabrication_flags']}")
    lines.append(f"RAGAS FAITHFULNESS SCORE: {ragas_score}\n")

    lines.append("NUMBERED PAPERS (similarity to the hypothesis):")
    for i, p in enumerate(numbered_papers, 1):
        lines.append(f"  [{i}] {p['title']} ({p.get('relevance_score', 0)})")
    return "\n".join(lines)


def run_chairman(state: dict) -> dict:
    """
    Round 5 — synthesizes all prior rounds and produces the final evaluation JSON.

    Steps:
      1. Computes the RAGAS faithfulness score from round_outputs + citation_flags.
      2. Computes evidence signals from the corpus and claim verdicts.
      3. One full evaluation call, plus (ARC_SCORING_SAMPLES - 1) independent scoring-only
         calls; the report shows the median score and the min-max range.
      4. Merges LLM judgement with computed facts (build_evaluation) and keeps the best
         attempt across repair rounds.

    Returns state patch:
        {"current_round", "ragas_score", "low_confidence_flag", "evaluation_json",
         "best_evaluation", "best_ragas", "attempt_history"}
    """
    session_id: str = state["session_id"]
    retry_count: int = state.get("retry_count", 0)
    round_outputs: list[dict] = state.get("round_outputs", [])
    citation_flags: list[dict] = state.get("citation_flags", [])

    ragas_score = compute_ragas_score(round_outputs, citation_flags)
    low_confidence_flag = ragas_score < RAGAS_THRESHOLD

    emit(session_id, "ragas_score", {"score": ragas_score, "passed": not low_confidence_flag, "attempt": retry_count})
    print(f"[Chairman] RAGAS score: {ragas_score:.4f} | Low confidence: {low_confidence_flag} | Retry: {retry_count}")

    papers = list_papers(session_id)
    numbered = papers[:20]
    signals = build_signals(state, papers, claim_audit(state))
    context = _build_context(state, ragas_score, signals, numbered)

    main = chat_json(
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"{context}\n\nNow produce your definitive research evaluation JSON."},
        ],
        agent="Chairman",
        session_id=session_id,
        schema=CHAIRMAN,
        schema_name="chairman",
        temperature=0.3,
        max_tokens=4000,
        required_keys=("novelty_score", "refined_hypothesis"),
    )

    samples = [main]
    for _ in range(get_settings().scoring_samples - 1):
        if budget_fraction_used(session_id) >= _SAMPLING_BUDGET_FRACTION:
            print("[Chairman] Skipping extra scoring samples to stay within the session budget.")
            break
        try:
            samples.append(chat_json(
                messages=[
                    {"role": "system", "content": _SCORES_PROMPT},
                    {"role": "user", "content": f"{context}\n\nScore the hypothesis."},
                ],
                agent="Chairman",
                session_id=session_id,
                schema=CHAIRMAN_SCORES,
                schema_name="chairman_scores",
                temperature=0.8,
                max_tokens=800,
                required_keys=("novelty_score",),
            ))
        except (LLMError, BudgetExceeded) as exc:
            print(f"[Chairman] Extra scoring sample failed ({exc}); continuing with {len(samples)}.")
            break

    attempt_history = list(state.get("attempt_history", [])) + [
        {"attempt": retry_count, "ragas_score": ragas_score, "passed": not low_confidence_flag}
    ]
    evaluation = build_evaluation(
        main, samples,
        state={**state, "attempt_history": attempt_history},
        papers=papers,
        numbered_papers=numbered,
        ragas_score=ragas_score,
        low_confidence_flag=low_confidence_flag,
        model=active_model("Chairman"),
    )

    print(f"[Chairman] Evaluation complete. "
          f"Novelty={evaluation['novelty_score']} {evaluation['score_ranges']['novelty']} "
          f"Feasibility={evaluation['feasibility_score']} Overall={evaluation['overall_confidence']}")

    best_ragas = state.get("best_ragas")
    patch = {
        "current_round": 5,
        "ragas_score": ragas_score,
        "low_confidence_flag": low_confidence_flag,
        "evaluation_json": evaluation,
        "attempt_history": attempt_history,
    }
    # Later attempts win ties: they include the repair work
    if best_ragas is None or ragas_score >= best_ragas:
        patch["best_evaluation"] = evaluation
        patch["best_ragas"] = ragas_score
    return patch
