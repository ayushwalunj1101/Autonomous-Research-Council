from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from backend.sse.event_emitter import emit


# --------------------------------------------------------------------------- #
# Typed sub-structures
# --------------------------------------------------------------------------- #

class CitationFlag(TypedDict):
    claim: str       # exact claim text extracted from agent output
    agent: str       # "Innovator" | "Skeptic"
    round: int       # debate round number
    reason: str      # e.g. "No supporting paper found in ChromaDB"
    severity: str    # "hard" (zero support) | "soft" (weak support only)


class Citation(TypedDict):
    title: str
    url: str
    relevance_score: float


class RoundOutput(TypedDict):
    agent: str              # "Innovator" | "Skeptic"
    round: int
    content: str            # full argument / critique prose
    claims: list[str]       # discrete auditable claims extracted by LLM
    citations: list[Citation]  # always empty for Skeptic


# --------------------------------------------------------------------------- #
# Council State — single source of truth passed through every graph node
# --------------------------------------------------------------------------- #

class CouncilState(TypedDict):
    # Set once from /api/start — never mutated during debate
    session_id: str
    mode: int
    hypothesis: str
    keywords: list[str]

    # Debate progress — append-only across all rounds
    current_round: int
    round_outputs: list[RoundOutput]
    citation_flags: list[CitationFlag]

    # Injected at Round 3
    chaos_constraint: str | None

    # Retry tracking
    retry_count: int
    ragas_score: float | None
    low_confidence_flag: bool
    evaluation_json: dict | None


# --------------------------------------------------------------------------- #
# Retry reset node
# --------------------------------------------------------------------------- #

def run_retry_reset(state: dict) -> dict:
    """
    Clears debate state for a fresh retry attempt.
    Increments retry_count. Preserves session context and
    evaluation_json (holds best attempt so far for the Secretary).
    """
    new_retry = state.get("retry_count", 0) + 1
    print(f"[Graph] RAGAS < 0.7 - starting retry {new_retry}...")
    emit(state["session_id"], "retry", {"attempt": new_retry, "reason": "RAGAS < 0.7"})
    return {
        "retry_count": new_retry,
        "round_outputs": [],
        "citation_flags": [],
        "current_round": 0,
        "chaos_constraint": None,
        "ragas_score": None,
        # evaluation_json intentionally kept — Secretary uses best attempt
    }


# --------------------------------------------------------------------------- #
# RAGAS conditional router
# --------------------------------------------------------------------------- #

def _ragas_router(state: dict) -> str:
    """
    Routes after Chairman:
      - RAGAS >= 0.7           → "end"
      - RAGAS < 0.7, retries < 2 → "retry"  (back to innovator via retry_reset)
      - RAGAS < 0.7, retries >= 2 → "end"   (low_confidence_flag set by Chairman)
    """
    ragas = state.get("ragas_score") or 0.0
    retries = state.get("retry_count", 0)

    if ragas >= 0.7 or retries >= 2:
        status = "PASSED" if ragas >= 0.7 else "LOW CONFIDENCE (max retries reached)"
        print(f"[Graph] RAGAS router -> end ({status}, score={ragas:.4f})")
        return "end"

    print(f"[Graph] RAGAS router -> retry (score={ragas:.4f}, attempt {retries + 1}/2)")
    return "retry"


# --------------------------------------------------------------------------- #
# Graph builder
# --------------------------------------------------------------------------- #

def build_council_graph():
    """
    Builds and compiles the full Phase 3 Council Chamber graph.

    Full topology:
        START
          → innovator          (R1 — initial proposal)
          → fact_checker_r1    (audits R1 Innovator via ChromaDB)
          → skeptic            (R2 — logical rebuttal)
          → fact_checker_r2    (audits R2 Skeptic via LLM fabrication check)
          → chaos_agent        (R3 — random constraint injection)
          → chaos_innovator    (R3 — Innovator responds to constraint)
          → chaos_skeptic      (R3 — Skeptic responds to constraint)
          → innovator_defense  (R4 — Innovator defends vs all objections + chaos)
          → fact_checker_r4    (R4 — final full audit of all Innovator claims)
          → chairman           (R5 — synthesis + RAGAS scoring + evaluation JSON)
          → [_ragas_router]
                ├─ "retry" → retry_reset → innovator  (loop, max 2x)
                └─ "end"   → END
    """
    from backend.agents.chaos_agent import run_chaos_agent
    from backend.agents.chairman import run_chairman
    from backend.agents.fact_checker import run_fact_checker
    from backend.agents.innovator import run_innovator
    from backend.agents.skeptic import run_skeptic

    graph = StateGraph(CouncilState)

    # --- Nodes ---
    graph.add_node("innovator",         run_innovator)       # R1 (and retry R1)
    graph.add_node("fact_checker_r1",   run_fact_checker)    # audits R1
    graph.add_node("skeptic",           run_skeptic)         # R2
    graph.add_node("fact_checker_r2",   run_fact_checker)    # audits R2
    graph.add_node("chaos_agent",       run_chaos_agent)     # R3 injection
    graph.add_node("chaos_innovator",   run_innovator)       # R3 Innovator response
    graph.add_node("chaos_skeptic",     run_skeptic)         # R3 Skeptic response
    graph.add_node("innovator_defense", run_innovator)       # R4 defense
    graph.add_node("fact_checker_r4",   run_fact_checker)    # R4 final full audit
    graph.add_node("chairman",          run_chairman)        # R5 synthesis
    graph.add_node("retry_reset",       run_retry_reset)     # retry state cleaner

    # --- Edges ---
    graph.add_edge(START,              "innovator")
    graph.add_edge("innovator",        "fact_checker_r1")
    graph.add_edge("fact_checker_r1",  "skeptic")
    graph.add_edge("skeptic",          "fact_checker_r2")
    graph.add_edge("fact_checker_r2",  "chaos_agent")
    graph.add_edge("chaos_agent",      "chaos_innovator")
    graph.add_edge("chaos_innovator",  "chaos_skeptic")
    graph.add_edge("chaos_skeptic",    "innovator_defense")
    graph.add_edge("innovator_defense","fact_checker_r4")
    graph.add_edge("fact_checker_r4",  "chairman")

    # Conditional edge after Chairman
    graph.add_conditional_edges(
        "chairman",
        _ragas_router,
        {"retry": "retry_reset", "end": END},
    )

    # Retry loop: reset → back to start of debate
    graph.add_edge("retry_reset", "innovator")

    return graph.compile()


# Singleton compiled graph — built once on first import
_compiled_graph = None


def get_council_graph():
    """Returns the singleton compiled graph, building it on first call."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_council_graph()
    return _compiled_graph
