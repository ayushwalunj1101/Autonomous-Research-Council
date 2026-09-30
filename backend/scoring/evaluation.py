"""
Builds and normalizes the Chairman's evaluation JSON — the single source of truth for
the report page, PDF and exports.

build_evaluation() merges the LLM's judgement with facts computed in code (references,
claim audit, score ranges, evidence signals), so nothing factual depends on the LLM
copying data correctly. normalize_evaluation() is idempotent and is applied again at
every read, so older or partial evaluations can never crash a consumer.
"""

from statistics import median
from typing import Any

from backend.llm.schemas import as_int, as_score, as_str, as_str_list
from backend.scoring.ragas_scorer import flag_key

SCORE_KEYS = ("novelty_score", "feasibility_score", "research_gap_score", "overall_confidence")
RATIONALE_KEYS = {
    "novelty_score": "novelty",
    "feasibility_score": "feasibility",
    "research_gap_score": "research_gap",
    "overall_confidence": "overall",
}
TOP_PAPERS = 5


def _authors_short(authors: Any) -> str:
    if isinstance(authors, list):
        names = [as_str(a) for a in authors if as_str(a)]
    else:
        names = [a.strip() for a in as_str(authors).split(",") if a.strip()]
    if not names:
        return ""
    return ", ".join(names[:3]) + (" et al." if len(names) > 3 else "")


def _authors_full(authors: Any) -> str:
    if isinstance(authors, list):
        return ", ".join(as_str(a) for a in authors if as_str(a))
    return as_str(authors)


def paper_meta(paper: dict) -> dict:
    return {
        "id": as_str(paper.get("id")),
        "title": as_str(paper.get("title")),
        "authors": _authors_short(paper.get("authors_full") or paper.get("authors")),
        "authors_full": _authors_full(paper.get("authors_full") or paper.get("authors")),
        "year": as_str(paper.get("published") or paper.get("year"))[:4],
        "url": as_str(paper.get("url")),
        "source": as_str(paper.get("source")),
        "doi": as_str(paper.get("doi")),
        "arxiv_id": as_str(paper.get("arxiv_id")),
        "relevance": round(float(paper.get("relevance_score") or paper.get("relevance") or 0.0), 1),
    }


def format_reference(meta: dict) -> str:
    parts = []
    if meta.get("authors"):
        parts.append(meta["authors"] + (f" ({meta['year']})." if meta.get("year") else "."))
    elif meta.get("year"):
        parts.append(f"({meta['year']}).")
    parts.append(meta.get("title", "").rstrip(".") + ".")
    if meta.get("url"):
        parts.append(meta["url"])
    return " ".join(p for p in parts if p.strip(". "))


def aggregate_scores(samples: list[dict]) -> tuple[dict[str, int], dict[str, list[int]]]:
    """Median and [min, max] of each score across Chairman samples."""
    scores: dict[str, int] = {}
    ranges: dict[str, list[int]] = {}
    for key in SCORE_KEYS:
        values = [v for v in (as_score(s.get(key)) for s in samples) if v is not None]
        if values:
            scores[key] = int(round(median(values)))
            ranges[key] = [min(values), max(values)]
        else:
            scores[key] = 0
            ranges[key] = [0, 0]
    return scores, ranges


def claim_audit(state: dict) -> list[dict]:
    """Claim verdict records with their repair-round resolution attached."""
    resolution = {
        flag_key(f): (f.get("resolved"), f.get("revised_to", ""))
        for f in state.get("citation_flags", [])
        if f.get("agent") == "Innovator" and f.get("resolved")
    }
    audit = []
    for record in state.get("claim_audits", []):
        key = (record.get("round"), record.get("stage") or "debate", record.get("attempt") or 0, record["claim"])
        resolved, revised_to = resolution.get(key, ("", ""))
        audit.append({**record, "resolved": resolved or "", "revised_to": revised_to or ""})
    return audit


def _cited_ids(state: dict) -> list[str]:
    ids: list[str] = []
    for output in state.get("round_outputs", []):
        for citation in output.get("citations", []):
            if citation.get("paper_id") and citation["paper_id"] not in ids:
                ids.append(citation["paper_id"])
    for record in state.get("claim_audits", []):
        if record.get("paper_id") and record["verdict"] in ("supported", "partial") and record["paper_id"] not in ids:
            ids.append(record["paper_id"])
    return ids


def build_signals(state: dict, papers: list[dict], audit: list[dict]) -> dict:
    relevances = [float(p.get("relevance_score") or 0) for p in papers]
    counts: dict[str, int] = {}
    for record in audit:
        if not record.get("resolved"):
            counts[record["verdict"]] = counts.get(record["verdict"], 0) + 1
    skeptic_claims = sum(len(o.get("claims", [])) for o in state.get("round_outputs", []) if o["agent"] == "Skeptic")
    return {
        "papers_total": len(papers),
        "nearest_paper_similarity": round(max(relevances, default=0.0), 1),
        "close_papers": sum(1 for r in relevances if r >= 60),
        "claims_total": len(audit),
        "verdict_counts": counts,
        "retracted": sum(1 for r in audit if r.get("resolved") == "retracted"),
        "revised": sum(1 for r in audit if r.get("resolved") == "revised"),
        "skeptic_objections": skeptic_claims,
        "fabrication_flags": sum(1 for f in state.get("citation_flags", []) if f.get("agent") == "Skeptic"),
    }


def build_evaluation(
    main: dict,
    samples: list[dict],
    *,
    state: dict,
    papers: list[dict],
    numbered_papers: list[dict],
    ragas_score: float,
    low_confidence_flag: bool,
    model: str,
) -> dict:
    """
    main: the Chairman's full reply; samples: every scoring reply (main included).
    numbered_papers: the paper list shown to the Chairman ([1]..[n]) for top_papers mapping.
    """
    scores, ranges = aggregate_scores(samples)
    by_id = {p["id"]: p for p in papers}
    audit = claim_audit(state)

    # References come from what was actually cited in the debate, never from LLM text
    cited = [by_id[i] for i in _cited_ids(state) if i in by_id]
    reference_papers = cited or sorted(papers, key=lambda p: p.get("relevance_score", 0), reverse=True)[:TOP_PAPERS]
    references_meta = [paper_meta(p) for p in reference_papers]

    top: list[dict] = []
    used: set[str] = set()
    for item in main.get("top_papers") or []:
        if not isinstance(item, dict):
            continue
        n = as_int(item.get("paper_id"))
        if n is None or not 1 <= n <= len(numbered_papers):
            continue
        paper = numbered_papers[n - 1]
        if paper["id"] in used:
            continue
        used.add(paper["id"])
        top.append({"paper_id": paper["id"], "title": paper["title"], "url": paper.get("url", ""),
                    "relevance_score": round(float(paper.get("relevance_score") or 0), 1),
                    "summary": as_str(item.get("summary"))})
    for paper in cited + sorted(papers, key=lambda p: p.get("relevance_score", 0), reverse=True):
        if len(top) >= TOP_PAPERS:
            break
        if paper["id"] not in used:
            used.add(paper["id"])
            top.append({"paper_id": paper["id"], "title": paper["title"], "url": paper.get("url", ""),
                        "relevance_score": round(float(paper.get("relevance_score") or 0), 1), "summary": ""})

    rationale_src = main.get("score_rationale") if isinstance(main.get("score_rationale"), dict) else {}
    evaluation = {
        **scores,
        "score_ranges": {RATIONALE_KEYS[k]: ranges[k] for k in SCORE_KEYS},
        "score_samples": len(samples),
        "score_rationale": {v: as_str(rationale_src.get(v)) for v in RATIONALE_KEYS.values()},
        "ragas_score": ragas_score,
        "low_confidence_flag": low_confidence_flag,
        "refined_hypothesis": as_str(main.get("refined_hypothesis")) or state.get("hypothesis", ""),
        "original_hypothesis": state.get("hypothesis", ""),
        "strengths": as_str_list(main.get("strengths")),
        "weaknesses": as_str_list(main.get("weaknesses")),
        "chaos_constraint": state.get("chaos_constraint") or "",
        "chaos_response_summary": as_str(main.get("chaos_response_summary")),
        "proposed_methodology": as_str_list(main.get("proposed_methodology")),
        "top_papers": top[:TOP_PAPERS],
        "references": [format_reference(m) for m in references_meta],
        "references_meta": references_meta,
        "claim_audit": audit,
        "signals": build_signals(state, papers, audit),
        "attempts": list(state.get("attempt_history", [])),
        "model": model,
    }
    return normalize_evaluation(evaluation)


def _as_range(value: Any, fallback: int) -> list[int]:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        lo, hi = as_score(value[0]), as_score(value[1])
        if lo is not None and hi is not None:
            return [min(lo, hi), max(lo, hi)]
    return [fallback, fallback]


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_evaluation(ev: dict | None) -> dict:
    """Coerces any evaluation dict into the full schema with safe types and defaults."""
    ev = dict(ev or {})
    out: dict[str, Any] = {}
    for key in SCORE_KEYS:
        out[key] = as_score(ev.get(key)) or 0

    ranges = ev.get("score_ranges") if isinstance(ev.get("score_ranges"), dict) else {}
    out["score_ranges"] = {
        RATIONALE_KEYS[k]: _as_range(ranges.get(RATIONALE_KEYS[k]), out[k]) for k in SCORE_KEYS
    }
    out["score_samples"] = as_int(ev.get("score_samples")) or 1
    rationale = ev.get("score_rationale") if isinstance(ev.get("score_rationale"), dict) else {}
    out["score_rationale"] = {v: as_str(rationale.get(v)) for v in RATIONALE_KEYS.values()}

    out["ragas_score"] = max(0.0, min(1.0, _as_float(ev.get("ragas_score"))))
    out["low_confidence_flag"] = bool(ev.get("low_confidence_flag", False))
    out["refined_hypothesis"] = as_str(ev.get("refined_hypothesis"))
    out["original_hypothesis"] = as_str(ev.get("original_hypothesis"))
    out["strengths"] = as_str_list(ev.get("strengths"))
    out["weaknesses"] = as_str_list(ev.get("weaknesses"))
    out["chaos_constraint"] = as_str(ev.get("chaos_constraint"))
    out["chaos_response_summary"] = as_str(ev.get("chaos_response_summary"))
    out["proposed_methodology"] = as_str_list(ev.get("proposed_methodology"))

    top = []
    for item in ev.get("top_papers") or []:
        if isinstance(item, dict):
            top.append({
                "paper_id": as_str(item.get("paper_id")),
                "title": as_str(item.get("title")),
                "url": as_str(item.get("url")),
                "relevance_score": round(_as_float(item.get("relevance_score")), 1),
                "summary": as_str(item.get("summary")),
            })
        elif as_str(item):
            top.append({"paper_id": "", "title": as_str(item), "url": "", "relevance_score": 0.0, "summary": ""})
    out["top_papers"] = [t for t in top if t["title"]][:TOP_PAPERS]

    out["references"] = as_str_list(ev.get("references"))
    out["references_meta"] = [paper_meta(m) for m in ev.get("references_meta") or [] if isinstance(m, dict)]

    audit = []
    for record in ev.get("claim_audit") or []:
        if not isinstance(record, dict) or not as_str(record.get("claim")):
            continue
        audit.append({
            "claim": as_str(record.get("claim")),
            "round": as_int(record.get("round")) or 0,
            "stage": as_str(record.get("stage")) or "debate",
            "verdict": as_str(record.get("verdict")) or "unsupported",
            "severity": as_str(record.get("severity")) or "none",
            "method": as_str(record.get("method")),
            "reason": as_str(record.get("reason")),
            "quote": as_str(record.get("quote")),
            "paper_id": as_str(record.get("paper_id")),
            "paper_title": as_str(record.get("paper_title")),
            "paper_url": as_str(record.get("paper_url")),
            "resolved": as_str(record.get("resolved")),
            "revised_to": as_str(record.get("revised_to")),
        })
    out["claim_audit"] = audit

    out["signals"] = ev.get("signals") if isinstance(ev.get("signals"), dict) else {}
    out["attempts"] = [a for a in ev.get("attempts") or [] if isinstance(a, dict)]
    out["model"] = as_str(ev.get("model"))
    out["cost_usd"] = round(_as_float(ev.get("cost_usd")), 4)
    return out
