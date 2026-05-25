import random

from backend.sse.event_emitter import emit

CHAOS_POOL: list[str] = [
    "Assume the primary dataset has 40% label noise.",
    "Assume GPU/compute budget is reduced by 50%.",
    "Assume no access to proprietary or closed-source datasets.",
    "Assume the study must be reproducible with open-source tools only.",
    "Assume the research must be completed in 6 months.",
    "Assume the target journal requires results on at least 3 benchmark datasets.",
    "Assume one of the key baseline models is retracted post-publication.",
    "Assume the research team has no domain experts — only ML generalists.",
    "Assume cross-institutional data sharing is legally restricted.",
    "Assume the primary methodology has been recently published by a competing lab.",
]


def run_chaos_agent(state: dict) -> dict:
    """
    Round 3 — randomly selects one constraint from CHAOS_POOL.
    No LLM call. Pure random selection per the implementation plan.

    Returns state patch:
        {
            "current_round": 3,
            "chaos_constraint": str
        }
    """
    constraint = random.choice(CHAOS_POOL)
    print(f"[Chaos Agent] CHAOS INJECTION: {constraint}")
    emit(state["session_id"], "chaos_injection", {"constraint": constraint})
    return {
        "current_round": 3,
        "chaos_constraint": constraint,
    }
