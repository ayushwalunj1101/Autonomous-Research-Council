"""Shared helpers for paper fetchers: HTTP with retry, dedup, title normalisation."""

import re
import time

import requests

USER_AGENT = "AutonomousResearchCouncil/1.0 (academic research prototype)"
_ARXIV_VERSION_RE = re.compile(r"v\d+$")


def http_get(url: str, *, params: dict | None = None, headers: dict | None = None,
             timeout: float = 20.0, retries: int = 1, backoff_s: float = 3.0,
             label: str = "HTTP") -> requests.Response | None:
    """GET with one retry on timeouts, 429 and 5xx. Returns None on failure (logged)."""
    merged = {"User-Agent": USER_AGENT, **(headers or {})}
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, params=params, headers=merged, timeout=timeout)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"{resp.status_code} from {label}", response=resp)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            retryable = status is None or status == 429 or status >= 500
            if attempt < retries and retryable:
                time.sleep(backoff_s * (attempt + 1))
                continue
            print(f"[{label}] Request failed: {exc}")
            return None
    return None


def normalize_title(title: str) -> str:
    """Lowercase + strip punctuation for deduplication."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", (title or "").lower())).strip()


def normalize_doi(doi: str | None) -> str:
    if not doi:
        return ""
    return re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", doi.strip(), flags=re.I).lower()


def merge_and_deduplicate(*paper_lists: list[dict], max_total: int | None = None) -> list[dict]:
    """
    Merges paper lists in priority order. Deduplicates by DOI, arXiv id and normalized title.
    """
    seen: set[str] = set()
    merged: list[dict] = []
    for papers in paper_lists:
        for paper in papers:
            keys = {f"t:{normalize_title(paper.get('title', ''))}"}
            if paper.get("doi"):
                keys.add(f"d:{normalize_doi(paper['doi'])}")
            if paper.get("arxiv_id"):
                keys.add("a:" + _ARXIV_VERSION_RE.sub("", paper["arxiv_id"]))
            keys.discard("t:")
            if not keys or keys & seen:
                continue
            seen |= keys
            merged.append(paper)
            if max_total is not None and len(merged) >= max_total:
                return merged
    return merged
