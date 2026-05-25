from backend.fetchers.arxiv_fetcher import fetch_arxiv_papers
from backend.fetchers.semantic_scholar import (
    fetch_semantic_scholar_papers,
    merge_and_deduplicate,
)
from backend.rag.chromadb_client import collection_exists, store_papers
from backend.sse.event_emitter import emit

MAX_PER_SOURCE = 10
MAX_TOTAL = 20


def run_librarian(context_packet: dict) -> dict:
    """
    Orchestrates paper fetching from ArXiv + Semantic Scholar and
    stores results in the session-namespaced ChromaDB collection.

    Skips API calls if the session collection already has papers (cache hit).

    Args:
        context_packet: output from run_orchestrator — must contain
                        'session_id' and 'keywords'

    Returns:
        {
            "session_id": str,
            "papers_loaded": int,
            "reused_cache": bool
        }
    """
    session_id: str = context_packet["session_id"]
    keywords: list[str] = context_packet["keywords"]

    # Cache check — reuse existing collection within the same session
    if collection_exists(session_id):
        print(f"[Librarian] Cache hit for session {session_id} — skipping API calls.")
        return {
            "session_id": session_id,
            "papers_loaded": 0,
            "reused_cache": True,
        }

    print(f"[Librarian] Fetching papers for keywords: {keywords}")

    arxiv_papers = fetch_arxiv_papers(keywords, max_results=MAX_PER_SOURCE)
    print(f"[Librarian] ArXiv: {len(arxiv_papers)} papers fetched.")

    ss_papers = fetch_semantic_scholar_papers(keywords, max_results=MAX_PER_SOURCE)
    print(f"[Librarian] Semantic Scholar: {len(ss_papers)} papers fetched.")

    papers = merge_and_deduplicate(arxiv_papers, ss_papers, max_total=MAX_TOTAL)
    print(f"[Librarian] Merged & deduplicated: {len(papers)} papers.")

    store_papers(session_id, papers)
    print(f"[Librarian] Stored {len(papers)} papers in ChromaDB collection '{session_id}'.")

    emit(session_id, "papers_loaded", {"count": len(papers)})

    return {
        "session_id": session_id,
        "papers_loaded": len(papers),
        "reused_cache": False,
    }
