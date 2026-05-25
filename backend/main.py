import asyncio
import functools
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

load_dotenv()

from backend.agents.librarian import run_librarian
from backend.agents.orchestrator import run_orchestrator
from backend.graph.council_graph import get_council_graph
from backend.pdf.report_generator import generate_pdf
from backend.rag.chromadb_client import get_client
from backend.sse.event_emitter import (
    cleanup_session,
    close_session_queue,
    create_session_queue,
    emit,
    get_queue,
    replay_from,
)

app = FastAPI(title="Autonomous Research Council", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)


# --------------------------------------------------------------------------- #
# In-memory session store
# --------------------------------------------------------------------------- #

@dataclass
class SessionRecord:
    session_id: str
    created_at: datetime
    mode: int
    hypothesis: str
    keywords: list
    status: str = "running"          # "running" | "complete" | "error"
    evaluation_json: dict | None = None
    pdf_path: str | None = None
    error: str | None = None

_sessions: dict[str, SessionRecord] = {}


# --------------------------------------------------------------------------- #
# File-based session helpers (for legacy /api/start + /api/debate)
# --------------------------------------------------------------------------- #

def _save_session(session_id: str, data: dict) -> None:
    path = SESSIONS_DIR / f"{session_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_session(session_id: str) -> dict:
    path = SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found. Call /api/start first.",
        )
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Full pipeline runner (background asyncio task)
# --------------------------------------------------------------------------- #

async def _run_pipeline(session_id: str, mode: int, user_input: str) -> None:
    """
    Runs the full ARC pipeline:
      1. Orchestrator  — keyword extraction + hypothesis
      2. Librarian     — fetch + embed papers, emit papers_loaded
      3. graph.invoke  — full 5-round debate (in thread pool, emits all events)
      4. generate_pdf  — build ReportLab PDF
      5. emit report_ready + close queue
    """
    record = _sessions[session_id]
    loop = asyncio.get_event_loop()

    try:
        # Phase 1 — orchestrator (sync, fast)
        context_packet = run_orchestrator(
            mode=mode,
            user_input=user_input,
            session_id=session_id,
        )
        record.hypothesis = context_packet["hypothesis"]
        record.keywords   = context_packet["keywords"]

        # Phase 1 — librarian (sync, emits papers_loaded)
        run_librarian(context_packet)

        # Phase 2-3 — full debate graph (blocking: run in thread pool)
        initial_state = {
            "session_id": session_id,
            "mode": mode,
            "hypothesis": context_packet["hypothesis"],
            "keywords":   context_packet["keywords"],
            "current_round": 0,
            "round_outputs": [],
            "citation_flags": [],
            "chaos_constraint": None,
            "retry_count": 0,
            "ragas_score": None,
            "low_confidence_flag": False,
            "evaluation_json": None,
        }

        graph = get_council_graph()
        final_state = await loop.run_in_executor(
            None,
            functools.partial(graph.invoke, initial_state, {"recursion_limit": 60}),
        )

        evaluation_json = final_state.get("evaluation_json") or {}

        # Phase 4 — PDF generation
        pdf_path = generate_pdf(session_id, evaluation_json, mode=mode)

        record.status          = "complete"
        record.evaluation_json = evaluation_json
        record.pdf_path        = pdf_path

        emit(session_id, "report_ready", {"session_id": session_id})

    except Exception as exc:
        record.status = "error"
        record.error  = str(exc)
        print(f"[Pipeline] Session {session_id} failed: {exc}")
        emit(session_id, "error", {"message": str(exc)})

    finally:
        close_session_queue(session_id)


# --------------------------------------------------------------------------- #
# ChromaDB + session cleanup (24-hour TTL)
# --------------------------------------------------------------------------- #

async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(30 * 60)
        cutoff = datetime.utcnow() - timedelta(hours=24)
        for sid in list(_sessions.keys()):
            rec = _sessions.get(sid)
            if rec and rec.created_at < cutoff:
                try:
                    get_client().delete_collection(f"session_{sid}")
                except Exception:
                    pass
                _sessions.pop(sid, None)
                cleanup_session(sid)
                (SESSIONS_DIR / f"{sid}.json").unlink(missing_ok=True)
                (SESSIONS_DIR / f"{sid}.pdf").unlink(missing_ok=True)


@app.on_event("startup")
async def startup() -> None:
    asyncio.create_task(_cleanup_loop())


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #

class SessionCreateRequest(BaseModel):
    mode: int = Field(..., ge=1, le=3, description="1=topic, 2=hypothesis, 3=proposal")
    user_input: str = Field(..., min_length=3)

class SessionCreateResponse(BaseModel):
    session_id: str

class StartRequest(BaseModel):
    mode: int = Field(..., ge=1, le=3)
    user_input: str = Field(..., min_length=3)
    session_id: str | None = Field(default=None)

class StartResponse(BaseModel):
    session_id: str
    mode: int
    keywords: list[str]
    hypothesis: str
    papers_loaded: int
    reused_cache: bool

class DebateRequest(BaseModel):
    session_id: str = Field(...)

class DebateResponse(BaseModel):
    session_id: str
    round_outputs: list[dict]
    citation_flags: list[dict]
    ragas_score: float | None
    low_confidence_flag: bool
    evaluation_json: dict | None


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #

@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


# --------------------------------------------------------------------------- #
# Phase 4 — Unified session endpoints
# --------------------------------------------------------------------------- #

@app.post("/api/session", response_model=SessionCreateResponse, status_code=202)
async def create_session(request: SessionCreateRequest):
    """
    Creates a session and starts the full pipeline in the background.
    Returns {session_id} immediately (202). Connect to /stream for live events.
    """
    session_id = str(uuid.uuid4())
    create_session_queue(session_id)   # must happen in async context
    _sessions[session_id] = SessionRecord(
        session_id=session_id,
        created_at=datetime.utcnow(),
        mode=request.mode,
        hypothesis="",
        keywords=[],
    )
    asyncio.create_task(_run_pipeline(session_id, request.mode, request.user_input))
    return SessionCreateResponse(session_id=session_id)


@app.get("/api/session/{session_id}/stream")
async def stream_session(session_id: str, request: Request):
    """
    SSE stream — emits all debate events in real time.
    Supports reconnection via Last-Event-ID header.
    """
    print(f"[SSE] Client connected for session {session_id[:8]}")
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    last_id = int(request.headers.get("last-event-id", -1))

    async def event_generator():
        # Emit an immediate keepalive so the browser fires onopen right away
        yield {"event": "keepalive", "data": "{}"}

        # Replay missed events for reconnection (or full replay for late clients)
        for item in replay_from(session_id, last_id):
            yield {"id": str(item["id"]), "event": item["event"], "data": json.dumps(item["data"])}

        # If session is already complete, no need to read from the live queue
        record = _sessions.get(session_id)
        if record and record.status != "running":
            return

        q = get_queue(session_id)
        if q is None:
            return  # pipeline already finished

        while True:
            if await request.is_disconnected():
                break
            try:
                item = await asyncio.wait_for(q.get(), timeout=30.0)
            except asyncio.TimeoutError:
                yield {"event": "keepalive", "data": "{}"}
                continue
            if item is None:   # sentinel — debate finished
                break
            yield {"id": str(item["id"]), "event": item["event"], "data": json.dumps(item["data"])}

    return EventSourceResponse(event_generator())


@app.get("/api/session/{session_id}/result")
async def get_session_result(session_id: str):
    """Returns evaluation_json once complete."""
    record = _sessions.get(session_id)
    if not record:
        raise HTTPException(status_code=404, detail="Session not found.")
    if record.status == "running":
        raise HTTPException(status_code=202, detail="Debate still in progress.")
    if record.status == "error":
        raise HTTPException(status_code=500, detail=record.error)
    return {
        "session_id": session_id,
        "evaluation_json":    record.evaluation_json,
        "ragas_score":        record.evaluation_json.get("ragas_score") if record.evaluation_json else None,
        "low_confidence_flag": record.evaluation_json.get("low_confidence_flag", False) if record.evaluation_json else False,
    }


@app.get("/api/session/{session_id}/pdf")
async def get_session_pdf(session_id: str):
    """Downloads the PDF report."""
    record = _sessions.get(session_id)
    if not record:
        raise HTTPException(status_code=404, detail="Session not found.")
    if record.status == "running":
        raise HTTPException(status_code=202, detail="Report not ready yet.")
    if record.status == "error":
        raise HTTPException(status_code=500, detail=record.error)
    if not record.pdf_path or not Path(record.pdf_path).exists():
        raise HTTPException(status_code=404, detail="PDF file not found.")
    return FileResponse(
        path=record.pdf_path,
        media_type="application/pdf",
        filename=f"arc_report_{session_id[:8]}.pdf",
    )


# --------------------------------------------------------------------------- #
# Legacy endpoints (Phase 1/2 — kept for backward compatibility)
# --------------------------------------------------------------------------- #

@app.post("/api/start", response_model=StartResponse)
async def start_session(request: StartRequest):
    """Phase 1 entry point (legacy). Prefer POST /api/session."""
    session_id = request.session_id or str(uuid.uuid4())

    try:
        context_packet = run_orchestrator(mode=request.mode, user_input=request.user_input, session_id=session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Orchestrator failed: {e}")

    try:
        library_result = run_librarian(context_packet)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Librarian failed: {e}")

    _save_session(session_id, {
        "session_id": session_id, "mode": request.mode,
        "hypothesis": context_packet["hypothesis"], "keywords": context_packet["keywords"],
    })

    return StartResponse(
        session_id=session_id, mode=request.mode,
        keywords=context_packet["keywords"], hypothesis=context_packet["hypothesis"],
        papers_loaded=library_result["papers_loaded"], reused_cache=library_result["reused_cache"],
    )


@app.post("/api/debate", response_model=DebateResponse)
async def run_debate(request: DebateRequest):
    """Full debate (legacy). Prefer POST /api/session."""
    session = _load_session(request.session_id)
    initial_state = {
        "session_id": session["session_id"], "mode": session["mode"],
        "hypothesis": session["hypothesis"], "keywords": session["keywords"],
        "current_round": 0, "round_outputs": [], "citation_flags": [],
        "chaos_constraint": None, "retry_count": 0,
        "ragas_score": None, "low_confidence_flag": False, "evaluation_json": None,
    }
    try:
        loop = asyncio.get_event_loop()
        final_state = await loop.run_in_executor(
            None, functools.partial(get_council_graph().invoke, initial_state)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Debate failed: {e}")

    return DebateResponse(
        session_id=request.session_id,
        round_outputs=final_state["round_outputs"],
        citation_flags=final_state["citation_flags"],
        ragas_score=final_state.get("ragas_score"),
        low_confidence_flag=final_state.get("low_confidence_flag", False),
        evaluation_json=final_state.get("evaluation_json"),
    )
