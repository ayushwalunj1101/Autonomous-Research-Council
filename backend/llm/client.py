"""
Centralised LLM client with Groq primary + OpenRouter fallback.

All agents call chat_completion() instead of managing their own OpenAI client.
On Groq RateLimitError (429), automatically retries on OpenRouter if the key
is configured.  If OpenRouter is also not available, the original error is re-raised.
"""

import os

from openai import OpenAI, RateLimitError

# ── Groq ────────────────────────────────────────────────────────────────────
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL    = "llama-3.3-70b-versatile"

# ── OpenRouter fallback ──────────────────────────────────────────────────────
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL    = "meta-llama/llama-3.3-70b-instruct"

_groq_client:        OpenAI | None = None
_openrouter_client:  OpenAI | None = None


def _groq() -> OpenAI:
    global _groq_client
    if _groq_client is None:
        _groq_client = OpenAI(
            api_key=os.environ["GROQ_API_KEY"],
            base_url=GROQ_BASE_URL,
        )
    return _groq_client


def _openrouter() -> OpenAI | None:
    global _openrouter_client
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key or key == "your_openrouter_api_key_here":
        return None
    if _openrouter_client is None:
        _openrouter_client = OpenAI(
            api_key=key,
            base_url=OPENROUTER_BASE_URL,
        )
    return _openrouter_client


def chat_completion(
    messages:    list[dict],
    temperature: float = 0.5,
    max_tokens:  int   = 1500,
) -> str:
    """
    Calls Groq.  On RateLimitError, falls back to OpenRouter if configured.
    Returns the raw response content string (stripped).
    Raises RuntimeError if both providers fail or are unavailable.
    """
    try:
        response = _groq().chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()

    except RateLimitError as groq_err:
        or_client = _openrouter()
        if or_client is None:
            raise RuntimeError(
                "Groq rate limit reached and OPENROUTER_API_KEY is not configured. "
                "Add your key to .env to enable the fallback."
            ) from groq_err

        print("[LLM] Groq rate limit — falling back to OpenRouter")
        response = or_client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()
