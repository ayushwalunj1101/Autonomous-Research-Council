"""
Per-session runtime flags shared between the async API layer and the graph thread.

Cancellation is cooperative: the flag is checked before every LLM call and graph node,
so a cancel takes effect at the next call boundary (an in-flight LLM request finishes first).
"""

import threading


class SessionCancelled(Exception):
    """Raised inside the pipeline when the user cancelled the session."""


class BudgetExceeded(Exception):
    """Raised when a session's LLM spend reaches ARC_SESSION_BUDGET_USD."""


class NoPapersFound(Exception):
    """Raised when retrieval returns zero papers even after broadening the query."""


_cancel_flags: dict[str, threading.Event] = {}
_lock = threading.Lock()


def _flag(session_id: str) -> threading.Event:
    with _lock:
        flag = _cancel_flags.get(session_id)
        if flag is None:
            flag = threading.Event()
            _cancel_flags[session_id] = flag
        return flag


def request_cancel(session_id: str) -> None:
    _flag(session_id).set()


def is_cancelled(session_id: str | None) -> bool:
    if not session_id:
        return False
    with _lock:
        flag = _cancel_flags.get(session_id)
    return bool(flag and flag.is_set())


def check_cancelled(session_id: str | None) -> None:
    if is_cancelled(session_id):
        raise SessionCancelled(f"Session {session_id} was cancelled.")


def clear_session(session_id: str) -> None:
    with _lock:
        _cancel_flags.pop(session_id, None)
