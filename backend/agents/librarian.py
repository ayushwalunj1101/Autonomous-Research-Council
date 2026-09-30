import re
from concurrent.futures import ThreadPoolExecutor

from backend.fetchers.arxiv_fetcher import fetch_arxiv_by_id, fetch_arxiv_papers
from backend.fetchers.common import merge_and_deduplicate
from backend.fetchers.documents import paper_from_upload
from backend.fetchers.openalex import fetch_openalex_by_doi, fetch_openalex_papers
from backend.fetchers.pubmed import fetch_pubmed_papers
from backend.fetchers.semantic_scholar import fetch_semantic_scholar_papers
from backend.rag.chromadb_client import collection_exists, list_papers, store_papers
from backend.rag.embedder import cosine_scores
from backend.runtime import NoPapersFound
from backend.sse.event_emitter import emit

MAX_TOTAL = 20
# Candidates below this similarity to the hypothesis are dropped (unless too few remain)
MIN_RELEVANCE = 20.0
MIN_KEEP = 5

_BIOMEDICAL = re.compile(r"biomed|medic|clinic|health|biolog|pharma|neuro|genom|life scien|psychiat|epidem|oncolog", re.I)


def _is_biomedical(domain: str, keywords: list[str]) -> bool:
    return bool(_BIOMEDICAL.search(domain or "") or any(_BIOMEDICAL.search(k) for k in keywords))


def _fetch_all(keywords: list[str], domain: str, broad: bool = False) -> dict[str, list[dict]]:
    """Queries all sources in parallel. broad=True loosens every query (used after an empty result)."""
    kws = keywords[:2] if broad else keywords
    jobs = {
        "arxiv": lambda: fetch_arxiv_papers(keywords, max_results=15, broad=broad),
        "openalex": lambda: fetch_openalex_papers(kws, max_results=20),
        "semantic_scholar": lambda: fetch_semantic_scholar_papers(kws, max_results=10),
    }
    if _is_biomedical(domain, keywords):
        jobs["pubmed"] = lambda: fetch_pubmed_papers(kws, max_results=15)

    results: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {name: pool.submit(job) for name, job in jobs.items()}
        for name, future in futures.items():
            try:
                results[name] = future.result()
            except Exception as exc:  # one broken source must not sink retrieval
                print(f"[Librarian] {name} failed: {exc}")
                results[name] = []
    return results


def _rerank(papers: list[dict], hypothesis: str, keywords: list[str]) -> list[dict]:
    """Scores every candidate against the hypothesis and keeps the best MAX_TOTAL."""
    query = f"{hypothesis} {' '.join(keywords)}".strip()
    texts = [f"{p['title']}. {(p.get('abstract') or '')[:1200]}" for p in papers]
    for paper, score in zip(papers, cosine_scores(query, texts)):
        paper["relevance"] = score
    ranked = sorted(papers, key=lambda p: p["relevance"], reverse=True)
    kept = [p for p in ranked if p["relevance"] >= MIN_RELEVANCE]
    if len(kept) < MIN_KEEP:
        kept = ranked[:MIN_KEEP]
    return kept[:MAX_TOTAL]


def paper_summary(paper: dict) -> dict:
    """Compact paper record for the UI / SSE."""
    authors = paper.get("authors") or ""
    if isinstance(authors, list):
        authors = ", ".join(authors)
    names = [a.strip() for a in authors.split(",") if a.strip()]
    short = ", ".join(names[:3]) + (" et al." if len(names) > 3 else "")
    return {
        "id": paper.get("id", ""),
        "title": paper.get("title", ""),
        "authors": short,
        "year": str(paper.get("published") or paper.get("year") or "")[:4],
        "source": paper.get("source", ""),
        "url": paper.get("url", ""),
        "relevance": round(float(paper.get("relevance_score", paper.get("relevance", 0)) or 0), 1),
        "user_added": bool(paper.get("user_added", False)),
    }


def run_librarian(context_packet: dict, awaiting_review: bool = False) -> dict:
    """
    Fetches papers from arXiv, OpenAlex, Semantic Scholar (and PubMed for biomedical topics),
    reranks them against the hypothesis and stores the best 20 in the session's ChromaDB
    collection. Retries once with broader queries; raises NoPapersFound if still empty.

    Returns:
        {"session_id", "papers_loaded", "reused_cache", "papers", "sources"}
    """
    session_id: str = context_packet["session_id"]
    keywords: list[str] = context_packet["keywords"]
    hypothesis: str = context_packet.get("hypothesis", "")
    domain: str = context_packet.get("domain", "")

    if collection_exists(session_id):
        print(f"[Librarian] Cache hit for session {session_id} - skipping API calls.")
        papers = list_papers(session_id)
        emit(session_id, "papers_loaded", {
            "count": len(papers), "papers": [paper_summary(p) for p in papers],
            "sources": {}, "reused_cache": True, "awaiting_review": awaiting_review,
        })
        return {"session_id": session_id, "papers_loaded": len(papers), "reused_cache": True,
                "papers": papers, "sources": {}}

    print(f"[Librarian] Fetching papers for keywords: {keywords}")
    results = _fetch_all(keywords, domain)
    candidates = merge_and_deduplicate(*results.values())

    if not candidates:
        print("[Librarian] No papers found - retrying with broader queries.")
        results = _fetch_all(keywords, domain, broad=True)
        candidates = merge_and_deduplicate(*results.values())

    if not candidates:
        raise NoPapersFound(
            "No papers were found for these keywords (all sources returned nothing or were unreachable). "
            "Try broader or differently worded keywords."
        )

    papers = _rerank(candidates, hypothesis, keywords)
    store_papers(session_id, papers)
    stored = list_papers(session_id)

    sources: dict[str, int] = {}
    for p in stored:
        sources[p["source"]] = sources.get(p["source"], 0) + 1
    print(f"[Librarian] {len(candidates)} candidates -> kept {len(stored)} papers {sources}.")

    emit(session_id, "papers_loaded", {
        "count": len(stored),
        "papers": [paper_summary(p) for p in stored],
        "sources": sources,
        "candidates": len(candidates),
        "reused_cache": False,
        "awaiting_review": awaiting_review,
    })

    return {
        "session_id": session_id,
        "papers_loaded": len(stored),
        "reused_cache": False,
        "papers": stored,
        "sources": sources,
    }


# --------------------------------------------------------------------------- #
# User curation (paper review step)
# --------------------------------------------------------------------------- #

_ARXIV_ID_RE = re.compile(r"arxiv|^\s*\d{4}\.\d{4,5}(v\d+)?\s*$", re.I)
_DOI_RE = re.compile(r"10\.\d{4,9}/\S+")


def _ensure_capacity(session_id: str) -> None:
    if len(list_papers(session_id)) >= MAX_TOTAL:
        raise ValueError(
            f"Sessions hold at most {MAX_TOTAL} papers. Untick a paper first - unticked papers are dropped when you add one."
        )


def _store_user_paper(session_id: str, paper: dict, hypothesis: str) -> dict:
    paper["relevance"] = cosine_scores(hypothesis or paper["title"], [f"{paper['title']}. {paper.get('abstract', '')}"])[0]
    paper["user_added"] = True
    [pid] = store_papers(session_id, [paper])
    return paper_summary({**paper, "id": pid, "relevance_score": paper["relevance"]})


def add_paper_by_identifier(session_id: str, identifier: str, hypothesis: str) -> dict:
    """Adds a paper by arXiv id/URL or DOI. Raises ValueError with a user-facing message."""
    _ensure_capacity(session_id)
    identifier = identifier.strip()
    paper = None
    if _ARXIV_ID_RE.search(identifier):
        paper = fetch_arxiv_by_id(identifier)
    elif _DOI_RE.search(identifier):
        paper = fetch_openalex_by_doi(_DOI_RE.search(identifier).group())
    else:
        raise ValueError("Enter an arXiv ID (e.g. 2401.01234) or a DOI (e.g. 10.1038/s41586-021-03819-2).")
    if not paper:
        raise ValueError(f"No paper with an abstract was found for '{identifier}'.")
    return _store_user_paper(session_id, paper, hypothesis)


def add_uploaded_paper(session_id: str, filename: str, data: bytes, hypothesis: str) -> dict:
    """Adds a user-uploaded PDF as a paper (title = first line, abstract section if present)."""
    _ensure_capacity(session_id)
    return _store_user_paper(session_id, paper_from_upload(filename, data), hypothesis)
