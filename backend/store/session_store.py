"""
SQLite-backed session store. Sessions, results and transcripts survive server restarts
(including uvicorn --reload), which keeps report links working and powers the
session history / compare features.
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

ACTIVE_STATUSES = ("preparing", "awaiting_confirmation", "queued", "fetching", "awaiting_review", "running")
# Statuses backed by a live pipeline task (lost on restart). A prepared session awaiting
# confirmation has no task and can still be started after a restart.
RUNNING_STATUSES = ("preparing", "queued", "fetching", "awaiting_review", "running")
# Never-started sessions (prepared then abandoned, or a failed prepare) stay out of history
HIDDEN_STATUSES = ("awaiting_confirmation", "discarded")
_JSON_FIELDS = ("keywords", "evaluation_json", "transcript")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    mode INTEGER NOT NULL,
    user_input TEXT NOT NULL DEFAULT '',
    hypothesis TEXT NOT NULL DEFAULT '',
    keywords TEXT NOT NULL DEFAULT '[]',
    domain TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    error TEXT,
    evaluation_json TEXT,
    transcript TEXT,
    pdf_path TEXT,
    cost_usd REAL NOT NULL DEFAULT 0,
    parent_session_id TEXT,
    chaos_constraint_override TEXT,
    review_papers INTEGER NOT NULL DEFAULT 0,
    corpus_deleted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at);
"""

_COLUMNS = (
    "session_id", "created_at", "updated_at", "mode", "user_input", "hypothesis", "keywords",
    "domain", "status", "error", "evaluation_json", "transcript", "pdf_path", "cost_usd",
    "parent_session_id", "chaos_constraint_override", "review_papers", "corpus_deleted",
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SessionStore:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # ------------------------------------------------------------------ #

    @staticmethod
    def _encode(field: str, value):
        if field in _JSON_FIELDS:
            return None if value is None else json.dumps(value, ensure_ascii=False)
        if field in ("review_papers", "corpus_deleted"):
            return int(bool(value))
        return value

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        record = dict(row)
        for field in _JSON_FIELDS:
            raw = record.get(field)
            record[field] = json.loads(raw) if raw else ([] if field == "keywords" else None)
        record["review_papers"] = bool(record.get("review_papers"))
        record["corpus_deleted"] = bool(record.get("corpus_deleted"))
        return record

    # ------------------------------------------------------------------ #

    def create(self, **fields) -> dict:
        now = utcnow()
        fields.setdefault("created_at", now)
        fields.setdefault("updated_at", now)
        unknown = set(fields) - set(_COLUMNS)
        if unknown:
            raise ValueError(f"Unknown session fields: {unknown}")
        cols = list(fields)
        with self._lock:
            self._conn.execute(
                f"INSERT INTO sessions ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                [self._encode(c, fields[c]) for c in cols],
            )
            self._conn.commit()
        return self.get(fields["session_id"])

    def update(self, session_id: str, **fields) -> None:
        if not fields:
            return
        fields["updated_at"] = utcnow()
        unknown = set(fields) - set(_COLUMNS)
        if unknown:
            raise ValueError(f"Unknown session fields: {unknown}")
        assignments = ", ".join(f"{c} = ?" for c in fields)
        with self._lock:
            self._conn.execute(
                f"UPDATE sessions SET {assignments} WHERE session_id = ?",
                [self._encode(c, v) for c, v in fields.items()] + [session_id],
            )
            self._conn.commit()

    def get(self, session_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        return self._decode(row)

    def list_recent(self, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT session_id, created_at, mode, hypothesis, status, cost_usd, parent_session_id, evaluation_json "
                f"FROM sessions WHERE status NOT IN ({', '.join('?' for _ in HIDDEN_STATUSES)}) "
                "ORDER BY created_at DESC LIMIT ?",
                (*HIDDEN_STATUSES, limit),
            ).fetchall()
        out = []
        for row in rows:
            record = dict(row)
            ev = json.loads(record.pop("evaluation_json") or "null") or {}
            record["ragas_score"] = ev.get("ragas_score")
            record["overall_confidence"] = ev.get("overall_confidence")
            record["refined_hypothesis"] = ev.get("refined_hypothesis")
            out.append(record)
        return out

    def expired_corpora(self, cutoff_iso: str) -> list[str]:
        """Finished sessions older than the cutoff whose ChromaDB collection still exists."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT session_id FROM sessions WHERE created_at < ? AND corpus_deleted = 0 AND status NOT IN "
                f"({', '.join('?' for _ in ACTIVE_STATUSES)})",
                (cutoff_iso, *ACTIVE_STATUSES),
            ).fetchall()
        return [r["session_id"] for r in rows]

    def mark_interrupted(self) -> int:
        """Sessions left active by a previous process can never finish — mark them failed."""
        with self._lock:
            cur = self._conn.execute(
                f"UPDATE sessions SET status = 'error', error = ?, updated_at = ? WHERE status IN "
                f"({', '.join('?' for _ in RUNNING_STATUSES)})",
                ("The server restarted while this session was running. Please start it again.", utcnow(),
                 *RUNNING_STATUSES),
            )
            self._conn.commit()
            return cur.rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()
