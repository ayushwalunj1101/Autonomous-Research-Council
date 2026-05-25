"""
Thread-safe SSE event emitter.

Agents running inside LangGraph (which runs in a ThreadPoolExecutor) call
emit() to push events. The async SSE generator in main.py consumes them.

Design:
  - Per-session asyncio.Queue for live streaming
  - Per-session event buffer (list) for reconnection replay
  - loop.call_soon_threadsafe() bridges sync → async safely from any context
"""

import asyncio

# Per-session state
_queues: dict[str, asyncio.Queue] = {}
_loops: dict[str, asyncio.AbstractEventLoop] = {}
_buffers: dict[str, list[dict]] = {}          # all events ever emitted, for replay


def create_session_queue(session_id: str) -> asyncio.Queue:
    """
    Creates the event queue for a new session.
    Must be called from async context (event loop is captured here).
    """
    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()
    _queues[session_id] = q
    _loops[session_id] = loop
    _buffers[session_id] = []
    return q


def emit(session_id: str, event: str, data: dict) -> None:
    """
    Thread-safe emit. Safe to call from:
      - async coroutines (event loop thread)
      - threads (graph.invoke inside run_in_executor)

    Uses call_soon_threadsafe so it works universally.
    """
    q = _queues.get(session_id)
    loop = _loops.get(session_id)
    if not q or not loop:
        return

    buf = _buffers.get(session_id, [])
    event_id = len(buf)
    item = {"id": event_id, "event": event, "data": data}
    buf.append(item)

    try:
        loop.call_soon_threadsafe(q.put_nowait, item)
    except RuntimeError:
        pass  # loop closed — session cleanup in progress


def close_session_queue(session_id: str) -> None:
    """Sends sentinel None to signal the SSE generator to close."""
    loop = _loops.get(session_id)
    q = _queues.get(session_id)
    if loop and q:
        try:
            loop.call_soon_threadsafe(q.put_nowait, None)
        except RuntimeError:
            pass


def get_queue(session_id: str) -> asyncio.Queue | None:
    return _queues.get(session_id)


def replay_from(session_id: str, last_event_id: int) -> list[dict]:
    """Returns all buffered events with id > last_event_id."""
    buf = _buffers.get(session_id, [])
    return [e for e in buf if e["id"] > last_event_id]


def cleanup_session(session_id: str) -> None:
    """Removes all state for a session (called during ChromaDB cleanup)."""
    _queues.pop(session_id, None)
    _loops.pop(session_id, None)
    _buffers.pop(session_id, None)
