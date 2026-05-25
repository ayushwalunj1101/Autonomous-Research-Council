def compute_ragas_score(round_outputs: list[dict], citation_flags: list[dict]) -> float:
    """
    RAGAS Faithfulness Score = Supported Claims / Total Claims.

    Only Innovator claims count (Skeptic intentionally makes no citation-backed claims).
    'Supported' = claim has no hard CitationFlag against it.
    Soft flags count as supported — weak support is not the same as unsupported.

    Returns float in [0.0, 1.0].
    Returns 1.0 if no Innovator claims exist (nothing to fail).
    """
    # Collect all Innovator claims across all rounds
    innovator_claims: list[str] = []
    for output in round_outputs:
        if output.get("agent") == "Innovator":
            innovator_claims.extend(output.get("claims", []))

    if not innovator_claims:
        return 1.0

    # Build set of hard-flagged claim texts
    hard_flagged: set[str] = {
        f["claim"]
        for f in citation_flags
        if f.get("agent") == "Innovator" and f.get("severity") == "hard"
    }

    supported = sum(1 for c in innovator_claims if c not in hard_flagged)
    score = supported / len(innovator_claims)
    return round(score, 4)
