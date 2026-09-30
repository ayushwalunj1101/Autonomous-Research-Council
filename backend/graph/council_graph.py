import functools
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from backend.agents.common import unresolved_hard_flags
from backend.config import get_settings
from backend.llm.usage import budget_fraction_used
from backend.runtime import BudgetExceeded, check_cancelled
from backend.sse.event_emitter import emit

RAGAS_THRESHOLD = 0.7
MAX_RETRIES = 2
# Don't start a repair round once this share of the session budget is spent
RETRY_BUDGET_FRACTION = 0.75
RECURSION_LIMIT = 60


# --------------------------------------------------------------------------- #
# Typed sub-structures
# --------------------------------------------------------------------------- #

class CitationFlag(TypedDict, total=False):
    claim: str       # exact claim text extracted from agent output
    agent: str       # "Innovator" | "Skeptic"
    round: int       # debate round number
    reason: str      # e.g. "No retrieved paper supports this claim"
    severity: str    # "hard" (unsupported/contradicted/fabricated) | "soft" (partial support)
    verdict: str     # "partial" | "unsupported" | "contradicted" | "fabricated"
    resolved: str    # "" | "retracted" | "revised" (set by the repair round)
    revised_to: str  # replacement claim text when resolved == "revised"


class Citation(TypedDict):
    paper_id: str
    title: str
    url: str
    relevance_score: float


class RoundOutput(TypedDict, total=False):
    agent: str              # "Innovator" | "Skeptic"
    round: int
    stage: str              # "debate" | "repair"
    attempt: int            # repair attempt number (repair outputs only)
    content: str            # full argument / critique prose
    claims: list[str]       # discrete auditable claims
    claim_citations: list[list[str]]  # paper ids cited for each claim
    citations: list[Citation]
    audited: bool           # set by the Fact-Checker so no output is audited twice


# --------------------------------------------------------------------------- #
# Council State — single source of truth passed through every graph node
# --------------------------------------------------------------------------- #

class CouncilState(TypedDict, total=False):
    # Set once at session start — never mutated during debate
    session_id: str
    mode: int
    hypothesis: str
    keywords: list[str]
    domain: str
    chaos_constraint_override: str | None

    # Debate progress — append-only within an attempt
    current_round: int
    round_outputs: list[RoundOutput]
    citation_flags: list[CitationFlag]
    claim_audits: list[dict]

    # Injected at Round 3
    chaos_constraint: str | None

    # Retry tracking
    retry_count: int
    ragas_score: float | None
    low_confidence_flag: bool
    evaluation_json: dict | None
    best_evaluation: dict | None
    best_ragas: float | None
    attempt_history: list[dict]


def initial_state(
    session_id: str,
    mode: int,
    hypothesis: str,
    keywords: list[str],
    domain: str = "",
    chaos_constraint_override: str | None = None,
) -> dict:
    return {
        "session_id": session_id,
        "mode": mode,
        "hypothesis": hypothesis,
        "keywords": keywords,
        "domain": domain,
        "chaos_constraint_override": chaos_constraint_override,
        "current_round": 0,
        "round_outputs": [],
        "citation_flags": [],
        "claim_audits": [],
        "chaos_constraint": None,
        "retry_count": 0,
        "ragas_score": None,
        "low_confidence_flag": False,
        "evaluation_json": None,
        "best_evaluation": None,
        "best_ragas": None,
        "attempt_history": [],
    }


def final_evaluation(state: dict) -> dict:
    """The best attempt's evaluation (highest RAGAS; later attempts win ties)."""
    return state.get("best_evaluation") or state.get("evaluation_json") or {}


# --------------------------------------------------------------------------- #
# Retry nodes
# --------------------------------------------------------------------------- #

def run_repair_prep(state: dict) -> dict:
    """Targeted retry: counts the attempt; the Innovator then repairs only flagged claims."""
    new_retry = state.get("retry_count", 0) + 1
    flagged = len(unresolved_hard_flags(state.get("citation_flags", [])))
    ragas = state.get("ragas_score") or 0.0
    print(f"[Graph] RAGAS {ragas:.2f} < {RAGAS_THRESHOLD} - repair attempt {new_retry} ({flagged} flagged claims)")
    emit(state["session_id"], "retry", {
        "attempt": new_retry, "max_attempts": MAX_RETRIES, "mode": "targeted",
        "flagged_claims": flagged, "reason": f"RAGAS {ragas:.2f} < {RAGAS_THRESHOLD}",
    })
    return {"retry_count": new_retry}


def run_retry_reset(state: dict) -> dict:
    """
    Full retry (ARC_RETRY_MODE=full): clears the debate for a fresh attempt.
    Preserves session context and the best evaluation so far.
    """
    new_retry = state.get("retry_count", 0) + 1
    ragas = state.get("ragas_score") or 0.0
    print(f"[Graph] RAGAS < {RAGAS_THRESHOLD} - starting full retry {new_retry}...")
    emit(state["session_id"], "retry", {
        "attempt": new_retry, "max_attempts": MAX_RETRIES, "mode": "full",
        "flagged_claims": 0, "reason": f"RAGAS {ragas:.2f} < {RAGAS_THRESHOLD}",
    })
    return {
        "retry_count": new_retry,
        "round_outputs": [],
        "citation_flags": [],
        "claim_audits": [],
        "current_round": 0,
        "chaos_constraint": None,
        "ragas_score": None,
        # best_evaluation / best_ragas / attempt_history intentionally kept
    }


# --------------------------------------------------------------------------- #
# RAGAS conditional router
# --------------------------------------------------------------------------- #

def _ragas_router(state: dict) -> str:
    """
    Routes after Chairman:
      - RAGAS >= 0.7                          -> "end"
      - retries used up (2)                   -> "end" (low_confidence_flag set by Chairman)
      - targeted mode, no flagged claims left -> "end" (nothing a repair could change)
      - >= 75% of the session budget spent    -> "end"
      - otherwise                             -> "repair" (targeted) or "reset" (full)
    """
    ragas = state.get("ragas_score") or 0.0
    retries = state.get("retry_count", 0)
    session_id = state["session_id"]
    mode = get_settings().retry_mode

    if ragas >= RAGAS_THRESHOLD:
        print(f"[Graph] RAGAS router -> end (PASSED, score={ragas:.4f})")
        return "end"
    if retries >= MAX_RETRIES:
        print(f"[Graph] RAGAS router -> end (LOW CONFIDENCE, max retries reached, score={ragas:.4f})")
        return "end"
    if mode != "full" and not unresolved_hard_flags(state.get("citation_flags", [])):
        print("[Graph] RAGAS router -> end (no flagged claims left to repair)")
        emit(session_id, "retry_skipped", {"reason": "No flagged claims left to repair."})
        return "end"
    if budget_fraction_used(session_id) >= RETRY_BUDGET_FRACTION:
        print("[Graph] RAGAS router -> end (session budget mostly spent)")
        emit(session_id, "retry_skipped", {"reason": "Most of the session cost limit is already spent."})
        return "end"

    print(f"[Graph] RAGAS router -> {mode} retry (score={ragas:.4f}, attempt {retries + 1}/{MAX_RETRIES})")
    return "reset" if mode == "full" else "repair"


# --------------------------------------------------------------------------- #
# Graph builder
# --------------------------------------------------------------------------- #

def _guarded(fn):
    """Stops the graph at the next node boundary once the session is cancelled."""
    @functools.wraps(fn)
    def wrapper(state: dict) -> dict:
        check_cancelled(state.get("session_id"))
        return fn(state)
    return wrapper


def build_council_graph():
    """
    Builds and compiles the Council Chamber graph.

    Full topology:
        START
          -> innovator          (R1 — initial proposal)
          -> fact_checker_r1    (verifies R1 Innovator claims)
          -> skeptic            (R2 — rebuttal)
          -> fact_checker_r2    (fabrication check on R2 Skeptic)
          -> chaos_agent        (R3 — constraint injection)
          -> chaos_innovator    (R3 — Innovator responds to constraint)
          -> fact_checker_r3i   (verifies R3 Innovator claims)
          -> chaos_skeptic      (R3 — Skeptic responds to constraint)
          -> fact_checker_r3s   (fabrication check on R3 Skeptic)
          -> innovator_defense  (R4 — Innovator defends vs all objections + chaos)
          -> fact_checker_r4    (verifies R4 Innovator claims)
          -> chairman           (R5 — synthesis + RAGAS + evaluation JSON)
          -> [_ragas_router]
                ├─ "repair" -> repair_prep -> innovator_repair -> fact_checker_repair -> chairman
                ├─ "reset"  -> retry_reset -> innovator   (ARC_RETRY_MODE=full)
                └─ "end"    -> END
    """
    from backend.agents.chairman import run_chairman
    from backend.agents.chaos_agent import run_chaos_agent
    from backend.agents.fact_checker import run_fact_checker
    from backend.agents.innovator import run_innovator, run_innovator_repair
    from backend.agents.skeptic import run_skeptic

    graph = StateGraph(CouncilState)

    nodes = {
        "innovator": run_innovator,              # R1 (and full-retry R1)
        "fact_checker_r1": run_fact_checker,
        "skeptic": run_skeptic,                  # R2
        "fact_checker_r2": run_fact_checker,
        "chaos_agent": run_chaos_agent,          # R3 injection
        "chaos_innovator": run_innovator,        # R3 Innovator response
        "fact_checker_r3i": run_fact_checker,
        "chaos_skeptic": run_skeptic,            # R3 Skeptic response
        "fact_checker_r3s": run_fact_checker,
        "innovator_defense": run_innovator,      # R4 defense
        "fact_checker_r4": run_fact_checker,
        "chairman": run_chairman,                # R5 synthesis
        "repair_prep": run_repair_prep,
        "innovator_repair": run_innovator_repair,
        "fact_checker_repair": run_fact_checker,
        "retry_reset": run_retry_reset,
    }
    for name, fn in nodes.items():
        graph.add_node(name, _guarded(fn))

    sequence = [
        START, "innovator", "fact_checker_r1", "skeptic", "fact_checker_r2", "chaos_agent",
        "chaos_innovator", "fact_checker_r3i", "chaos_skeptic", "fact_checker_r3s",
        "innovator_defense", "fact_checker_r4", "chairman",
    ]
    for src, dst in zip(sequence, sequence[1:]):
        graph.add_edge(src, dst)

    graph.add_conditional_edges(
        "chairman",
        _ragas_router,
        {"repair": "repair_prep", "reset": "retry_reset", "end": END},
    )
    graph.add_edge("repair_prep", "innovator_repair")
    graph.add_edge("innovator_repair", "fact_checker_repair")
    graph.add_edge("fact_checker_repair", "chairman")
    graph.add_edge("retry_reset", "innovator")

    return graph.compile()


# Singleton compiled graph — built once on first use
_compiled_graph = None


def get_council_graph():
    """Returns the singleton compiled graph, building it on first call."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_council_graph()
    return _compiled_graph


def run_council(state: dict) -> dict:
    """
    Runs the full debate synchronously (call from a worker thread).

    The graph is streamed so the latest state survives an exception: if the session's
    cost limit is hit during a repair round, the best evaluation already produced (and
    paid for) is returned instead of failing the whole session.
    """
    last = state
    try:
        for snapshot in get_council_graph().stream(state, {"recursion_limit": RECURSION_LIMIT}, stream_mode="values"):
            last = snapshot
    except BudgetExceeded as exc:
        if not last.get("best_evaluation"):
            raise
        print(f"[Graph] Cost limit reached mid-repair; keeping the best finished attempt. ({exc})")
        emit(state["session_id"], "retry_skipped", {"reason": "The session cost limit was reached during a repair round."})
    return last
