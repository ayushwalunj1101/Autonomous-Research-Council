import pytest

from backend.graph.council_graph import final_evaluation, initial_state, run_council
from backend.runtime import SessionCancelled, clear_session, request_cancel
from tests.conftest import FAKE_PAPERS

HYPOTHESIS = "Federated learning improves clinical prediction without sharing patient data."


def _state(session_id, **kw):
    return initial_state(session_id, 2, HYPOTHESIS, ["federated learning", "clinical prediction"],
                         domain="biomedical", **kw)


def test_full_debate_with_targeted_repair(seeded_session):
    final = run_council(_state(seeded_session))

    outputs = final["round_outputs"]
    labels = [(o["agent"], o["round"], o.get("stage", "debate")) for o in outputs]
    assert labels[:6] == [
        ("Innovator", 1, "debate"), ("Skeptic", 2, "debate"), ("Innovator", 3, "debate"),
        ("Skeptic", 3, "debate"), ("Innovator", 4, "debate"), ("Innovator", 4, "repair"),
    ]
    assert all(o.get("audited") for o in outputs), "every output is fact-checked exactly once"

    # Round 3 Innovator claims are now verified (there was no fact-checker after R3 before)
    assert any(a["round"] == 3 for a in final["claim_audits"])

    # Mock: 1 of 3 claims per Innovator turn is unsupported -> 6/9 = 0.667 -> repair -> pass
    history = final["attempt_history"]
    assert [round(h["ragas_score"], 3) for h in history] == [0.667, 1.0]
    assert final["retry_count"] == 1

    resolved = [f for f in final["citation_flags"] if f.get("resolved")]
    assert {f["resolved"] for f in resolved} == {"revised", "retracted"}

    ev = final_evaluation(final)
    assert ev["ragas_score"] == 1.0 and not ev["low_confidence_flag"]
    assert ev["chaos_constraint"] == "Assume GPU/compute budget is reduced by 50%."
    assert ev["score_samples"] == 3
    lo, hi = ev["score_ranges"]["novelty"]
    assert lo <= ev["novelty_score"] <= hi and lo < hi

    titles = {p["title"] for p in FAKE_PAPERS}
    assert ev["top_papers"] and all(p["title"] in titles for p in ev["top_papers"])
    assert ev["references_meta"] and all(m["title"] in titles for m in ev["references_meta"])
    assert all(r.startswith(("Author", "Paper")) for r in ev["references"])
    assert {"supported", "unsupported"} <= {a["verdict"] for a in ev["claim_audit"]}
    assert ev["signals"]["retracted"] >= 1 and ev["model"] == "mock"


def test_best_attempt_is_kept(seeded_session, monkeypatch):
    """If a repair lowers RAGAS, the report keeps the better earlier attempt."""
    from backend.agents import chairman

    scores = iter([0.6, 0.4])
    monkeypatch.setattr(chairman, "compute_ragas_score", lambda outputs, flags: next(scores))
    final = run_council(_state(seeded_session))
    # The repair resolved every flag, so the router stops: nothing left a second repair could change
    assert [h["ragas_score"] for h in final["attempt_history"]] == [0.6, 0.4]
    assert final["ragas_score"] == 0.4
    ev = final_evaluation(final)
    assert ev["ragas_score"] == 0.6 and ev["low_confidence_flag"]


def test_user_chaos_constraint_overrides_selection(seeded_session):
    final = run_council(_state(seeded_session, chaos_constraint_override="Assume a 3-month deadline."))
    assert final["chaos_constraint"] == "Assume a 3-month deadline."


def test_full_retry_mode_reruns_the_debate(seeded_session, monkeypatch):
    monkeypatch.setenv("ARC_RETRY_MODE", "full")
    from backend.agents import chairman
    from backend.config import reset_settings
    reset_settings()
    scores = iter([0.5, 0.9])
    monkeypatch.setattr(chairman, "compute_ragas_score", lambda outputs, flags: next(scores))
    final = run_council(_state(seeded_session))
    assert final["retry_count"] == 1
    assert not any(o.get("stage") == "repair" for o in final["round_outputs"])
    assert final_evaluation(final)["ragas_score"] == 0.9


def test_cancelled_session_stops(seeded_session):
    request_cancel(seeded_session)
    try:
        with pytest.raises(SessionCancelled):
            run_council(_state(seeded_session))
    finally:
        clear_session(seeded_session)


def test_similarity_claim_check_still_works(seeded_session, monkeypatch):
    monkeypatch.setenv("ARC_CLAIM_CHECK", "similarity")
    from backend.config import reset_settings
    reset_settings()
    final = run_council(_state(seeded_session))
    assert final["claim_audits"] and all(a["method"] == "similarity" for a in final["claim_audits"])


def test_identical_revision_leaves_the_flag_open(seeded_session, monkeypatch):
    """Review finding: a word-for-word 'revision' must not count as a repair."""
    from backend.agents import innovator

    flags = [{"claim": "Claim that stays the same.", "agent": "Innovator", "round": 1,
              "severity": "hard", "reason": "unsupported"}]

    def fake_chat_json(messages, **kwargs):
        return {"content": "Kept it.", "resolutions": [
            {"flag_id": 1, "action": "revise", "revised_claim": "Claim that stays the same", "paper_ids": [1]},
        ]}

    monkeypatch.setattr(innovator, "chat_json", fake_chat_json)
    patch = innovator.run_innovator_repair({
        "session_id": seeded_session, "hypothesis": "h", "retry_count": 1,
        "round_outputs": [], "citation_flags": flags,
    })
    assert not patch["citation_flags"][0].get("resolved")
    assert patch["round_outputs"][-1]["claims"] == []


def test_budget_hit_during_repair_keeps_the_finished_report(seeded_session, monkeypatch):
    """Review finding: BudgetExceeded mid-repair used to discard the paid-for first attempt."""
    from backend.agents import innovator
    from backend.graph import council_graph
    from backend.runtime import BudgetExceeded

    def over_budget(state):
        raise BudgetExceeded("Session cost limit reached")

    monkeypatch.setattr(innovator, "run_innovator_repair", over_budget)
    monkeypatch.setattr(council_graph, "_compiled_graph", None)  # rebuild with the patched node
    try:
        final = run_council(_state(seeded_session))
    finally:
        council_graph._compiled_graph = None
    ev = final_evaluation(final)
    assert final["retry_count"] == 1 and len(final["attempt_history"]) == 1
    assert ev["ragas_score"] == round(6 / 9, 4) and ev["low_confidence_flag"]


def test_supported_verdict_without_verbatim_quote_is_partial(seeded_session, monkeypatch):
    from backend.agents import fact_checker

    def fake_chat_json(messages, **kwargs):
        return {"verdicts": [
            {"claim_id": 1, "verdict": "supported", "paper_id": 1, "quote": "words that are not in any abstract", "reason": "r"},
            {"claim_id": 2, "verdict": "supported", "paper_id": 1, "quote": "results improve on standard benchmarks", "reason": "r"},
        ]}

    monkeypatch.setattr(fact_checker, "chat_json", fake_chat_json)
    state = {"session_id": seeded_session, "citation_flags": [], "claim_audits": []}
    output = {"agent": "Innovator", "round": 1, "claims": ["Claim one.", "Claim two."], "claim_citations": [[], []]}
    flags, records = fact_checker._audit_innovator_claims(state, output)
    assert [r["verdict"] for r in records] == ["partial", "supported"]
    assert [f["severity"] for f in flags] == ["soft"]
