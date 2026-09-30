import re
import time
import xml.etree.ElementTree as ET

from backend.fetchers.common import http_get

ARXIV_API_URL = "https://export.arxiv.org/api/query"
NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
# arXiv asks clients to wait 3 seconds between requests
_POLITE_DELAY_S = 3.0


def _term(keyword: str) -> str:
    kw = keyword.replace('"', "").strip()
    return f'all:"{kw}"' if " " in kw else f"all:{kw}"


def build_queries(keywords: list[str], broad: bool = False) -> list[str]:
    """
    Pairwise AND queries over the top keywords (multi-word keywords quoted as phrases).
    broad=True returns a single OR query over all keywords, used when strict queries find nothing.
    """
    kws = [k for k in keywords if k and k.strip()]
    if not kws:
        return []
    if broad or len(kws) == 1:
        return [" OR ".join(_term(k) for k in kws[:4])]
    queries = [f"{_term(kws[0])} AND {_term(kws[1])}"]
    if len(kws) > 2:
        queries.append(f"{_term(kws[0])} AND {_term(kws[2])}")
    return queries


def _parse_feed(xml_text: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"[ArXiv] XML parse error: {e}")
        return []

    papers = []
    for entry in root.findall("atom:entry", NS):
        title_el = entry.find("atom:title", NS)
        summary_el = entry.find("atom:summary", NS)
        id_el = entry.find("atom:id", NS)
        published_el = entry.find("atom:published", NS)
        doi_el = entry.find("arxiv:doi", NS)

        title = re.sub(r"\s+", " ", title_el.text).strip() if title_el is not None and title_el.text else ""
        abstract = re.sub(r"\s+", " ", summary_el.text).strip() if summary_el is not None and summary_el.text else ""
        arxiv_url = id_el.text.strip() if id_el is not None and id_el.text else ""
        arxiv_id = arxiv_url.split("/abs/")[-1] if "/abs/" in arxiv_url else arxiv_url
        published = published_el.text.strip()[:10] if published_el is not None and published_el.text else ""

        authors = [
            author.find("atom:name", NS).text.strip()
            for author in entry.findall("atom:author", NS)
            if author.find("atom:name", NS) is not None
        ]

        if title and abstract and title.lower() != "error":
            papers.append(
                {
                    "title": title,
                    "abstract": abstract,
                    "authors": authors,
                    "url": arxiv_url.replace("http://", "https://"),
                    "arxiv_id": arxiv_id,
                    "doi": doi_el.text.strip() if doi_el is not None and doi_el.text else "",
                    "published": published,
                    "year": published[:4],
                    "source": "arxiv",
                }
            )
    return papers


def fetch_arxiv_papers(keywords: list[str], max_results: int = 15, broad: bool = False) -> list[dict]:
    """
    Queries the arXiv API (no key required) with one or more keyword queries.

    Returns list of paper dicts with keys:
        title, abstract, authors, url, arxiv_id, doi, published, year, source
    """
    papers: list[dict] = []
    for i, query in enumerate(build_queries(keywords, broad=broad)):
        if i:
            time.sleep(_POLITE_DELAY_S)
        params = {
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        resp = http_get(ARXIV_API_URL, params=params, timeout=25, label="ArXiv")
        if resp is not None:
            papers.extend(_parse_feed(resp.text))
    return papers


def fetch_arxiv_by_id(arxiv_id: str) -> dict | None:
    """Fetches one paper by arXiv id (e.g. 2401.01234 or https://arxiv.org/abs/2401.01234v2)."""
    match = re.search(r"(\d{4}\.\d{4,5}(v\d+)?|[a-z\-]+(\.[A-Z]{2})?/\d{7}(v\d+)?)", arxiv_id)
    if not match:
        return None
    resp = http_get(ARXIV_API_URL, params={"id_list": match.group(1)}, timeout=25, label="ArXiv")
    if resp is None:
        return None
    papers = _parse_feed(resp.text)
    return papers[0] if papers else None
