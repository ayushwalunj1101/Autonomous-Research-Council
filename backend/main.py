import asyncio
import json
import os
import sys
import traceback
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

load_dotenv()

# Windows consoles and redirected logs default to cp1252: never let print() of
# LLM-generated text raise UnicodeEncodeError inside the pipeline's error handler.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

from backend.agents.librarian import (  # noqa: E402
    add_paper_by_identifier,
    add_uploaded_paper,
    paper_summary,
    run_librarian,
)
from backend.agents.orchestrator import run_orchestrator  # noqa: E402
from backend.config import get_settings  # noqa: E402
from backend.export.exporters import to_bibtex, to_docx, to_markdown  # noqa: E402
from backend.fetchers.documents import UnsupportedDocument, extract_text  # noqa: E402
from backend.graph.council_graph import final_evaluation, initial_state, run_council  # noqa: E402
from backend.llm.client import LLMError, active_model  # noqa: E402
from backend.llm.usage import reset_session, session_cost  # noqa: E402
from backend.pdf.report_generator import generate_pdf  # noqa: E402
from backend.rag.chromadb_client import delete_collection, list_papers, remove_papers  # noqa: E402
from backend.runtime import (  # noqa: E402
    BudgetExceeded,
    NoPapersFound,
    SessionCancelled,
    check_cancelled,
    clear_session,
    request_cancel,
)
from backend.scoring.evaluation import normalize_evaluation  # noqa: E402
from backend.sse.event_emitter import (  # noqa: E402
    cleanup_session,
    close_session_queue,
    create_session_queue,
    emit,
    subscribe,
    unsubscribe,
)
from backend.store.session_store import ACTIVE_STATUSES, SessionStore  # noqa: E402

SESSIONS_DIR = get_settings().sessions_dir
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# Runtime state (per process)
# --------------------------------------------------------------------------- #

@dataclass
class SessionRuntime:
    review_event: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None


_store: SessionStore | None = None
_runtime: dict[str, SessionRuntime] = {}
_background_tasks: set[asyncio.Task] = set()   # strong refs so tasks are never GC'd mid-run
_slots: asyncio.Semaphore | None = None
_waiting = 0


def store() -> SessionStore:
    if _store is None:
        raise HTTPException(status_code=503, detail="Session store is not initialised.")
    return _store


def _spawn(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _store, _slots
    settings = get_settings()
    _store = SessionStore(settings.db_path)
    interrupted = _store.mark_interrupted()
    if interrupted:
        print(f"[Startup] Marked {interrupted} interrupted session(s) as failed.")
    _slots = asyncio.Semaphore(settings.max_concurrent_sessions)
    cleanup = _spawn(_cleanup_loop())
    print(f"[Startup] LLM provider={settings.llm_provider} model={active_model('Chairman')} "
          f"budget=${settings.session_budget_usd:.2f}/session slots={settings.max_concurrent_sessions}")
    try:
        yield
    finally:
        cleanup.cancel()
        _store.close()


app = FastAPI(title="Autonomous Research Council", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("ARC_CORS_ORIGINS", "*").split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


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

def _short(exc: Exception, limit: int = 400) -> str:
    text = str(exc).strip() or type(exc).__name__
    return text if len(text) <= limit else text[:limit] + "…"


async def _run_pipeline(session_id: str, run_prepare: bool) -> None:
    """
    Runs the full ARC pipeline for a session:
      0. waits for a free slot (ARC_MAX_CONCURRENT_SESSIONS)
      1. Orchestrator (only for the one-shot POST /api/session flow)
      2. Librarian — fetch + rerank + store papers, emit papers_loaded
      3. optional paper review — waits for POST /papers/confirm
      4. debate graph (worker thread) — emits all debate events
      5. save the result, then build the PDF (a PDF failure never fails the session)
    All blocking work runs in worker threads so the event loop keeps serving SSE.
    """
    global _waiting
    runtime = _runtime[session_id]
    settings = get_settings()
    cancelled = False

    try:
        if _slots.locked():
            _waiting += 1
            emit(session_id, "queued", {"position": _waiting})
            try:
                await _slots.acquire()
            finally:
                _waiting -= 1
        else:
            await _slots.acquire()

        try:
            check_cancelled(session_id)
            record = store().get(session_id)

            if run_prepare:
                store().update(session_id, status="preparing")
                packet = await asyncio.to_thread(run_orchestrator, record["mode"], record["user_input"], session_id)
                store().update(session_id, hypothesis=packet["hypothesis"], keywords=packet["keywords"],
                               domain=packet["domain"])
                record = store().get(session_id)

            emit(session_id, "session_info", {
                "hypothesis": record["hypothesis"], "keywords": record["keywords"], "mode": record["mode"],
                "model": active_model("Chairman"), "budget_usd": settings.session_budget_usd,
            })

            store().update(session_id, status="fetching")
            packet = {"session_id": session_id, "keywords": record["keywords"],
                      "hypothesis": record["hypothesis"], "domain": record["domain"]}
            await asyncio.to_thread(run_librarian, packet, record["review_papers"])

            if record["review_papers"]:
                store().update(session_id, status="awaiting_review")
                try:
                    await asyncio.wait_for(runtime.review_event.wait(), timeout=settings.paper_review_timeout_s)
                except asyncio.TimeoutError:
                    emit(session_id, "review_timeout", {"message": "No response - continuing with all papers."})
                check_cancelled(session_id)
                papers = await asyncio.to_thread(list_papers, session_id)
                if not papers:
                    raise NoPapersFound("Every paper was removed. Add at least one paper before starting the debate.")
                emit(session_id, "papers_confirmed", {"count": len(papers)})

            store().update(session_id, status="running")
            state = initial_state(
                session_id, record["mode"], record["hypothesis"], record["keywords"],
                domain=record["domain"], chaos_constraint_override=record["chaos_constraint_override"],
            )
            final_state = await asyncio.to_thread(run_council, state)

            cost = round(session_cost(session_id), 4)
            # The best attempt's evaluation, but with the full attempt history (it may predate later repairs)
            evaluation = normalize_evaluation({
                **final_evaluation(final_state),
                "attempts": final_state.get("attempt_history", []),
                "cost_usd": cost,
            })
            transcript = {
                "round_outputs": final_state.get("round_outputs", []),
                "citation_flags": final_state.get("citation_flags", []),
                "claim_audits": final_state.get("claim_audits", []),
                "attempt_history": final_state.get("attempt_history", []),
            }
            store().update(session_id, status="complete", evaluation_json=evaluation,
                           transcript=transcript, cost_usd=cost, error=None)

            try:
                pdf_path = await asyncio.to_thread(generate_pdf, session_id, evaluation, record["mode"])
                store().update(session_id, pdf_path=pdf_path)
            except Exception as exc:  # the report page and exports still work without the PDF
                print(f"[Pipeline] PDF generation failed for {session_id}: {exc}")
                emit(session_id, "pdf_failed", {"message": _short(exc)})

            emit(session_id, "report_ready", {"session_id": session_id, "cost_usd": cost})
        finally:
            _slots.release()

    except (SessionCancelled, asyncio.CancelledError):
        cancelled = True
        store().update(session_id, status="cancelled", error="Cancelled by user.",
                       cost_usd=round(session_cost(session_id), 4))
        emit(session_id, "cancelled", {"message": "The debate was stopped."})
    except (BudgetExceeded, NoPapersFound, LLMError, ValueError) as exc:
        _fail(session_id, _short(exc))
    except Exception as exc:
        traceback.print_exc()
        _fail(session_id, f"Unexpected {type(exc).__name__}: {_short(exc, 300)}")
    finally:
        close_session_queue(session_id)
        _runtime.pop(session_id, None)
        if not cancelled:
            # A cancelled graph thread may still be mid-call; it needs the flag to stop.
            clear_session(session_id)


def _fail(session_id: str, message: str) -> None:
    print(f"[Pipeline] Session {session_id} failed: {message}")
    store().update(session_id, status="error", error=message, cost_usd=round(session_cost(session_id), 4))
    emit(session_id, "pipeline_error", {"message": message})


def _launch(session_id: str, run_prepare: bool) -> None:
    create_session_queue(session_id)
    runtime = SessionRuntime()
    _runtime[session_id] = runtime
    runtime.task = _spawn(_run_pipeline(session_id, run_prepare))


# --------------------------------------------------------------------------- #
# ChromaDB cleanup (TTL) — session rows, results and PDFs are kept for history
# --------------------------------------------------------------------------- #

async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(30 * 60)
        try:
            ttl = get_settings().session_ttl_hours
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=ttl)).isoformat(timespec="seconds")
            for sid in store().expired_corpora(cutoff):
                await asyncio.to_thread(delete_collection, sid)
                cleanup_session(sid)
                reset_session(sid)
                clear_session(sid)
                store().update(sid, corpus_deleted=True)
        except Exception as exc:
            print(f"[Cleanup] {exc}")


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #

class PrepareRequest(BaseModel):
    mode: int = Field(..., ge=1, le=3, description="1=topic, 2=hypothesis, 3=proposal")
    user_input: str = Field(..., min_length=3, max_length=20000)
    parent_session_id: str | None = None


class PrepareResponse(BaseModel):
    session_id: str
    hypothesis: str
    keywords: list[str]
    domain: str


class StartSessionRequest(BaseModel):
    hypothesis: str | None = Field(default=None, max_length=2000)
    keywords: list[str] | None = None
    review_papers: bool = False
    chaos_constraint: str | None = Field(default=None, max_length=500)


class SessionCreateRequest(BaseModel):
    mode: int = Field(..., ge=1, le=3, description="1=topic, 2=hypothesis, 3=proposal")
    user_input: str = Field(..., min_length=3, max_length=20000)
    review_papers: bool = False
    chaos_constraint: str | None = Field(default=None, max_length=500)
    parent_session_id: str | None = None


class SessionCreateResponse(BaseModel):
    session_id: str


class AddPaperRequest(BaseModel):
    identifier: str = Field(..., min_length=4, max_length=300)
    # Papers the user unticked: dropped first so an add works at the 20-paper cap
    remove_ids: list[str] = Field(default_factory=list)


class ConfirmPapersRequest(BaseModel):
    remove_ids: list[str] = Field(default_factory=list)


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
# Helpers
# --------------------------------------------------------------------------- #

def _record_or_404(session_id: str) -> dict:
    record = store().get(session_id)
    if not record:
        raise HTTPException(status_code=404, detail="Session not found.")
    return record


def _require_complete(record: dict) -> None:
    status = record["status"]
    if status in ACTIVE_STATUSES:
        raise HTTPException(status_code=409, detail="The debate is still in progress.")
    if status == "cancelled":
        raise HTTPException(status_code=409, detail="This session was cancelled.")
    if status == "discarded":
        raise HTTPException(status_code=409, detail="This session was never started.")
    if status == "error":
        raise HTTPException(status_code=500, detail=record.get("error") or "Session failed.")


def _clean_keywords(keywords: list[str] | None, fallback: list[str]) -> list[str]:
    if keywords is None:
        return fallback
    cleaned = []
    for kw in keywords:
        kw = " ".join(str(kw).split())[:80]
        if kw and kw.lower() not in (k.lower() for k in cleaned):
            cleaned.append(kw)
    if not cleaned:
        raise HTTPException(status_code=422, detail="Provide at least one search keyword.")
    return cleaned[:6]


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #

@app.get("/api/health")
async def health_check():
    settings = get_settings()
    return {
        "status": "ok",
        "provider": settings.llm_provider,
        "model": active_model("Chairman"),
        "budget_usd": settings.session_budget_usd,
        "claim_check": settings.claim_check,
    }


# --------------------------------------------------------------------------- #
# Session lifecycle
# --------------------------------------------------------------------------- #

@app.post("/api/session/prepare", response_model=PrepareResponse)
async def prepare_session(request: PrepareRequest):
    """
    Step 1 of the two-step flow: runs the Orchestrator and returns the extracted
    hypothesis + keywords so the user can review and edit them before starting.
    """
    session_id = str(uuid.uuid4())
    store().create(session_id=session_id, mode=request.mode, user_input=request.user_input,
                   status="preparing", parent_session_id=request.parent_session_id)
    try:
        packet = await asyncio.to_thread(run_orchestrator, request.mode, request.user_input, session_id)
    except (LLMError, ValueError, BudgetExceeded) as exc:
        # Never started: keep the row for debugging but out of the history list
        store().update(session_id, status="discarded", error=_short(exc))
        raise HTTPException(status_code=502, detail=_short(exc))
    store().update(session_id, status="awaiting_confirmation", hypothesis=packet["hypothesis"],
                   keywords=packet["keywords"], domain=packet["domain"],
                   cost_usd=round(session_cost(session_id), 4))
    return PrepareResponse(session_id=session_id, hypothesis=packet["hypothesis"],
                           keywords=packet["keywords"], domain=packet["domain"])


@app.post("/api/session/{session_id}/start", response_model=SessionCreateResponse, status_code=202)
async def start_prepared_session(session_id: str, request: StartSessionRequest):
    """Step 2: starts the debate with the (optionally edited) hypothesis and keywords."""
    record = _record_or_404(session_id)
    if record["status"] != "awaiting_confirmation":
        raise HTTPException(status_code=409, detail=f"Session cannot be started (status: {record['status']}).")
    hypothesis = (request.hypothesis or "").strip() or record["hypothesis"]
    if not hypothesis:
        raise HTTPException(status_code=422, detail="The hypothesis cannot be empty.")
    store().update(
        session_id,
        hypothesis=hypothesis,
        keywords=_clean_keywords(request.keywords, record["keywords"]),
        review_papers=request.review_papers,
        chaos_constraint_override=(request.chaos_constraint or "").strip() or None,
        status="queued",
    )
    _launch(session_id, run_prepare=False)
    return SessionCreateResponse(session_id=session_id)


@app.post("/api/session", response_model=SessionCreateResponse, status_code=202)
async def create_session(request: SessionCreateRequest):
    """
    One-shot flow: creates a session and runs Orchestrator + debate in the background.
    Returns {session_id} immediately (202). Connect to /stream for live events.
    """
    session_id = str(uuid.uuid4())
    store().create(
        session_id=session_id, mode=request.mode, user_input=request.user_input,
        status="queued", review_papers=request.review_papers,
        chaos_constraint_override=(request.chaos_constraint or "").strip() or None,
        parent_session_id=request.parent_session_id,
    )
    _launch(session_id, run_prepare=True)
    return SessionCreateResponse(session_id=session_id)


@app.post("/api/session/{session_id}/cancel")
async def cancel_session(session_id: str):
    record = _record_or_404(session_id)
    if record["status"] == "awaiting_confirmation":
        store().update(session_id, status="discarded", error="Discarded before the debate started.")
        return {"status": "discarded"}
    if record["status"] not in ACTIVE_STATUSES:
        raise HTTPException(status_code=409, detail=f"Session is not running (status: {record['status']}).")
    request_cancel(session_id)  # stops the graph thread at its next LLM call / node
    runtime = _runtime.get(session_id)
    if runtime:
        runtime.review_event.set()
        if runtime.task and not runtime.task.done():
            runtime.task.cancel()  # releases waits (queue slot, paper review) immediately
    return {"status": "cancelling"}


@app.get("/api/session/{session_id}/stream")
async def stream_session(session_id: str, request: Request):
    """
    SSE stream — emits all debate events in real time.
    Reconnection: pass the last received id as the Last-Event-ID header or the
    ?last_event_id= query parameter (EventSource cannot set headers on a new connection).
    """
    record = _record_or_404(session_id)

    raw_id = request.headers.get("last-event-id") or request.query_params.get("last_event_id") or "-1"
    try:
        last_id = int(raw_id)
    except ValueError:
        last_id = -1

    async def event_generator():
        backlog, q = subscribe(session_id, last_id)
        try:
            # Immediate keepalive so the browser fires onopen right away
            yield {"event": "keepalive", "data": "{}"}
            for item in backlog:
                yield {"id": str(item["id"]), "event": item["event"], "data": json.dumps(item["data"])}
            if q is None:
                # Not streaming in this process (finished, never started, or server restarted):
                # tell the client the final status so it stops reconnecting.
                current = store().get(session_id) or record
                yield {"event": "session_status", "data": json.dumps({
                    "status": current["status"], "error": current.get("error") or "",
                })}
                return
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(q.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield {"event": "keepalive", "data": "{}"}
                    continue
                if item is None:   # sentinel — pipeline finished
                    break
                yield {"id": str(item["id"]), "event": item["event"], "data": json.dumps(item["data"])}
        finally:
            unsubscribe(session_id, q)

    return EventSourceResponse(event_generator())


@app.get("/api/session/{session_id}/result")
async def get_session_result(session_id: str):
    """Returns the evaluation once complete; 202 with the current status while running."""
    record = _record_or_404(session_id)
    status = record["status"]
    if status in ACTIVE_STATUSES:
        return JSONResponse(status_code=202, content={
            "session_id": session_id, "status": status, "detail": "Debate still in progress.",
            "hypothesis": record["hypothesis"], "keywords": record["keywords"],
        })
    if status in ("cancelled", "discarded"):
        raise HTTPException(status_code=409, detail="This session was cancelled." if status == "cancelled"
                            else "This session was never started.")
    if status == "error":
        raise HTTPException(status_code=500, detail=record.get("error") or "Session failed.")

    evaluation = normalize_evaluation(record["evaluation_json"])
    return {
        "session_id": session_id,
        "status": status,
        "mode": record["mode"],
        "created_at": record["created_at"],
        "hypothesis": record["hypothesis"],
        "keywords": record["keywords"],
        "parent_session_id": record["parent_session_id"],
        "cost_usd": record["cost_usd"],
        "evaluation_json": evaluation,
        "ragas_score": evaluation["ragas_score"],
        "low_confidence_flag": evaluation["low_confidence_flag"],
    }


@app.get("/api/session/{session_id}/transcript")
async def get_session_transcript(session_id: str):
    """Full debate transcript: every round's text, claims, flags and verdicts."""
    record = _record_or_404(session_id)
    _require_complete(record)
    return {"session_id": session_id, **(record["transcript"] or {"round_outputs": [], "citation_flags": []})}


@app.get("/api/sessions")
async def list_sessions(limit: int = 20):
    """Recent sessions (newest first) for the history and compare views."""
    return {"sessions": store().list_recent(max(1, min(limit, 100)))}


# --------------------------------------------------------------------------- #
# Paper review (between retrieval and debate)
# --------------------------------------------------------------------------- #

def _require_review(record: dict) -> None:
    if record["status"] != "awaiting_review":
        raise HTTPException(status_code=409, detail="Papers can only be changed while the session awaits review.")


async def _drop_papers(session_id: str, remove_ids: list[str]) -> None:
    ids = [i for i in remove_ids if i.startswith(session_id)]
    if ids:
        await asyncio.to_thread(remove_papers, session_id, ids)


@app.get("/api/session/{session_id}/papers")
async def get_papers(session_id: str):
    record = _record_or_404(session_id)
    papers = await asyncio.to_thread(list_papers, session_id)
    return {"status": record["status"], "papers": [paper_summary(p) for p in papers]}


@app.post("/api/session/{session_id}/papers")
async def add_paper(session_id: str, request: AddPaperRequest):
    record = _record_or_404(session_id)
    _require_review(record)
    await _drop_papers(session_id, request.remove_ids)
    try:
        paper = await asyncio.to_thread(add_paper_by_identifier, session_id, request.identifier, record["hypothesis"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    papers = await asyncio.to_thread(list_papers, session_id)
    return {"paper": paper, "papers": [paper_summary(p) for p in papers]}


@app.post("/api/session/{session_id}/papers/upload")
async def upload_paper(session_id: str, file: UploadFile = File(...), remove_ids: str = Form("")):
    record = _record_or_404(session_id)
    _require_review(record)
    await _drop_papers(session_id, [i.strip() for i in remove_ids.split(",") if i.strip()])
    data = await file.read()
    try:
        paper = await asyncio.to_thread(add_uploaded_paper, session_id, file.filename or "paper.pdf", data,
                                        record["hypothesis"])
    except (ValueError, UnsupportedDocument) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    papers = await asyncio.to_thread(list_papers, session_id)
    return {"paper": paper, "papers": [paper_summary(p) for p in papers]}


@app.post("/api/session/{session_id}/papers/confirm")
async def confirm_papers(session_id: str, request: ConfirmPapersRequest):
    record = _record_or_404(session_id)
    _require_review(record)
    await _drop_papers(session_id, request.remove_ids)
    runtime = _runtime.get(session_id)
    if runtime is None:
        raise HTTPException(status_code=409, detail="Session is not running in this server process.")
    runtime.review_event.set()
    return {"status": "running"}


# --------------------------------------------------------------------------- #
# Reports and exports
# --------------------------------------------------------------------------- #

@app.get("/api/session/{session_id}/pdf")
async def get_session_pdf(session_id: str):
    """Downloads the PDF report (rebuilt on demand if it is missing)."""
    record = _record_or_404(session_id)
    _require_complete(record)
    pdf_path = record.get("pdf_path")
    if not pdf_path or not Path(pdf_path).exists():
        try:
            pdf_path = await asyncio.to_thread(generate_pdf, session_id, record["evaluation_json"] or {}, record["mode"])
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"PDF generation failed: {_short(exc)}")
        store().update(session_id, pdf_path=pdf_path)
    return FileResponse(path=pdf_path, media_type="application/pdf", filename=f"arc_report_{session_id[:8]}.pdf")


_EXPORTS = {
    "markdown": ("text/markdown; charset=utf-8", "md"),
    "bibtex": ("application/x-bibtex; charset=utf-8", "bib"),
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"),
}


@app.get("/api/session/{session_id}/export/{fmt}")
async def export_session(session_id: str, fmt: str):
    if fmt not in _EXPORTS:
        raise HTTPException(status_code=404, detail=f"Unknown export format '{fmt}'. Use markdown, bibtex or docx.")
    record = _record_or_404(session_id)
    _require_complete(record)
    if fmt == "markdown":
        body: bytes = to_markdown(record).encode("utf-8")
    elif fmt == "bibtex":
        body = to_bibtex(record).encode("utf-8")
    else:
        body = await asyncio.to_thread(to_docx, record)
    media_type, ext = _EXPORTS[fmt]
    return Response(content=body, media_type=media_type, headers={
        "Content-Disposition": f'attachment; filename="arc_report_{session_id[:8]}.{ext}"',
    })


@app.post("/api/extract-text")
async def extract_uploaded_text(file: UploadFile = File(...)):
    """Extracts text from an uploaded PDF/DOCX/TXT proposal (input mode 3)."""
    data = await file.read()
    try:
        text = await asyncio.to_thread(extract_text, file.filename or "", data)
    except UnsupportedDocument as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    limit = 20000
    return {"filename": file.filename, "text": text[:limit], "truncated": len(text) > limit}


# --------------------------------------------------------------------------- #
# Legacy endpoints (Phase 1/2 — kept for backward compatibility)
# --------------------------------------------------------------------------- #

@app.post("/api/start", response_model=StartResponse)
async def start_session(request: StartRequest):
    """Phase 1 entry point (legacy). Prefer POST /api/session/prepare."""
    session_id = request.session_id or str(uuid.uuid4())

    try:
        context_packet = await asyncio.to_thread(run_orchestrator, request.mode, request.user_input, session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Orchestrator failed: {_short(e)}")

    try:
        library_result = await asyncio.to_thread(run_librarian, context_packet)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Librarian failed: {_short(e)}")

    _save_session(session_id, {
        "session_id": session_id, "mode": request.mode,
        "hypothesis": context_packet["hypothesis"], "keywords": context_packet["keywords"],
        "domain": context_packet["domain"],
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
    state = initial_state(session["session_id"], session["mode"], session["hypothesis"],
                          session["keywords"], domain=session.get("domain", ""))
    try:
        final_state = await asyncio.to_thread(run_council, state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Debate failed: {_short(e)}")

    return DebateResponse(
        session_id=request.session_id,
        round_outputs=final_state["round_outputs"],
        citation_flags=final_state["citation_flags"],
        ragas_score=final_state.get("ragas_score"),
        low_confidence_flag=final_state.get("low_confidence_flag", False),
        evaluation_json=final_evaluation(final_state),
    )
