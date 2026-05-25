import chromadb
from chromadb.config import Settings
from backend.rag.embedder import embed_texts

_client: chromadb.ClientAPI | None = None
CHROMA_PATH = "./chroma_store"


def get_client() -> chromadb.ClientAPI:
    """Returns singleton persistent ChromaDB client."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=CHROMA_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


def _collection_name(session_id: str) -> str:
    return f"session_{session_id}"


def collection_exists(session_id: str) -> bool:
    """Returns True if the session collection already has documents."""
    client = get_client()
    try:
        col = client.get_collection(_collection_name(session_id))
        return col.count() > 0
    except Exception:
        return False


def store_papers(session_id: str, papers: list[dict]) -> None:
    """
    Embeds title + abstract for each paper and stores in
    session-namespaced ChromaDB collection.
    """
    if not papers:
        return

    client = get_client()
    col = client.get_or_create_collection(
        name=_collection_name(session_id),
        metadata={"hnsw:space": "cosine"},
    )

    texts = [f"{p['title']}. {p.get('abstract', '')}" for p in papers]
    embeddings = embed_texts(texts)

    ids = [f"{session_id}_{i}" for i in range(len(papers))]
    metadatas = [
        {
            "title": p.get("title", ""),
            "authors": ", ".join(p.get("authors", [])),
            "url": p.get("url", ""),
            "source": p.get("source", ""),
            "published": str(p.get("published") or p.get("year") or ""),
        }
        for p in papers
    ]
    documents = [p.get("abstract", p.get("title", "")) for p in papers]

    col.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )


def query_papers(session_id: str, query: str, n_results: int = 5) -> list[dict]:
    """
    Semantic search over the session collection.
    Returns top-k papers with relevance metadata.
    """
    client = get_client()
    try:
        col = client.get_collection(_collection_name(session_id))
    except Exception:
        return []

    query_embedding = embed_texts([query])[0]
    results = col.query(
        query_embeddings=[query_embedding],
        n_results=min(n_results, col.count()),
        include=["documents", "metadatas", "distances"],
    )

    papers = []
    for i in range(len(results["ids"][0])):
        meta = results["metadatas"][0][i]
        distance = results["distances"][0][i]
        relevance_score = round((1 - distance) * 100, 1)
        papers.append(
            {
                "title": meta.get("title", ""),
                "abstract": results["documents"][0][i],
                "authors": meta.get("authors", ""),
                "url": meta.get("url", ""),
                "source": meta.get("source", ""),
                "published": meta.get("published", ""),
                "relevance_score": relevance_score,
            }
        )
    return papers
