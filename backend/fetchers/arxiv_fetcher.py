import urllib.parse
import xml.etree.ElementTree as ET

import requests

ARXIV_API_URL = "http://export.arxiv.org/api/query"
NS = {"atom": "http://www.w3.org/2005/Atom"}


def fetch_arxiv_papers(keywords: list[str], max_results: int = 10) -> list[dict]:
    """
    Queries ArXiv API (no key required). Parses Atom XML response.

    Returns list of paper dicts with keys:
        title, abstract, authors, url, arxiv_id, published, source
    """
    # Use top 2 keywords with AND; more keywords make the query too restrictive
    top_kws = keywords[:2]
    query = " AND ".join(f'all:{kw}' for kw in top_kws)
    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }

    try:
        response = requests.get(ARXIV_API_URL, params=params, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[ArXiv] Request failed: {e}")
        return []

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError as e:
        print(f"[ArXiv] XML parse error: {e}")
        return []

    papers = []
    for entry in root.findall("atom:entry", NS):
        title_el = entry.find("atom:title", NS)
        summary_el = entry.find("atom:summary", NS)
        id_el = entry.find("atom:id", NS)
        published_el = entry.find("atom:published", NS)

        title = title_el.text.strip() if title_el is not None else ""
        abstract = summary_el.text.strip() if summary_el is not None else ""
        arxiv_url = id_el.text.strip() if id_el is not None else ""
        arxiv_id = arxiv_url.split("/abs/")[-1] if "/abs/" in arxiv_url else arxiv_url
        published = published_el.text.strip()[:10] if published_el is not None else ""

        authors = [
            author.find("atom:name", NS).text.strip()
            for author in entry.findall("atom:author", NS)
            if author.find("atom:name", NS) is not None
        ]

        if title and abstract:
            papers.append(
                {
                    "title": title,
                    "abstract": abstract,
                    "authors": authors,
                    "url": arxiv_url,
                    "arxiv_id": arxiv_id,
                    "published": published,
                    "source": "arxiv",
                }
            )

    return papers
