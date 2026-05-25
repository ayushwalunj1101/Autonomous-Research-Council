import json

from backend.llm.client import chat_completion


_MODE_INSTRUCTIONS = {
    1: (
        "The user has provided a research TOPIC only (not yet a hypothesis). "
        "Extract 3-5 specific search keywords from the topic. "
        "Also generate a concise initial hypothesis (1-2 sentences) that could be investigated."
    ),
    2: (
        "The user has provided a research HYPOTHESIS. "
        "Extract 3-5 specific search keywords from the hypothesis. "
        "Use the hypothesis as-is for the 'hypothesis' field."
    ),
    3: (
        "The user has provided a PARTIAL PROPOSAL (abstract or methodology draft). "
        "Parse it to extract the core claim and 3-5 specific search keywords. "
        "Summarize the core claim as the hypothesis (1-2 sentences)."
    ),
}

_SYSTEM_PROMPT = """You are the Orchestrator of the Autonomous Research Council.
Your job is to prepare a structured context packet for a council of AI research agents.

Always respond with valid JSON only — no markdown fences, no extra text.
Output schema:
{
  "keywords": ["keyword1", "keyword2", "keyword3"],
  "hypothesis": "A concise 1-2 sentence research hypothesis."
}"""


def run_orchestrator(mode: int, user_input: str, session_id: str) -> dict:
    """
    Calls Groq LLM to extract search keywords and prepare context packet.

    Args:
        mode: 1 = topic, 2 = hypothesis, 3 = partial proposal
        user_input: raw text from the user
        session_id: uuid4 string for this session

    Returns:
        {
            "session_id": str,
            "mode": int,
            "keywords": list[str],
            "hypothesis": str,
            "raw_input": str
        }
    """
    if mode not in _MODE_INSTRUCTIONS:
        raise ValueError(f"mode must be 1, 2, or 3 — got {mode}")

    user_prompt = (
        f"{_MODE_INSTRUCTIONS[mode]}\n\n"
        f"User input:\n{user_input}"
    )

    raw = chat_completion(
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=512,
    )

    try:
        parsed = json.loads(raw, strict=False)
    except json.JSONDecodeError:
        # Fallback: try to extract JSON block if model added extra text
        import re
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            parsed = json.loads(match.group(), strict=False)
        else:
            raise ValueError(f"Orchestrator LLM returned unparseable output: {raw}")

    return {
        "session_id": session_id,
        "mode": mode,
        "keywords": parsed.get("keywords", []),
        "hypothesis": parsed.get("hypothesis", ""),
        "raw_input": user_input,
    }
