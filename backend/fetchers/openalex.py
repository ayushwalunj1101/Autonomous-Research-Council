"""OpenAlex (free, no key) — broad coverage of journals and conferences beyond arXiv."""

import os

from backend.fetchers.common import http_get, normalize_doi

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
_SELECT = "id,doi,display_name,publication_year,authorships,abstract_inverted_index,primary_location"


def _abstract_from_index(index: dict | None) -> str:
    """OpenAlex stores abstracts as {word: [positions]}; rebuild the text."""
    if not index:
        return ""
    positions: dict[int, str] = {}
    for word, spots in index.items():
        for spot in spots:
            positions[spot] = word
    return " ".join(positions[i] for i in sorted(positions))


def _to_paper(work: dict) -> dict | None:
    title = (work.get("display_name") or "").strip()
    abstract = _abstract_from_index(work.get("abstract_inverted_index"))
    if not title or not abstract:
        return None
    doi = normalize_doi(work.get("doi"))
    location = work.get("primary_location") or {}
    url = f"https://doi.org/{doi}" if doi else (location.get("landing_page_url") or work.get("id") or "")
    authors = [
        (a.get("author") or {}).get("display_name", "")
        for a in (work.get("authorships") or [])[:12]
    ]
    return {
        "title": title,
        "abstract": abstract,
        "authors": [a for a in authors if a],
        "url": url,
        "doi": doi,
        "year": work.get("publication_year"),
        "source": "openalex",
    }


def _params(extra: dict) -> dict:
    params = {"select": _SELECT, **extra}
    mailto = os.environ.get("OPENALEX_MAILTO", "").strip()
    if mailto:
        params["mailto"] = mailto  # joins OpenAlex's faster "polite pool"
    return params


def fetch_openalex_papers(keywords: list[str], max_results: int = 20) -> list[dict]:
    query = " ".join(k for k in keywords if k)
    if not query:
        return []
    resp = http_get(
        OPENALEX_WORKS_URL,
        params=_params({"search": query, "per-page": max_results, "filter": "has_abstract:true"}),
        timeout=20, label="OpenAlex",
    )
    if resp is None:
        return []
    papers = [_to_paper(w) for w in resp.json().get("results", []) or []]
    return [p for p in papers if p]


def fetch_openalex_by_doi(doi: str) -> dict | None:
    clean = normalize_doi(doi)
    if not clean:
        return None
    resp = http_get(f"{OPENALEX_WORKS_URL}/doi:{clean}", params=_params({}), timeout=20, label="OpenAlex")
    if resp is None:
        return None
    return _to_paper(resp.json())
