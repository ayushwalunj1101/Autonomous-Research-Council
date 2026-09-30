import threading
import uuid

import chromadb
from chromadb.config import Settings

from backend.config import get_settings
from backend.rag.embedder import embed_texts

_client: chromadb.ClientAPI | None = None
_client_lock = threading.Lock()


def get_client() -> chromadb.ClientAPI:
    """Returns singleton persistent ChromaDB client."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = chromadb.PersistentClient(
                    path=get_settings().chroma_path,
                    settings=Settings(anonymized_telemetry=False),
                )
    return _client


def _collection_name(session_id: str) -> str:
    return f"session_{session_id}"


def _get_collection(session_id: str):
    try:
        return get_client().get_collection(_collection_name(session_id))
    except Exception:
        return None


def collection_exists(session_id: str) -> bool:
    """Returns True if the session collection already has documents."""
    col = _get_collection(session_id)
    return bool(col and col.count() > 0)


def store_papers(session_id: str, papers: list[dict]) -> list[str]:
    """
    Embeds title + abstract for each paper and stores it in the session-namespaced
    ChromaDB collection. The initial batch gets ids {session_id}_0..n; papers added
    later get random suffixes, so an id is never reused after a paper is removed.
    Returns the ids assigned.
    """
    if not papers:
        return []

    col = get_client().get_or_create_collection(
        name=_collection_name(session_id),
        metadata={"hnsw:space": "cosine"},
    )

    if col.count() == 0:
        ids = [f"{session_id}_{i}" for i in range(len(papers))]
    else:
        ids = [f"{session_id}_u{uuid.uuid4().hex[:10]}" for _ in papers]
    texts = [f"{p['title']}. {p.get('abstract', '')}" for p in papers]
    embeddings = embed_texts(texts)

    metadatas = [
        {
            "title": p.get("title", ""),
            "authors": ", ".join(p.get("authors", [])) if isinstance(p.get("authors"), list) else str(p.get("authors") or ""),
            "url": p.get("url", ""),
            "source": p.get("source", ""),
            "published": str(p.get("published") or p.get("year") or ""),
            "doi": p.get("doi") or "",
            "arxiv_id": p.get("arxiv_id") or "",
            "relevance": float(p.get("relevance") or 0.0),
            "user_added": bool(p.get("user_added", False)),
        }
        for p in papers
    ]
    documents = [p.get("abstract") or p.get("title", "") for p in papers]

    col.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
    return ids


def _paper_from(pid: str, meta: dict, document: str, relevance: float | None = None) -> dict:
    return {
        "id": pid,
        "title": meta.get("title", ""),
        "abstract": document or "",
        "authors": meta.get("authors", ""),
        "url": meta.get("url", ""),
        "source": meta.get("source", ""),
        "published": meta.get("published", ""),
        "doi": meta.get("doi", ""),
        "arxiv_id": meta.get("arxiv_id", ""),
        "user_added": bool(meta.get("user_added", False)),
        "relevance_score": relevance if relevance is not None else round(float(meta.get("relevance", 0.0)), 1),
    }


def query_papers(session_id: str, query: str, n_results: int = 5) -> list[dict]:
    """
    Semantic search over the session collection.
    Returns top-k papers with relevance metadata (0-100, cosine similarity x100).
    """
    col = _get_collection(session_id)
    if col is None:
        return []
    count = col.count()
    if count == 0 or n_results <= 0:
        return []

    query_embedding = embed_texts([query])[0]
    results = col.query(
        query_embeddings=[query_embedding],
        n_results=min(n_results, count),
        include=["documents", "metadatas", "distances"],
    )

    papers = []
    for i, pid in enumerate(results["ids"][0]):
        distance = results["distances"][0][i]
        relevance_score = round((1 - distance) * 100, 1)
        papers.append(_paper_from(pid, results["metadatas"][0][i], results["documents"][0][i], relevance_score))
    return papers


def list_papers(session_id: str) -> list[dict]:
    """All papers in the session, most relevant to the hypothesis first."""
    col = _get_collection(session_id)
    if col is None:
        return []
    data = col.get(include=["documents", "metadatas"])
    papers = [_paper_from(pid, meta, doc) for pid, meta, doc in zip(data["ids"], data["metadatas"], data["documents"])]
    return sorted(papers, key=lambda p: p["relevance_score"], reverse=True)


def get_papers_by_ids(session_id: str, ids: list[str]) -> list[dict]:
    col = _get_collection(session_id)
    if col is None or not ids:
        return []
    data = col.get(ids=list(ids), include=["documents", "metadatas"])
    by_id = {pid: _paper_from(pid, meta, doc) for pid, meta, doc in zip(data["ids"], data["metadatas"], data["documents"])}
    return [by_id[i] for i in ids if i in by_id]


def remove_papers(session_id: str, ids: list[str]) -> None:
    col = _get_collection(session_id)
    if col is not None and ids:
        col.delete(ids=list(ids))


def delete_collection(session_id: str) -> None:
    try:
        get_client().delete_collection(_collection_name(session_id))
    except Exception:
        pass
