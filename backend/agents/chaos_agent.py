import random

from backend.config import get_settings
from backend.llm.client import LLMError, chat_json
from backend.llm.schemas import CHAOS_SELECTION, as_int
from backend.sse.event_emitter import emit

# (constraint, tags) — tags help the selector and keep ML-only constraints away from
# unrelated fields. "any" constraints fit every domain.
CHAOS_POOL: list[tuple[str, tuple[str, ...]]] = [
    ("Assume the primary dataset has 40% label noise.", ("ml", "data")),
    ("Assume GPU/compute budget is reduced by 50%.", ("ml", "compute")),
    ("Assume no access to proprietary or closed-source datasets.", ("any",)),
    ("Assume the study must be reproducible with open-source tools only.", ("any",)),
    ("Assume the research must be completed in 6 months.", ("any",)),
    ("Assume the target journal requires results on at least 3 benchmark datasets.", ("ml",)),
    ("Assume one of the key baseline models is retracted post-publication.", ("ml",)),
    ("Assume the research team has no domain experts - only ML generalists.", ("ml",)),
    ("Assume cross-institutional data sharing is legally restricted.", ("any", "biomedical")),
    ("Assume the primary methodology has been recently published by a competing lab.", ("any",)),
    ("Assume the available sample size is one third of what was planned.", ("any",)),
    ("Assume the funding body requires pre-registration of all hypotheses and analyses.", ("any",)),
    ("Assume ethics approval forbids collecting any new personal data.", ("any", "biomedical", "social")),
    ("Assume participant recruitment is limited to a single site or country.", ("biomedical", "social")),
    ("Assume the key measurement instrument has a 20% systematic error.", ("any",)),
    ("Assume results must generalize to a low-resource setting with poor infrastructure.", ("any",)),
    ("Assume a regulator requires full interpretability of every model decision.", ("ml", "biomedical")),
    ("Assume longitudinal follow-up is impossible; only cross-sectional data is available.", ("biomedical", "social")),
    ("Assume the budget allows no paid annotation or expert labelling.", ("ml", "data")),
    ("Assume the main data source becomes unavailable halfway through the project.", ("any",)),
]

_SELECT_PROMPT = """You are the Chaos Agent on the Autonomous Research Council.
Pick the ONE constraint from the numbered list that would most seriously stress-test the
hypothesis below while still being relevant to how this research would actually be done.
Avoid constraints that do not apply to the field (e.g. GPU budgets for non-computational work).

Respond with a JSON object only: {"constraint_index": <number from the list>, "reason": "one sentence"}"""


def _select_with_llm(state: dict) -> str | None:
    options = "\n".join(f"{i}: {text}" for i, (text, _tags) in enumerate(CHAOS_POOL))
    try:
        parsed = chat_json(
            messages=[
                {"role": "system", "content": _SELECT_PROMPT},
                {"role": "user", "content": (
                    f"Field: {state.get('domain') or 'unspecified'}\n"
                    f"Hypothesis: {state['hypothesis']}\n\nConstraints:\n{options}"
                )},
            ],
            agent="Chaos Agent",
            session_id=state["session_id"],
            schema=CHAOS_SELECTION,
            schema_name="chaos_selection",
            temperature=0.7,
            max_tokens=300,
            required_keys=("constraint_index",),
        )
    except LLMError as exc:
        print(f"[Chaos Agent] LLM selection failed, falling back to random: {exc}")
        return None
    idx = as_int(parsed.get("constraint_index"))
    if idx is None or not 0 <= idx < len(CHAOS_POOL):
        return None
    return CHAOS_POOL[idx][0]


def run_chaos_agent(state: dict) -> dict:
    """
    Round 3 — injects one real-world constraint.

    Priority: a constraint chosen by the user when starting the session, then the most
    relevant pool entry picked by the LLM (ARC_CHAOS_SELECTION=llm, default), then a
    random pool entry (ARC_CHAOS_SELECTION=random, or if the LLM call fails).

    Returns state patch: {"current_round": 3, "chaos_constraint": str}
    """
    override = (state.get("chaos_constraint_override") or "").strip()
    if override:
        constraint, selected_by = override, "user"
    else:
        constraint = _select_with_llm(state) if get_settings().chaos_selection == "llm" else None
        selected_by = "llm"
        if not constraint:
            constraint, selected_by = random.choice(CHAOS_POOL)[0], "random"

    print(f"[Chaos Agent] CHAOS INJECTION ({selected_by}): {constraint}")
    emit(state["session_id"], "chaos_injection", {"constraint": constraint, "selected_by": selected_by})
    return {
        "current_round": 3,
        "chaos_constraint": constraint,
    }
