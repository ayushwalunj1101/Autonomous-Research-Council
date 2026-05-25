import os

import requests

S2_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
S2_FIELDS = "title,abstract,authors,year,externalIds,url"


def fetch_semantic_scholar_papers(keywords: list[str], max_results: int = 10) -> list[dict]:
    """
    Queries Semantic Scholar public API.

    Returns list of paper dicts with keys:
        title, abstract, authors, url, paper_id, year, source
    """
    query = " ".join(keywords)
    headers = {}
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key

    params = {
        "query": query,
        "limit": max_results,
        "fields": S2_FIELDS,
    }

    try:
        response = requests.get(S2_SEARCH_URL, params=params, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[S2] Request failed: {e}")
        return []

    data = response.json().get("data", [])
    papers = []
    for item in data:
        title = item.get("title") or ""
        abstract = item.get("abstract") or ""
        year = item.get("year")
        paper_id = item.get("paperId") or ""

        authors = [a.get("name", "") for a in item.get("authors", [])]

        # Prefer DOI URL, fall back to S2 URL
        external = item.get("externalIds") or {}
        doi = external.get("DOI")
        url = f"https://doi.org/{doi}" if doi else f"https://www.semanticscholar.org/paper/{paper_id}"

        if title and abstract:
            papers.append(
                {
                    "title": title,
                    "abstract": abstract,
                    "authors": authors,
                    "url": url,
                    "paper_id": paper_id,
                    "year": year,
                    "source": "semantic_scholar",
                }
            )

    return papers


def merge_and_deduplicate(
    arxiv_papers: list[dict],
    ss_papers: list[dict],
    max_total: int = 20,
) -> list[dict]:
    """
    Merges both paper lists. Deduplicates by lowercased normalized title.
    ArXiv papers take priority. Caps result at max_total (20 per plan).
    """
    seen_titles: set[str] = set()
    merged: list[dict] = []

    for paper in arxiv_papers + ss_papers:
        normalized = _normalize_title(paper.get("title", ""))
        if normalized and normalized not in seen_titles:
            seen_titles.add(normalized)
            merged.append(paper)
        if len(merged) >= max_total:
            break

    return merged


def _normalize_title(title: str) -> str:
    """Lowercase + strip punctuation for deduplication."""
    import re
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()
