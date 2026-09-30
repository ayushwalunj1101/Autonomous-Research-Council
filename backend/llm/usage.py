"""
Per-session LLM usage accounting: cost tracking, budget guard, and a JSONL call log.

Every LLM call appends one line to {ARC_LOG_DIR}/{session_id}.jsonl with the prompt,
raw reply, finish_reason, token counts, latency and cost. The same file can be replayed
offline with ARC_LLM_PROVIDER=replay ARC_LLM_REPLAY=<path>.
"""

import json
import threading
import time
from datetime import datetime, timezone

import requests

from backend.config import get_settings
from backend.runtime import BudgetExceeded

# USD per 1M tokens (input, output). Checked against openrouter.ai/api/v1/models on 2026-09-30.
_KNOWN_PRICES: dict[str, tuple[float, float]] = {
    "anthropic/claude-sonnet-5.5": (2.00, 10.00),
    "anthropic/claude-haiku-4.5": (1.00, 5.00),
    "deepseek/deepseek-v3.2": (0.28, 0.42),
    "meta-llama/llama-3.3-70b-instruct": (0.10, 0.32),
    "openai/gpt-5-mini": (0.25, 2.00),
    "google/gemini-2.5-flash": (0.30, 2.50),
}
# Unknown models are billed at a deliberately high rate so the budget guard stays safe.
_CONSERVATIVE_PRICE = (3.00, 15.00)

_price_cache: dict[str, tuple[float, float]] = {}
_price_lock = threading.Lock()
_remote_prices_loaded = False

_session_cost: dict[str, float] = {}
_session_calls: dict[str, int] = {}
_usage_lock = threading.Lock()


def _load_remote_prices() -> None:
    global _remote_prices_loaded
    if _remote_prices_loaded:
        return
    _remote_prices_loaded = True
    try:
        resp = requests.get("https://openrouter.ai/api/v1/models", timeout=10)
        resp.raise_for_status()
        for model in resp.json().get("data", []):
            pricing = model.get("pricing") or {}
            try:
                prompt = float(pricing.get("prompt", 0)) * 1e6
                completion = float(pricing.get("completion", 0)) * 1e6
            except (TypeError, ValueError):
                continue
            _price_cache[model["id"]] = (prompt, completion)
    except Exception as exc:  # network trouble must never break a debate
        print(f"[Usage] Could not fetch OpenRouter prices: {exc}")


def price_for(provider: str, model: str) -> tuple[float, float]:
    """(input, output) USD per 1M tokens."""
    if provider in ("mock", "replay"):
        return (0.0, 0.0)
    if provider == "groq":
        return (0.0, 0.0)  # free tier; rate limits are the constraint, not money
    if model in _KNOWN_PRICES:
        return _KNOWN_PRICES[model]
    with _price_lock:
        if model not in _price_cache:
            _load_remote_prices()
        return _price_cache.get(model, _CONSERVATIVE_PRICE)


def session_cost(session_id: str | None) -> float:
    if not session_id:
        return 0.0
    with _usage_lock:
        return _session_cost.get(session_id, 0.0)


def session_calls(session_id: str | None) -> int:
    if not session_id:
        return 0
    with _usage_lock:
        return _session_calls.get(session_id, 0)


def check_budget(session_id: str | None) -> None:
    if not session_id:
        return
    budget = get_settings().session_budget_usd
    if budget > 0 and session_cost(session_id) >= budget:
        raise BudgetExceeded(
            f"Session cost limit reached (${session_cost(session_id):.3f} of ${budget:.2f}). "
            "Raise ARC_SESSION_BUDGET_USD to allow longer sessions."
        )


def budget_fraction_used(session_id: str | None) -> float:
    budget = get_settings().session_budget_usd
    if budget <= 0:
        return 0.0
    return session_cost(session_id) / budget


def record_call(
    *,
    session_id: str | None,
    agent: str,
    provider: str,
    model: str,
    messages: list[dict],
    raw: str,
    finish_reason: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    reported_cost: float | None,
    latency_s: float,
    attempt: int,
    error: str | None = None,
) -> float:
    """Adds the call's cost to the session total, appends it to the JSONL log, returns cost."""
    if reported_cost is not None:
        cost = float(reported_cost)
    else:
        price_in, price_out = price_for(provider, model)
        cost = (prompt_tokens * price_in + completion_tokens * price_out) / 1e6

    key = session_id or "_no_session"
    with _usage_lock:
        _session_cost[key] = _session_cost.get(key, 0.0) + cost
        _session_calls[key] = _session_calls.get(key, 0) + 1
        total = _session_cost[key]

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session_id": session_id,
        "agent": agent,
        "provider": provider,
        "model": model,
        "attempt": attempt,
        "finish_reason": finish_reason,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cost_usd": round(cost, 6),
        "session_cost_usd": round(total, 6),
        "latency_s": round(latency_s, 2),
        "error": error,
        "messages": messages,
        "raw": raw,
    }
    try:
        log_dir = get_settings().log_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / f"{key}.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"[Usage] Could not write call log: {exc}")
    return cost


def reset_session(session_id: str) -> None:
    with _usage_lock:
        _session_cost.pop(session_id, None)
        _session_calls.pop(session_id, None)


class Timer:
    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.elapsed = time.perf_counter() - self.start
        return False
