"""PubMed via NCBI E-utilities (no key needed; NCBI_API_KEY raises the rate limit)."""

import os
import xml.etree.ElementTree as ET

from backend.fetchers.common import http_get

_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _key_params() -> dict:
    key = os.environ.get("NCBI_API_KEY", "").strip()
    return {"api_key": key} if key and not key.startswith("your_") else {}


def _text(el) -> str:
    return "".join(el.itertext()).strip() if el is not None else ""


def _parse_articles(xml_text: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"[PubMed] XML parse error: {e}")
        return []

    papers = []
    for art in root.findall(".//PubmedArticle"):
        pmid = _text(art.find(".//MedlineCitation/PMID"))
        title = _text(art.find(".//Article/ArticleTitle"))
        parts = []
        for block in art.findall(".//Article/Abstract/AbstractText"):
            label = block.get("Label")
            body = _text(block)
            if body:
                parts.append(f"{label}: {body}" if label else body)
        abstract = " ".join(parts)
        authors = []
        for author in art.findall(".//Article/AuthorList/Author")[:12]:
            name = " ".join(x for x in (_text(author.find("ForeName")), _text(author.find("LastName"))) if x)
            if name:
                authors.append(name)
        year = _text(art.find(".//Article/Journal/JournalIssue/PubDate/Year"))
        doi = ""
        for aid in art.findall(".//PubmedData/ArticleIdList/ArticleId"):
            if aid.get("IdType") == "doi":
                doi = _text(aid)
        if title and abstract:
            papers.append({
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "doi": doi,
                "year": year,
                "source": "pubmed",
            })
    return papers


def fetch_pubmed_papers(keywords: list[str], max_results: int = 15) -> list[dict]:
    term = " AND ".join(f"({k})" for k in keywords[:3] if k)
    if not term:
        return []
    search = http_get(
        f"{_EUTILS}/esearch.fcgi",
        params={"db": "pubmed", "term": term, "retmax": max_results, "sort": "relevance",
                "retmode": "json", **_key_params()},
        timeout=20, label="PubMed",
    )
    if search is None:
        return []
    ids = (search.json().get("esearchresult") or {}).get("idlist") or []
    if not ids:
        return []
    fetch = http_get(
        f"{_EUTILS}/efetch.fcgi",
        params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml", **_key_params()},
        timeout=25, label="PubMed",
    )
    return _parse_articles(fetch.text) if fetch is not None else []
