"""
Central runtime settings, read from environment variables (.env is loaded by main.py).

Settings are read lazily and cached; tests call reset_settings() after changing env vars.
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# Values copied verbatim from .env.example — treated as "not configured".
_PLACEHOLDER_PREFIX = "your_"


def env_secret(name: str) -> str:
    """Returns an API key from the environment, or "" if unset or still a placeholder."""
    value = os.environ.get(name, "").strip()
    if not value or value.startswith(_PLACEHOLDER_PREFIX):
        return ""
    return value


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # LLM provider: "openrouter" | "groq" | "mock" | "replay"
    llm_provider: str
    # Default model for every agent; override per agent with ARC_MODEL_<AGENT>
    default_model: str
    groq_model: str
    # Optional second provider tried when the primary fails after its own retries
    llm_fallback: str
    llm_timeout_s: float
    replay_file: str

    session_budget_usd: float
    max_concurrent_sessions: int

    # Fact-Checker claim verification: "llm" (entailment verdicts) | "similarity" (legacy thresholds)
    claim_check: str
    skeptic_evidence: bool
    # Chaos constraint selection: "llm" (most relevant from pool) | "random"
    chaos_selection: str
    scoring_samples: int
    # Retry on RAGAS < 0.7: "targeted" (repair flagged claims) | "full" (re-run whole debate)
    retry_mode: str

    paper_review_timeout_s: float
    session_ttl_hours: float

    chroma_path: str
    db_path: str
    log_dir: Path
    sessions_dir: Path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    provider = os.environ.get("ARC_LLM_PROVIDER", "").strip().lower()
    if not provider:
        # No explicit choice: prefer OpenRouter when its key is configured
        provider = "openrouter" if env_secret("OPENROUTER_API_KEY") else "groq"

    return Settings(
        llm_provider=provider,
        default_model=os.environ.get("ARC_MODEL", "anthropic/claude-sonnet-5.5").strip(),
        groq_model=os.environ.get("ARC_GROQ_MODEL", "llama-3.3-70b-versatile").strip(),
        llm_fallback=os.environ.get("ARC_LLM_FALLBACK", "").strip().lower(),
        llm_timeout_s=_env_float("ARC_LLM_TIMEOUT", 180.0),
        replay_file=os.environ.get("ARC_LLM_REPLAY", "").strip(),
        session_budget_usd=_env_float("ARC_SESSION_BUDGET_USD", 0.50),
        max_concurrent_sessions=max(1, _env_int("ARC_MAX_CONCURRENT_SESSIONS", 2)),
        claim_check=os.environ.get("ARC_CLAIM_CHECK", "llm").strip().lower(),
        skeptic_evidence=_env_bool("ARC_SKEPTIC_EVIDENCE", False),
        chaos_selection=os.environ.get("ARC_CHAOS_SELECTION", "llm").strip().lower(),
        scoring_samples=max(1, _env_int("ARC_SCORING_SAMPLES", 3)),
        retry_mode=os.environ.get("ARC_RETRY_MODE", "targeted").strip().lower(),
        paper_review_timeout_s=_env_float("ARC_PAPER_REVIEW_TIMEOUT", 900.0),
        session_ttl_hours=_env_float("ARC_SESSION_TTL_HOURS", 24.0),
        chroma_path=os.environ.get("ARC_CHROMA_PATH", "./chroma_store"),
        db_path=os.environ.get("ARC_DB_PATH", "sessions/arc.db"),
        log_dir=Path(os.environ.get("ARC_LOG_DIR", "logs")),
        sessions_dir=Path(os.environ.get("ARC_SESSIONS_DIR", "sessions")),
    )


def reset_settings() -> None:
    get_settings.cache_clear()


def model_for(agent: str) -> str:
    """Model used by an agent: ARC_MODEL_<AGENT> if set, else ARC_MODEL."""
    key = "ARC_MODEL_" + agent.upper().replace("-", "_").replace(" ", "_")
    override = os.environ.get(key, "").strip()
    return override or get_settings().default_model
