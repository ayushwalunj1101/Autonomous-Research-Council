from backend.llm.schemas import as_score, as_str, as_str_list, normalize_claims, normalize_debate_turn
from backend.scoring.evaluation import aggregate_scores, format_reference, normalize_evaluation
from backend.scoring.ragas_scorer import compute_ragas_score


def test_as_score_accepts_common_llm_formats():
    assert as_score(80) == 80
    assert as_score("80") == 80
    assert as_score("80/100") == 80
    assert as_score("8/10") == 80
    assert as_score("85%") == 85
    assert as_score(0.75) == 75
    assert as_score(150) == 100
    assert as_score(-3) == 0
    assert as_score("N/A") is None
    assert as_score(None) is None
    assert as_score(True) is None


def test_as_str_handles_lists_and_dicts():
    assert as_str(["para one", "para two"]) == "para one\n\npara two"
    assert as_str({"text": "claim"}) == "claim"
    assert as_str(None) == ""


def test_as_str_list_splits_bullets():
    assert as_str_list("- one\n- two\n3. three") == ["one", "two", "three"]
    assert as_str_list([{"description": "a"}, "b", ""]) == ["a", "b"]


def test_normalize_claims_variants():
    claims = normalize_claims([
        "Plain claim [Paper 2].",
        {"claim": "Dict claim", "papers": ["3", 4]},
        {"text": "Standard", "paper_ids": [1]},
    ])
    assert claims[0] == {"text": "Plain claim [Paper 2].", "paper_ids": [2]}
    assert claims[1]["paper_ids"] == [3, 4]
    assert claims[2]["paper_ids"] == [1]
    # A single string (what made the Fact-Checker iterate characters) becomes a list
    assert [c["text"] for c in normalize_claims("- first\n- second")] == ["first", "second"]


def test_normalize_debate_turn_with_list_content():
    turn = normalize_debate_turn({"content": ["p1", "p2"], "claims": "only one"})
    assert turn["content"] == "p1\n\np2"
    assert turn["claims"] == [{"text": "only one", "paper_ids": []}]


def test_normalize_evaluation_fills_every_field():
    ev = normalize_evaluation({})
    for key in ("novelty_score", "strengths", "weaknesses", "proposed_methodology", "references",
                "top_papers", "claim_audit", "score_ranges", "ragas_score", "low_confidence_flag"):
        assert key in ev
    assert ev["strengths"] == [] and ev["novelty_score"] == 0
    assert ev["score_ranges"]["novelty"] == [0, 0]


def test_normalize_evaluation_coerces_odd_types():
    ev = normalize_evaluation({
        "novelty_score": "80", "feasibility_score": 7.2, "strengths": "- a\n- b",
        "top_papers": ["Just a title", {"title": "T", "relevance_score": "71.5"}],
        "proposed_methodology": [{"step": "Step 1: Do it"}], "ragas_score": "0.9",
        "claim_audit": [{"claim": "c", "round": "1"}, "junk"],
    })
    assert ev["novelty_score"] == 80 and ev["feasibility_score"] == 7
    assert ev["strengths"] == ["a", "b"]
    assert ev["top_papers"][0]["title"] == "Just a title"
    assert ev["top_papers"][1]["relevance_score"] == 71.5
    assert ev["proposed_methodology"] == ["Step 1: Do it"]
    assert ev["ragas_score"] == 0.9
    assert len(ev["claim_audit"]) == 1 and ev["claim_audit"][0]["round"] == 1


def test_normalize_is_idempotent():
    once = normalize_evaluation({"novelty_score": "75", "strengths": "x"})
    assert normalize_evaluation(once) == once


def test_aggregate_scores_median_and_range():
    scores, ranges = aggregate_scores([
        {"novelty_score": 60, "feasibility_score": "70"},
        {"novelty_score": 80, "feasibility_score": 70},
        {"novelty_score": 70, "feasibility_score": None},
    ])
    assert scores["novelty_score"] == 70 and ranges["novelty_score"] == [60, 80]
    assert scores["feasibility_score"] == 70 and ranges["feasibility_score"] == [70, 70]
    assert scores["overall_confidence"] == 0


def test_format_reference():
    ref = format_reference({"authors": "A, B", "year": "2021", "title": "A study.", "url": "https://x"})
    assert ref == "A, B (2021). A study. https://x"


def _inn(claims, round_num=1):
    return {"agent": "Innovator", "round": round_num, "claims": claims}


def test_ragas_zero_claims_is_zero_not_one():
    assert compute_ragas_score([], []) == 0.0
    assert compute_ragas_score([{"agent": "Skeptic", "round": 2, "claims": ["x"]}], []) == 0.0


def test_ragas_hard_flags_count_soft_do_not():
    outputs = [_inn(["a", "b", "c", "d"])]
    flags = [
        {"claim": "a", "agent": "Innovator", "round": 1, "severity": "hard"},
        {"claim": "b", "agent": "Innovator", "round": 1, "severity": "soft"},
    ]
    assert compute_ragas_score(outputs, flags) == 0.75


def test_ragas_resolved_claims_leave_the_denominator():
    outputs = [_inn(["a", "b", "c", "d"]), {**_inn(["a-revised"], 4), "stage": "repair", "attempt": 1}]
    flags = [
        {"claim": "a", "agent": "Innovator", "round": 1, "severity": "hard", "resolved": "revised"},
        {"claim": "b", "agent": "Innovator", "round": 1, "severity": "hard", "resolved": "retracted"},
        {"claim": "c", "agent": "Innovator", "round": 1, "severity": "hard"},
    ]
    # standing claims: c (unsupported), d, a-revised -> 2/3
    assert compute_ragas_score(outputs, flags) == round(2 / 3, 4)


def test_ragas_restating_a_claim_cannot_erase_its_flag():
    # Review finding: a word-for-word "revision" used to leave the denominator with the original
    outputs = [_inn(["x", "y"]), {**_inn(["x"], 4), "stage": "repair", "attempt": 1}]
    flags = [
        {"claim": "x", "agent": "Innovator", "round": 1, "severity": "hard", "resolved": "revised"},
        {"claim": "x", "agent": "Innovator", "round": 4, "stage": "repair", "attempt": 1, "severity": "hard"},
    ]
    assert compute_ragas_score(outputs, flags) == 0.5  # y supported, repair x still unsupported


def test_ragas_retracting_a_repair_claim_removes_it():
    outputs = [_inn(["x", "y"]), {**_inn(["x2"], 4), "stage": "repair", "attempt": 1}]
    flags = [
        {"claim": "x", "agent": "Innovator", "round": 1, "severity": "hard", "resolved": "revised"},
        {"claim": "x2", "agent": "Innovator", "round": 4, "stage": "repair", "attempt": 1,
         "severity": "hard", "resolved": "retracted"},
    ]
    assert compute_ragas_score(outputs, flags) == 1.0  # only y stands


def test_citation_markers_become_author_year_labels():
    from backend.agents.common import map_claims, resolve_markers

    papers = [{"id": "s_0", "title": "FL for EHR", "authors": "Stephen Pfohl, Andrew Dai", "published": "2019-11-01"},
              {"id": "s_1", "title": "Digital health and FL", "authors": "", "year": 2020}]
    assert resolve_markers("see [1] and [1, 2]", papers) == "see [Pfohl 2019] and [Pfohl 2019; Digital health and FL 2020]"
    assert resolve_markers("interval [0, 1] and [9]", papers) == "interval [0, 1] and [9]"
    cited = map_claims({"content": "as in [1; 2]", "claims": []}, papers)[2]
    assert [c["paper_id"] for c in cited] == ["s_0", "s_1"]
