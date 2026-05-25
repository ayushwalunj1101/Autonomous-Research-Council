import json
import re

from backend.llm.client import chat_completion
from backend.sse.event_emitter import emit


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
            "\nSTRICTNESS NOTE (Retry 2 — Maximum): Every objection must be a direct, "
            "traceable logical flaw in the argument. No speculation."
        )
    return ""


_SYSTEM_R2 = """You are the Skeptic agent on the Autonomous Research Council.
Round 2 — Logical Rebuttal.
Your role: attack the Innovator's argument using pure logic and reasoning alone.

STRICT RULES:
- You have NO access to external papers or databases. Do NOT cite papers.
- Do NOT invent statistics, retractions, or external facts.
- Attack only on: logical fallacies, methodology gaps, missing counterarguments,
  overreaching conclusions, unsupported leaps of reasoning.
- If Citation Flags were raised against the Innovator, exploit those weaknesses.
- Be rigorous and adversarial, but logically honest.

Output schema (valid JSON only, no markdown fences):
{
  "content": "Your full critique as flowing prose (3-5 paragraphs).",
  "claims": ["Discrete objection 1 stated as a single sentence.", "..."],
  "citations": []
}
'citations' must always be an empty list."""

_SYSTEM_R3 = """You are the Skeptic agent on the Autonomous Research Council.
Round 3 — Chaos Response.
A real-world constraint has been injected into the debate. You must now respond to
how this constraint affects the Innovator's proposal — and your own critique.

STRICT RULES:
- You have NO access to external papers or databases. Do NOT cite papers.
- Use the constraint to reinforce your existing objections or raise new logical ones.
- Show how the constraint makes the Innovator's proposal harder to execute.
- Do NOT invent statistics or external facts.

Output schema (valid JSON only, no markdown fences):
{
  "content": "Your response to the chaos constraint (2-3 paragraphs).",
  "claims": ["Discrete objection incorporating constraint.", "..."],
  "citations": []
}
'citations' must always be an empty list."""


def run_skeptic(state: dict) -> dict:
    """
    Multi-round Skeptic node. Handles Rounds 2 and 3.

    Round determination: counts existing Skeptic outputs in state.
      0 outputs → Round 2 (initial rebuttal)
      1 output  → Round 3 (chaos response)

    Returns state patch:
        {
            "current_round": int,
            "round_outputs": [appended RoundOutput]
        }
    """
    round_num = _determine_round(state)
    retry_count: int = state.get("retry_count", 0)
    hypothesis: str = state["hypothesis"]

    session_id: str = state["session_id"]
    emit(session_id, "round_start", {"round": round_num, "agent": "Skeptic"})

    if round_num == 2:
        system_prompt = _SYSTEM_R2 + _strictness_note(retry_count)
        user_prompt = _build_r2_prompt(state, hypothesis)
    else:
        system_prompt = _SYSTEM_R3 + _strictness_note(retry_count)
        user_prompt = _build_r3_prompt(state, hypothesis)

    raw = chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.6,
        max_tokens=1200,
    )
    parsed = _parse_json(raw)

    round_output = {
        "agent": "Skeptic",
        "round": round_num,
        "content": parsed.get("content", ""),
        "claims": parsed.get("claims", []),
        "citations": [],  # Skeptic never cites
    }

    summary = (round_output["content"][:150] + "...") if len(round_output["content"]) > 150 else round_output["content"]
    emit(session_id, "round_complete", {"round": round_num, "agent": "Skeptic", "summary": summary})

    print(f"[Skeptic] Round {round_num} complete. {len(round_output['claims'])} objections.")

    return {
        "current_round": round_num,
        "round_outputs": state.get("round_outputs", []) + [round_output],
    }


def _build_r2_prompt(state: dict, hypothesis: str) -> str:
    innovator_r1 = next(
        (r for r in state.get("round_outputs", []) if r["agent"] == "Innovator" and r["round"] == 1),
        {},
    )
    flags = [f for f in state.get("citation_flags", []) if f["round"] == 1]
    flags_text = ""
    if flags:
        flag_lines = "\n".join(
            f"  [{f['severity'].upper()}] \"{f['claim']}\" — {f['reason']}"
            for f in flags
        )
        flags_text = f"\nCitation Flags raised against Innovator:\n{flag_lines}\n"

    return (
        f"Research hypothesis under debate:\n{hypothesis}\n\n"
        f"Innovator's Round 1 argument:\n{innovator_r1.get('content', '')}\n"
        f"{flags_text}\n"
        "Deliver your logical critique."
    )


def _build_r3_prompt(state: dict, hypothesis: str) -> str:
    chaos = state.get("chaos_constraint", "")
    innovator_r3 = next(
        (r for r in state.get("round_outputs", []) if r["agent"] == "Innovator" and r["round"] == 3),
        {},
    )
    r2_self = next(
        (r for r in state.get("round_outputs", []) if r["agent"] == "Skeptic" and r["round"] == 2),
        {},
    )
    return (
        f"Hypothesis: {hypothesis}\n\n"
        f"Your Round 2 critique:\n{r2_self.get('content', '')}\n\n"
        f"⚡ CHAOS CONSTRAINT INJECTED:\n{chaos}\n\n"
        f"Innovator's Round 3 chaos response:\n{innovator_r3.get('content', '')}\n\n"
        "Respond to the constraint — show how it compounds the Innovator's challenges."
    )


def _parse_json(raw: str) -> dict:
    try:
        return json.loads(raw, strict=False)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group(), strict=False)
        raise ValueError(f"Skeptic LLM returned unparseable output:\n{raw}")
