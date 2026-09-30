"""
Helpers shared by the debate agents.

Agents never ask the LLM to copy titles or URLs: papers are shown as numbered entries
([1], [2], ...) and the model cites by number. Numbers are mapped back to ChromaDB
papers here, so citations cannot contain hallucinated titles or links. (12 of the 16
cut-off replies in the experiment logs stopped mid-way through copying an arXiv URL.)
"""

import re

from backend.llm.schemas import as_str, normalize_claims
from backend.llm.usage import session_cost
from backend.rag.chromadb_client import query_papers

ABSTRACT_CHARS = 900
# [2], [1, 3], [2; 4] — citation markers that refer to the numbered paper list of a prompt
_MARKER_RE = re.compile(r"\[(\d{1,2}(?:\s*[,;]\s*\d{1,2})*)\]")


def truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def summarize(content: str, limit: int = 150) -> str:
    return truncate(content, limit)


def retrieve(session_id: str, queries: list[str], k_each: int = 5, limit: int = 6) -> list[dict]:
    """Union of top-k results for several queries, in first-seen order, deduplicated by id."""
    papers: list[dict] = []
    seen: set[str] = set()
    for query in queries:
        if not query or not query.strip():
            continue
        for paper in query_papers(session_id, query, n_results=k_each):
            if paper["id"] not in seen:
                seen.add(paper["id"])
                papers.append(paper)
    return papers[:limit]


def paper_context(papers: list[dict], abstract_chars: int = ABSTRACT_CHARS) -> str:
    if not papers:
        return "(no papers were retrieved for this session)"
    blocks = []
    for i, p in enumerate(papers, 1):
        year = str(p.get("published") or "")[:4]
        meta = ", ".join(x for x in (year, p.get("source", "")) if x)
        blocks.append(
            f"[{i}] {p['title']}" + (f" ({meta})" if meta else "") +
            f"\nAbstract: {truncate(p.get('abstract', ''), abstract_chars)}"
        )
    return "\n\n".join(blocks)


def citation_record(paper: dict) -> dict:
    return {
        "paper_id": paper["id"],
        "title": paper.get("title", ""),
        "url": paper.get("url", ""),
        "relevance_score": paper.get("relevance_score", 0.0),
    }


def map_claims(turn: dict, papers: list[dict]) -> tuple[list[str], list[list[str]], list[dict]]:
    """
    Converts normalized {content, claims:[{text, paper_ids}]} into
    (claims, claim_citations, citations) using real paper ids.
    Out-of-range numbers are dropped; [n] markers in the prose also count as citations.
    """
    def resolve(numbers: list[int]) -> list[str]:
        return [papers[n - 1]["id"] for n in numbers if 1 <= n <= len(papers)]

    claims: list[str] = []
    claim_citations: list[list[str]] = []
    cited: list[str] = []
    for claim in turn.get("claims", []):
        ids = resolve(claim.get("paper_ids", []))
        claims.append(claim["text"])
        claim_citations.append(ids)
        cited.extend(ids)

    prose_numbers = [int(n) for m in _MARKER_RE.findall(turn.get("content", "")) for n in re.split(r"[,;]", m)]
    cited.extend(resolve(prose_numbers))

    by_id = {p["id"]: p for p in papers}
    citations, seen = [], set()
    for pid in cited:
        if pid not in seen and pid in by_id:
            seen.add(pid)
            citations.append(citation_record(by_id[pid]))
    return claims, claim_citations, citations


def paper_label(paper: dict) -> str:
    """Short, prompt-independent citation label such as 'Rieke 2020'."""
    authors = paper.get("authors") or ""
    first = (authors if isinstance(authors, str) else ", ".join(authors)).split(",")[0].strip()
    year = str(paper.get("published") or paper.get("year") or "")[:4]
    if first:
        return f"{first.split()[-1]} {year}".strip()
    words = (paper.get("title") or "untitled").split()
    return (" ".join(words[:4]) + ("…" if len(words) > 4 else "") + f" {year}").strip()


def resolve_markers(text: str, papers: list[dict]) -> str:
    """
    Rewrites [n] markers (numbers into this prompt's paper list) as [Author Year] labels.
    Each prompt numbers papers differently, so a raw [2] in text carried into later rounds
    or the Chairman's prompt would point at the wrong paper. Markers with a number outside
    the list (e.g. an interval like [0, 1]) are left untouched.
    """
    def replace(match: re.Match) -> str:
        numbers = [int(n) for n in re.split(r"[,;]", match.group(1))]
        if not all(1 <= n <= len(papers) for n in numbers):
            return match.group(0)
        return "[" + "; ".join(paper_label(papers[n - 1]) for n in numbers) + "]"
    return _MARKER_RE.sub(replace, text or "")


def unresolved_hard_flags(flags: list[dict], agent: str = "Innovator") -> list[dict]:
    return [f for f in flags if f.get("agent") == agent and f.get("severity") == "hard" and not f.get("resolved")]


def cost_so_far(session_id: str) -> float:
    return round(session_cost(session_id), 4)


def require_turn(item_name: str, count: str):
    """
    chat_json validator for debate turns: an argument with an empty claims list would
    escape fact-checking entirely (seen live: a Round 4 defense with 0 claims).
    """
    def validate(parsed: dict) -> str | None:
        if not as_str(parsed.get("content")):
            return "the 'content' field is empty"
        if not normalize_claims(parsed.get("claims")):
            return (f"the 'claims' list is empty - list every {item_name} your argument makes "
                    f"({count} items) as separate entries")
        return None
    return validate
