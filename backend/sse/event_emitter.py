"""
Thread-safe SSE event emitter with per-subscriber fan-out.

Agents running inside LangGraph (which runs in a worker thread) call emit() to push
events. Each connected SSE client gets its own asyncio.Queue, so a stale connection
that has not noticed its disconnect yet can no longer "steal" events from the client
that replaced it (the previous design shared one queue per session).

Design:
  - Per-session event buffer (ids 0, 1, 2, ...) for reconnection replay
  - subscribe() snapshots the backlog and registers a queue atomically, so a client
    never misses or duplicates an event between replay and live streaming
  - loop.call_soon_threadsafe() bridges sync -> async safely from any thread
"""

import asyncio
import threading

_loops: dict[str, asyncio.AbstractEventLoop] = {}
_buffers: dict[str, list[dict]] = {}          # all events ever emitted, for replay
_subscribers: dict[str, set[asyncio.Queue]] = {}
_closed: set[str] = set()
_lock = threading.Lock()


def create_session_queue(session_id: str) -> None:
    """
    Registers a session for streaming. Must be called from async context
    (the running event loop is captured here).
    """
    loop = asyncio.get_running_loop()
    with _lock:
        _loops[session_id] = loop
        _buffers.setdefault(session_id, [])
        _subscribers.setdefault(session_id, set())
        _closed.discard(session_id)


def emit(session_id: str, event: str, data: dict) -> None:
    """Thread-safe emit; safe from coroutines and from worker threads."""
    with _lock:
        loop = _loops.get(session_id)
        if loop is None:
            return
        buf = _buffers.setdefault(session_id, [])
        item = {"id": len(buf), "event": event, "data": data}
        buf.append(item)
        # Scheduled under the lock: callbacks run FIFO, so live delivery keeps id order
        # even when a worker thread and the event loop emit at the same moment.
        for q in _subscribers.get(session_id, ()):
            try:
                loop.call_soon_threadsafe(q.put_nowait, item)
            except RuntimeError:
                pass  # loop closed — session cleanup in progress


def subscribe(session_id: str, last_event_id: int) -> tuple[list[dict], asyncio.Queue | None]:
    """
    Returns (backlog of events with id > last_event_id, live queue).
    The queue is None when the session is not streaming (finished or unknown):
    the caller should send the backlog and close.
    """
    with _lock:
        backlog = [e for e in _buffers.get(session_id, []) if e["id"] > last_event_id]
        if session_id in _closed or session_id not in _loops:
            return backlog, None
        q: asyncio.Queue = asyncio.Queue()
        _subscribers.setdefault(session_id, set()).add(q)
    return backlog, q


def unsubscribe(session_id: str, q: asyncio.Queue | None) -> None:
    if q is None:
        return
    with _lock:
        _subscribers.get(session_id, set()).discard(q)


def close_session_queue(session_id: str) -> None:
    """Marks the stream finished and wakes every subscriber with a None sentinel."""
    with _lock:
        _closed.add(session_id)
        loop = _loops.get(session_id)
        if loop is None:
            return
        for q in _subscribers.get(session_id, ()):
            try:
                loop.call_soon_threadsafe(q.put_nowait, None)
            except RuntimeError:
                pass


def is_streaming(session_id: str) -> bool:
    with _lock:
        return session_id in _loops and session_id not in _closed


def replay_from(session_id: str, last_event_id: int) -> list[dict]:
    """Returns all buffered events with id > last_event_id."""
    with _lock:
        buf = list(_buffers.get(session_id, []))
    return [e for e in buf if e["id"] > last_event_id]


def cleanup_session(session_id: str) -> None:
    """Removes all state for a session (called during TTL cleanup)."""
    with _lock:
        _loops.pop(session_id, None)
        _buffers.pop(session_id, None)
        _subscribers.pop(session_id, None)
        _closed.discard(session_id)
