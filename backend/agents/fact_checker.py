import re

from backend.agents.common import truncate
from backend.agents.skeptic import flags_seen_by_skeptic
from backend.config import get_settings
from backend.llm.client import LLMOutputError, chat_json
from backend.llm.schemas import CLAIM_VERIFICATION, FABRICATION_CHECK, as_int, as_str
from backend.rag.chromadb_client import get_papers_by_ids, query_papers
from backend.sse.event_emitter import emit

# Similarity fallback thresholds (hard < 45, soft < 60). These no longer tighten on
# retries: a retry now re-checks only revised claims against the same corpus, and a
# stricter bar there made retries structurally harder to pass than the first attempt.
HARD_THRESHOLD = 45.0
SOFT_THRESHOLD = 60.0

CANDIDATES_PER_CLAIM = 3
MAX_PAPERS_IN_PROMPT = 12
_VERDICT_SEVERITY = {"supported": None, "partial": "soft", "unsupported": "hard", "contradicted": "hard"}


# ------------------------------------------------------------------ #
# Innovator audit — entailment verdicts (LLM) with similarity fallback
# ------------------------------------------------------------------ #

_VERIFY_SYSTEM_PROMPT = """You are the Fact-Checker agent on the Autonomous Research Council.
For each claim, decide whether the numbered paper abstracts support it.

Verdicts:
- "supported": an abstract states the claim or directly implies it.
- "partial": an abstract supports a weaker or narrower version of the claim.
- "unsupported": no abstract addresses the claim (topical similarity is NOT support).
- "contradicted": an abstract states the opposite of the claim.

For supported/partial/contradicted verdicts give the paper number and a short VERBATIM
quote (under 30 words) copied from that abstract. For unsupported use paper_id 0 and an
empty quote. Judge only against the abstracts provided, not your own knowledge.

Respond with a JSON object only:
{"verdicts": [{"claim_id": 1, "verdict": "supported", "paper_id": 2, "quote": "...", "reason": "one sentence"}]}
Return exactly one verdict per claim."""


def _normalize_for_match(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _similarity_audit(claim: str, candidates: list[dict]) -> dict:
    best = max(candidates, key=lambda p: p["relevance_score"], default=None)
    score = best["relevance_score"] if best else 0.0
    if score < HARD_THRESHOLD:
        verdict, reason = "unsupported", f"No supporting paper found (best relevance: {score:.1f})"
    elif score < SOFT_THRESHOLD:
        verdict, reason = "partial", f"Weak paper support only (best relevance: {score:.1f})"
    else:
        verdict, reason = "supported", f"Closely matching paper (relevance: {score:.1f})"
    return {
        "verdict": verdict, "reason": reason, "method": "similarity",
        "paper": best if verdict != "unsupported" else None, "quote": "",
    }


def _candidates_for(session_id: str, claim: str, cited_ids: list[str]) -> list[dict]:
    papers = get_papers_by_ids(session_id, cited_ids)
    seen = {p["id"] for p in papers}
    for paper in query_papers(session_id, claim, n_results=CANDIDATES_PER_CLAIM):
        if paper["id"] not in seen:
            seen.add(paper["id"])
            papers.append(paper)
    return papers[: CANDIDATES_PER_CLAIM + 1]


def _llm_audit(session_id: str, claims: list[str], candidates: list[list[dict]]) -> dict[int, dict]:
    """Returns {claim_index: audit} for claims the LLM gave a usable verdict on."""
    ordered: list[dict] = []
    index: dict[str, int] = {}
    for group in candidates:
        for paper in group:
            if paper["id"] not in index and len(ordered) < MAX_PAPERS_IN_PROMPT:
                index[paper["id"]] = len(ordered) + 1
                ordered.append(paper)

    paper_block = "\n\n".join(
        f"[{n}] {p['title']}\nAbstract: {truncate(p.get('abstract', ''), 1200)}"
        for n, p in enumerate(ordered, 1)
    )
    claim_block = "\n".join(
        f"C{i}: {claim} (candidate papers: [{', '.join(str(index[p['id']]) for p in group if p['id'] in index)}])"
        for i, (claim, group) in enumerate(zip(claims, candidates), 1)
    )

    parsed = chat_json(
        messages=[
            {"role": "system", "content": _VERIFY_SYSTEM_PROMPT},
            {"role": "user", "content": f"Papers:\n{paper_block}\n\nClaims:\n{claim_block}"},
        ],
        agent="Fact-Checker",
        session_id=session_id,
        schema=CLAIM_VERIFICATION,
        schema_name="claim_verification",
        temperature=0.1,
        max_tokens=min(600 + 160 * len(claims), 4000),
        required_keys=("verdicts",),
    )

    audits: dict[int, dict] = {}
    for item in parsed.get("verdicts") or []:
        if not isinstance(item, dict):
            continue
        claim_id = as_int(item.get("claim_id"))
        verdict = as_str(item.get("verdict")).lower()
        if claim_id is None or not 1 <= claim_id <= len(claims) or verdict not in _VERDICT_SEVERITY:
            continue
        paper_no = as_int(item.get("paper_id")) or 0
        paper = ordered[paper_no - 1] if 1 <= paper_no <= len(ordered) else None
        quote = as_str(item.get("quote"))
        # Keep only quotes that really appear in the cited abstract
        if quote and (paper is None or _normalize_for_match(quote) not in _normalize_for_match(paper.get("abstract", ""))):
            quote = ""
        reason = as_str(item.get("reason"))
        if verdict in ("supported", "partial", "contradicted") and paper is None:
            verdict = "partial" if verdict == "supported" else verdict
        if verdict == "supported" and not quote:
            # Support the Fact-Checker cannot quote verbatim from the abstract is only partial
            verdict = "partial"
            reason = (reason + " " if reason else "") + "(no verbatim supporting quote found in the abstract)"
        audits[claim_id - 1] = {
            "verdict": verdict,
            "reason": reason,
            "method": "llm",
            "paper": paper,
            "quote": quote,
        }
    return audits


def _flag_reason(audit: dict) -> str:
    paper = audit.get("paper")
    reason = audit.get("reason") or ""
    if audit["method"] == "similarity":
        return reason
    if audit["verdict"] == "contradicted" and paper:
        return f"Contradicted by '{paper['title']}': {reason}".strip()
    if audit["verdict"] == "partial":
        return f"Only partial support: {reason}".strip()
    return f"No retrieved paper supports this claim. {reason}".strip()


def _audit_innovator_claims(state: dict, output: dict) -> tuple[list[dict], list[dict]]:
    session_id: str = state["session_id"]
    claims: list[str] = output.get("claims", [])
    if not claims:
        return [], []
    cited = output.get("claim_citations") or [[] for _ in claims]
    candidates = [_candidates_for(session_id, c, ids) for c, ids in zip(claims, cited)]

    audits: dict[int, dict] = {}
    if get_settings().claim_check == "llm":
        try:
            audits = _llm_audit(session_id, claims, candidates)
        except LLMOutputError as exc:
            print(f"[Fact-Checker] LLM verification failed, using similarity thresholds: {exc}")

    flags: list[dict] = []
    records: list[dict] = []
    for i, claim in enumerate(claims):
        audit = audits.get(i) or _similarity_audit(claim, candidates[i])
        severity = _VERDICT_SEVERITY[audit["verdict"]]
        paper = audit.get("paper")
        records.append({
            "claim": claim,
            "round": output["round"],
            "stage": output.get("stage", "debate"),
            "attempt": output.get("attempt", 0),
            "verdict": audit["verdict"],
            "severity": severity or "none",
            "method": audit["method"],
            "reason": audit.get("reason", ""),
            "quote": audit.get("quote", ""),
            "paper_id": paper["id"] if paper else "",
            "paper_title": paper["title"] if paper else "",
            "paper_url": paper.get("url", "") if paper else "",
        })
        if severity:
            flags.append({
                "claim": claim,
                "agent": "Innovator",
                "round": output["round"],
                "stage": output.get("stage", "debate"),
                "attempt": output.get("attempt", 0),
                "reason": _flag_reason(audit),
                "severity": severity,
                "verdict": audit["verdict"],
            })
    return flags, records


# ------------------------------------------------------------------ #
# Skeptic audit — fabrication check via LLM
# ------------------------------------------------------------------ #

_FABRICATION_SYSTEM_PROMPT = """You are the Fact-Checker agent on the Autonomous Research Council.
Audit the Skeptic's objections for fabricated or dishonest claims.

The Skeptic may attack on logic, and may use facts that appear in the debate context
below (including citation-flag relevance numbers, the chaos constraint, and any
counter-evidence papers it was given). Flag any objection that:
  - Invents a specific statistic, percentage, or study not present in the debate context
  - Claims a paper was retracted or discredited without basis
  - Introduces a concrete external fact the Skeptic could not know from the context

Do NOT flag opinions, logical arguments, or reasonable inferences.

Respond with a JSON object only:
{"fabricated_claims": [{"claim": "The exact objection text.", "reason": "Why this is fabricated."}]}
If nothing is fabricated, return {"fabricated_claims": []}"""


def _audit_skeptic(state: dict, last_output: dict) -> list[dict]:
    round_num = last_output["round"]
    innovator = next(
        (r for r in state.get("round_outputs", [])
         if r["agent"] == "Innovator" and r["round"] == (1 if round_num == 2 else 3)
         and r.get("stage", "debate") == "debate"),
        None,
    )
    context = [f"Innovator's argument:\n{truncate(innovator['content'], 4000) if innovator else ''}"]
    if round_num == 2:
        seen = flags_seen_by_skeptic(state)
        if seen:
            context.append(seen.strip())
    if round_num == 3 and state.get("chaos_constraint"):
        context.append(f"Chaos constraint given to both agents:\n{state['chaos_constraint']}")
    cited_ids = [c["paper_id"] for c in last_output.get("citations", [])]
    for paper in get_papers_by_ids(state["session_id"], cited_ids):
        context.append(f"Counter-evidence paper '{paper['title']}':\n{truncate(paper['abstract'], 900)}")

    claims_text = "\n".join(f"- {c}" for c in last_output.get("claims", []))
    if not claims_text:
        return []
    parsed = chat_json(
        messages=[
            {"role": "system", "content": _FABRICATION_SYSTEM_PROMPT},
            {"role": "user", "content": (
                "Debate context the Skeptic had access to:\n" + "\n\n".join(context) +
                f"\n\nSkeptic's objections to audit:\n{claims_text}"
            )},
        ],
        agent="Fact-Checker",
        session_id=state["session_id"],
        schema=FABRICATION_CHECK,
        schema_name="fabrication_check",
        temperature=0.2,
        max_tokens=1200,
        required_keys=("fabricated_claims",),
    )

    flags = []
    for item in parsed.get("fabricated_claims") or []:
        claim = as_str(item.get("claim")) if isinstance(item, dict) else as_str(item)
        if not claim:
            continue
        flags.append({
            "claim": claim,
            "agent": "Skeptic",
            "round": round_num,
            "reason": (as_str(item.get("reason")) if isinstance(item, dict) else "") or "Fabricated external fact",
            "severity": "hard",
            "verdict": "fabricated",
        })
    return flags


# ------------------------------------------------------------------ #
# Main node
# ------------------------------------------------------------------ #

def run_fact_checker(state: dict) -> dict:
    """
    Audits the most recent RoundOutput (each output is audited exactly once).

    Innovator outputs (rounds 1, 3, 4 and repair rounds):
      each claim gets a verdict — supported / partial / unsupported / contradicted —
      from the LLM against its candidate papers (ARC_CLAIM_CHECK=llm, default), or from
      relevance thresholds (ARC_CLAIM_CHECK=similarity, or if the LLM reply is unusable).
      partial -> soft flag; unsupported/contradicted -> hard flag.

    Skeptic outputs (rounds 2, 3):
      LLM checks objections for fabricated external facts.

    Returns state patch: {"citation_flags", "claim_audits", "round_outputs"}
    """
    round_outputs: list[dict] = state.get("round_outputs", [])
    if not round_outputs or round_outputs[-1].get("audited"):
        return {}

    last_output = round_outputs[-1]
    agent = last_output["agent"]
    round_num = last_output["round"]
    session_id: str = state["session_id"]

    print(f"[Fact-Checker] Auditing {agent} Round {round_num} ({last_output.get('stage', 'debate')}, "
          f"{len(last_output.get('claims', []))} claims)...")

    records: list[dict] = []
    if agent == "Innovator":
        new_flags, records = _audit_innovator_claims(state, last_output)
    elif agent == "Skeptic":
        new_flags = _audit_skeptic(state, last_output)
    else:
        new_flags = []

    hard = sum(1 for f in new_flags if f["severity"] == "hard")
    soft = sum(1 for f in new_flags if f["severity"] == "soft")
    print(f"[Fact-Checker] Round {round_num} audit: {hard} hard, {soft} soft flags.")

    for f in new_flags:
        emit(session_id, "citation_flag", {
            "claim": f["claim"], "agent": f["agent"], "round": f["round"],
            "severity": f["severity"], "verdict": f.get("verdict", ""), "reason": f["reason"],
        })
    if records:
        counts: dict[str, int] = {}
        for r in records:
            counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        emit(session_id, "claims_verified", {"round": round_num, "stage": last_output.get("stage", "debate"),
                                             "counts": counts})

    audited = dict(last_output, audited=True)
    return {
        "citation_flags": state.get("citation_flags", []) + new_flags,
        "claim_audits": state.get("claim_audits", []) + records,
        "round_outputs": round_outputs[:-1] + [audited],
    }
