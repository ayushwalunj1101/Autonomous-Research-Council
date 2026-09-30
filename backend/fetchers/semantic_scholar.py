from backend.config import env_secret
from backend.fetchers.common import http_get
from backend.fetchers.common import merge_and_deduplicate as _merge

S2_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
S2_FIELDS = "title,abstract,authors,year,externalIds,url"


def fetch_semantic_scholar_papers(keywords: list[str], max_results: int = 10) -> list[dict]:
    """
    Queries the Semantic Scholar public API.

    The API key is only sent when SEMANTIC_SCHOLAR_API_KEY holds a real value — the
    .env.example placeholder used to be sent verbatim, which S2 rejects with 403.
    Unauthenticated requests share a global rate limit, so 429s are retried once.

    Returns list of paper dicts with keys:
        title, abstract, authors, url, paper_id, doi, arxiv_id, year, source
    """
    query = " ".join(keywords)
    headers = {}
    api_key = env_secret("SEMANTIC_SCHOLAR_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key

    params = {
        "query": query,
        "limit": max_results,
        "fields": S2_FIELDS,
    }

    resp = http_get(S2_SEARCH_URL, params=params, headers=headers, timeout=15,
                    retries=1, backoff_s=2.0, label="S2")
    if resp is None:
        return []

    data = resp.json().get("data", []) or []
    papers = []
    for item in data:
        title = item.get("title") or ""
        abstract = item.get("abstract") or ""
        year = item.get("year")
        paper_id = item.get("paperId") or ""

        authors = [a.get("name", "") for a in item.get("authors", []) or []]

        # Prefer DOI URL, fall back to S2 URL
        external = item.get("externalIds") or {}
        doi = external.get("DOI") or ""
        url = f"https://doi.org/{doi}" if doi else f"https://www.semanticscholar.org/paper/{paper_id}"

        if title and abstract:
            papers.append(
                {
                    "title": title,
                    "abstract": abstract,
                    "authors": authors,
                    "url": url,
                    "paper_id": paper_id,
                    "doi": doi,
                    "arxiv_id": external.get("ArXiv") or "",
                    "year": year,
                    "source": "semantic_scholar",
                }
            )

    return papers


def merge_and_deduplicate(arxiv_papers: list[dict], ss_papers: list[dict], max_total: int = 20) -> list[dict]:
    """Backwards-compatible wrapper around fetchers.common.merge_and_deduplicate."""
    return _merge(arxiv_papers, ss_papers, max_total=max_total)
