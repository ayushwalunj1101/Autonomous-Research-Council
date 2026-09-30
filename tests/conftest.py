"""
Test configuration: every test runs offline against the mock LLM provider, with
ChromaDB, SQLite, call logs and PDFs redirected to a throwaway directory.
Environment variables are set before any backend module is imported.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="arc_tests_"))
os.environ.update({
    "ARC_LLM_PROVIDER": "mock",
    "ARC_LLM_FALLBACK": "",
    "ARC_CHROMA_PATH": str(_TMP / "chroma"),
    "ARC_DB_PATH": str(_TMP / "arc.db"),
    "ARC_LOG_DIR": str(_TMP / "logs"),
    "ARC_SESSIONS_DIR": str(_TMP / "sessions"),
    "ARC_SESSION_BUDGET_USD": "0.30",
    "ARC_CHAOS_SELECTION": "llm",
    "ARC_CLAIM_CHECK": "llm",
    "ARC_RETRY_MODE": "targeted",
    "ARC_SCORING_SAMPLES": "3",
    "ARC_MOCK_FAULTS": "",
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
})

import pytest  # noqa: E402

from backend.config import reset_settings  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_settings(monkeypatch):
    """Tests may change env vars; always rebuild settings and clients around each test."""
    from backend.llm import client, mock_provider

    reset_settings()
    client.reset_clients()
    mock_provider.reset_faults()
    yield
    reset_settings()
    client.reset_clients()
    mock_provider.reset_faults()


FAKE_PAPERS = [
    {
        "title": f"Paper {i}: federated learning for clinical prediction",
        "abstract": (
            f"We study federated learning for clinical prediction models (study {i}). "
            "Results improve on standard benchmarks while keeping patient data on site. "
            "We also evaluate robustness under distribution shift across hospitals."
        ),
        "authors": [f"Author {i}", "Second Author", "Third Author", "Fourth Author"],
        "url": f"https://arxiv.org/abs/2401.0000{i}",
        "arxiv_id": f"2401.0000{i}",
        "published": "2024-01-0{}".format(i + 1),
        "source": "arxiv",
    }
    for i in range(6)
]


@pytest.fixture
def seeded_session():
    """A session id whose ChromaDB collection holds FAKE_PAPERS (with relevance scores)."""
    import uuid

    from backend.rag.chromadb_client import delete_collection, store_papers

    session_id = str(uuid.uuid4())
    store_papers(session_id, [dict(p, relevance=70.0 - i) for i, p in enumerate(FAKE_PAPERS)])
    yield session_id
    delete_collection(session_id)


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP, ignore_errors=True)
