# Autonomous Research Council (ARC)

A multi-agent AI system that assembles a council of adversarial agents to debate a research hypothesis, stress-test it against real academic literature, and produce a professional evaluation report with scores and infographics.

---

## What It Does

You submit a research idea (topic, hypothesis, or partial proposal). ARC:

1. Extracts keywords and formulates a clean hypothesis — which you can review and edit before anything else runs
2. Fetches candidate papers from arXiv, OpenAlex, Semantic Scholar (and PubMed for biomedical topics), ranks them by similarity to the hypothesis and keeps the best 20 — optionally letting you remove papers or add your own (arXiv ID, DOI or PDF)
3. Runs a structured 5-round debate between 8 AI agents
4. Checks every factual claim against the paper abstracts (supported / partial / unsupported / contradicted, with a quote)
5. Scores faithfulness with a RAGAS-style metric; if it is below 0.7, the Innovator must revise or retract the unverified claims (up to 2 repair rounds)
6. Produces a report with median scores and their range across independent Chairman passes, a claim-evidence table, the full transcript, and PDF / Markdown / Word / BibTeX exports

---

## Agent Roster

| Agent | Role |
|---|---|
| **Orchestrator** | Parses user input, extracts keywords, frames the hypothesis and research domain |
| **Librarian** | Fetches and reranks papers from arXiv, OpenAlex, Semantic Scholar, PubMed; stores them in ChromaDB |
| **Innovator** | Proposes and defends the research direction (Rounds 1, 3, 4) and repairs flagged claims |
| **Skeptic** | Attacks the proposal with logical critiques (Rounds 2, 3); optionally cites counter-evidence |
| **Fact-Checker** | Gives every Innovator claim an evidence verdict; checks the Skeptic for fabricated facts (every round) |
| **Chaos Agent** | Injects the most relevant real-world constraint from its pool, or one you chose (Round 3) |
| **Chairman** | Synthesizes all rounds, scores against an anchored rubric (median of 3 passes), produces the evaluation JSON |
| **Secretary** | Converts the evaluation JSON into the PDF report and exports |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python) |
| Agent Orchestration | LangGraph |
| LLM | OpenRouter — default `anthropic/claude-sonnet-5.5` (configurable per agent); Groq `llama-3.3-70b-versatile` optional |
| Structured output | JSON-schema structured outputs + tolerant parser + repair retry |
| Vector Database | ChromaDB (session-namespaced) |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` (local) |
| Paper Sources | arXiv, OpenAlex, Semantic Scholar, PubMed |
| Session store | SQLite (`sessions/arc.db`) — sessions survive restarts |
| Frontend | Next.js 14 + Apache ECharts |
| Real-time | Server-Sent Events (SSE) with resumable replay |
| Reports | ReportLab (PDF), python-docx (Word), Markdown, BibTeX |

---

## Project Structure

```
├── backend/
│   ├── agents/               # One file per agent (+ common.py shared helpers)
│   ├── graph/council_graph.py  # LangGraph StateGraph + repair loop
│   ├── fetchers/             # arxiv, openalex, semantic_scholar, pubmed, documents (PDF/DOCX text)
│   ├── rag/                  # chromadb_client.py, embedder.py
│   ├── llm/
│   │   ├── client.py         # providers, structured outputs, retries, fallback, budget, logging
│   │   ├── json_utils.py     # tolerant JSON extraction
│   │   ├── schemas.py        # JSON schemas + normalizers for every agent reply
│   │   ├── usage.py          # per-session cost tracking + JSONL call logs
│   │   └── mock_provider.py  # offline LLM for tests and UI work
│   ├── scoring/              # ragas_scorer.py, evaluation.py (builds/normalizes the report JSON)
│   ├── store/session_store.py  # SQLite sessions
│   ├── sse/event_emitter.py  # per-subscriber SSE fan-out + replay buffer
│   ├── pdf/report_generator.py
│   ├── export/exporters.py   # Markdown, BibTeX, DOCX
│   ├── config.py             # all ARC_* settings
│   └── main.py               # FastAPI app + endpoints
├── frontend/
│   ├── lib/api.ts            # backend URL, typed fetch helpers
│   └── app/
│       ├── page.tsx                      # Input + confirm step + recent sessions
│       ├── council/[session_id]/page.tsx # Live debate feed + paper review
│       ├── report/[session_id]/page.tsx  # Report, claim audit, transcript, exports
│       └── compare/page.tsx              # Two runs side by side
├── tests/                    # pytest suite (runs offline with the mock LLM)
├── requirements.txt / requirements-dev.txt
└── .env.example
```

---

## Setup

### 1. Backend

```bash
pip install -r requirements.txt
cp .env.example .env      # then add your OPENROUTER_API_KEY
uvicorn backend.main:app --reload
```

API runs at `http://localhost:8000` (docs at `/docs`). The startup log prints the provider, model and per-session cost limit.

**Cost:** with Claude Sonnet 5.5 a measured run costs about $0.24 (14 LLM calls, ~2.5 minutes), plus ~$0.11 per repair round; `ARC_SESSION_BUDGET_USD` (default $0.50) hard-stops a session. To cut cost ~35%, set `ARC_SCORING_SAMPLES=1` and `ARC_MODEL_FACT_CHECKER=deepseek/deepseek-v3.2`. For development set `ARC_MODEL=deepseek/deepseek-v3.2` (~$0.005/run) or `ARC_LLM_PROVIDER=mock` (free, offline, deterministic). Every LLM call is logged to `logs/<session_id>.jsonl`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:3000`. Set `NEXT_PUBLIC_API_BASE` (see `frontend/.env.example`) if the backend is not on `localhost:8000`.

### 3. Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```

The suite runs fully offline (mock LLM, temp ChromaDB/SQLite) and covers the JSON parser (built from real failure logs), the LLM client's retry/fallback/budget logic, the full debate graph including repair rounds, the PDF/exports with hostile text, and every API endpoint including SSE replay.

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/session/prepare` | Runs the Orchestrator; returns `{session_id, hypothesis, keywords, domain}` for review |
| `POST` | `/api/session/{id}/start` | Starts the debate with edited hypothesis/keywords, `review_papers`, optional `chaos_constraint` (202) |
| `POST` | `/api/session` | One-shot: prepare + start in the background (202) |
| `GET` | `/api/session/{id}/stream` | SSE stream; resume with `Last-Event-ID` or `?last_event_id=` |
| `GET` | `/api/session/{id}/papers` | Current paper set |
| `POST` | `/api/session/{id}/papers` | Add a paper `{identifier}` (arXiv ID/URL or DOI) during review |
| `POST` | `/api/session/{id}/papers/upload` | Add a PDF paper during review |
| `POST` | `/api/session/{id}/papers/confirm` | `{remove_ids}` — finish review and start the debate |
| `POST` | `/api/session/{id}/cancel` | Stop a queued/running session |
| `GET` | `/api/session/{id}/result` | Final evaluation JSON (202 with status while running) |
| `GET` | `/api/session/{id}/transcript` | Every round's full text, claims, flags and verdicts |
| `GET` | `/api/session/{id}/pdf` | PDF report (rebuilt on demand if missing) |
| `GET` | `/api/session/{id}/export/{markdown\|docx\|bibtex}` | Other export formats |
| `GET` | `/api/sessions?limit=20` | Recent sessions (history / compare) |
| `POST` | `/api/extract-text` | Text from an uploaded PDF/DOCX/TXT proposal |
| `GET` | `/api/health` | Health + active provider/model/budget |

**Modes:** `1` research topic · `2` hypothesis (used as-is) · `3` partial proposal / abstract.

---

## How the Debate Works

```
User Input → Orchestrator → [you confirm/edit hypothesis + keywords]
    ↓
Librarian → arXiv + OpenAlex + S2 (+ PubMed) → rerank → top 20 → ChromaDB
    ↓                                   (0 papers → broaden once → fail fast)
[optional: you review the papers]
    ↓
┌──────────────────── LangGraph Council ────────────────────┐
│  Innovator R1 → Fact-Checker → Skeptic R2 → Fact-Checker  │
│  → Chaos Agent → Innovator R3 → Fact-Checker              │
│  → Skeptic R3 → Fact-Checker → Innovator R4 → Fact-Checker│
│  → Chairman (RAGAS + 3 scoring passes + evaluation JSON)   │
│       ↓                                                    │
│  RAGAS ≥ 0.7 → END                                         │
│  RAGAS < 0.7 → repair: Innovator revises/retracts flagged  │
│               claims → Fact-Checker → Chairman (max 2×)    │
└────────────────────────────────────────────────────────────┘
    ↓
Report (best attempt) → PDF / Markdown / Word / BibTeX
```

`ARC_RETRY_MODE=full` restores the original behaviour of re-running the whole debate on a retry.

### Scoring

| Metric | How it works |
|---|---|
| **RAGAS Faithfulness** | `supported / standing Innovator claims`; unsupported or contradicted claims are hard-flagged, partial support is a soft flag (still counts as supported); retracted/revised claims leave the denominator; zero claims scores 0 |
| **Claim verdicts** | Fact-Checker judges each claim against its candidate abstracts and must quote the supporting sentence (quotes are verified verbatim); `ARC_CLAIM_CHECK=similarity` uses the legacy 45/60 relevance thresholds |
| **Novelty / Feasibility / Research Gap / Overall** | Chairman judgement against an anchored rubric, informed by computed signals (nearest-paper similarity, claim verdict counts); median of `ARC_SCORING_SAMPLES` passes, range shown |

---

## Sample Hypotheses to Test

- *"Regular aerobic exercise reduces cardiovascular disease risk in adults over 40"* — well-supported, expect high RAGAS
- *"Remote work increases individual productivity but decreases team collaboration quality"* — contested, good for multi-round debate
- *"Psilocybin-assisted therapy outperforms SSRIs for treatment-resistant depression"* — strong recent literature, recommended for first run
- *"Transformer architectures have reached a scaling ceiling"* — speculative, will challenge the Fact-Checker

---

## License

MIT
