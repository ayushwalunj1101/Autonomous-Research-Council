def _output_key(output: dict, claim: str) -> tuple:
    return (output.get("round"), output.get("stage") or "debate", output.get("attempt") or 0, claim)


def flag_key(flag: dict) -> tuple:
    """Identifies the exact claim occurrence a flag belongs to (round, stage, attempt, text)."""
    return (flag.get("round"), flag.get("stage") or "debate", flag.get("attempt") or 0, flag.get("claim"))


def compute_ragas_score(round_outputs: list[dict], citation_flags: list[dict]) -> float:
    """
    RAGAS Faithfulness Score = Supported Claims / Total Claims.

    Only Innovator claims count (Skeptic intentionally makes no citation-backed claims).
    'Supported' = claim has no unresolved hard CitationFlag against it.
    Soft flags count as supported — weak support is not the same as unsupported.
    A claim the Innovator revised or retracted in a repair round leaves the denominator;
    its revised version is counted (and fact-checked) as a new claim. Flags are matched to
    the exact claim occurrence (round, stage, attempt, text), so restating a flagged claim
    word-for-word in a repair round cannot erase its flag.

    Returns float in [0.0, 1.0].
    Returns 0.0 if no Innovator claims exist — making no verifiable claims must not pass.
    """
    innovator_flags = [f for f in citation_flags if f.get("agent") == "Innovator"]
    resolved = {flag_key(f) for f in innovator_flags if f.get("resolved")}
    hard_flagged = {
        flag_key(f) for f in innovator_flags if f.get("severity") == "hard" and not f.get("resolved")
    }

    standing = [
        key
        for output in round_outputs
        if output.get("agent") == "Innovator"
        for key in (_output_key(output, claim) for claim in output.get("claims", []))
        if key not in resolved
    ]
    if not standing:
        return 0.0

    supported = sum(1 for key in standing if key not in hard_flagged)
    return round(supported / len(standing), 4)
