from backend.llm.client import chat_json
from backend.llm.schemas import ORCHESTRATOR, as_str, as_str_list

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

Keywords are used as literature-search queries: make each one a specific noun phrase of
1-3 words (e.g. "federated learning", "readmission prediction"), most important first.

Respond with a JSON object only:
{
  "keywords": ["keyword1", "keyword2", "keyword3"],
  "hypothesis": "A concise 1-2 sentence research hypothesis.",
  "domain": "The research field in 1-3 words, e.g. 'computer science', 'biomedical', 'economics'."
}"""

# Proposals can be long; the orchestrator only needs the gist
_MAX_INPUT_CHARS = 12000


def run_orchestrator(mode: int, user_input: str, session_id: str) -> dict:
    """
    Calls the LLM to extract search keywords and prepare the context packet.

    Args:
        mode: 1 = topic, 2 = hypothesis, 3 = partial proposal
        user_input: raw text from the user
        session_id: uuid4 string for this session

    Returns:
        {"session_id", "mode", "keywords", "hypothesis", "domain", "raw_input"}
    """
    if mode not in _MODE_INSTRUCTIONS:
        raise ValueError(f"mode must be 1, 2, or 3 - got {mode}")

    user_prompt = (
        f"{_MODE_INSTRUCTIONS[mode]}\n\n"
        f"User input:\n{user_input[:_MAX_INPUT_CHARS]}"
    )

    parsed = chat_json(
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        agent="Orchestrator",
        session_id=session_id,
        schema=ORCHESTRATOR,
        schema_name="orchestrator",
        temperature=0.3,
        max_tokens=800,
        required_keys=("keywords", "hypothesis"),
    )

    keywords = [k for k in as_str_list(parsed.get("keywords")) if len(k) <= 80][:5]
    hypothesis = as_str(parsed.get("hypothesis"))
    if mode == 2 and not hypothesis:
        hypothesis = user_input.strip()
    if not keywords:
        raise ValueError("The Orchestrator could not extract search keywords from the input.")

    return {
        "session_id": session_id,
        "mode": mode,
        "keywords": keywords,
        "hypothesis": hypothesis or user_input.strip()[:500],
        "domain": as_str(parsed.get("domain")) or "general",
        "raw_input": user_input,
    }
