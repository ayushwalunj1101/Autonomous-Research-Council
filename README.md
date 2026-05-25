# Autonomous Research Council (ARC)

A multi-agent AI system that assembles a council of adversarial agents to debate a research hypothesis, stress-test it against real academic literature, and produce a professional evaluation report with scores and infographics.

---

## What It Does

You submit a research idea (topic, hypothesis, or partial proposal). ARC:

1. Extracts keywords and formulates a clean hypothesis
2. Fetches up to 20 real papers from ArXiv and Semantic Scholar
3. Runs a structured 5-round debate between 8 AI agents
4. Scores the debate quality using a RAGAS faithfulness metric
5. Retries the debate (up to 2×) if quality is too low
6. Generates a PDF evaluation report with novelty, feasibility, and confidence scores

---

## Agent Roster

| Agent | Role |
|---|---|
| **Orchestrator** | Parses user input, extracts keywords, frames the hypothesis |
| **Librarian** | Fetches papers from ArXiv + Semantic Scholar, stores in ChromaDB |
| **Innovator** | Proposes and defends the research direction (Rounds 1, 3, 4) |
| **Skeptic** | Attacks the proposal with logical critiques (Rounds 2, 3) |
| **Fact-Checker** | Audits claims against ChromaDB; flags unsupported assertions |
| **Chaos Agent** | Injects a random real-world constraint (Round 3) |
| **Chairman** | Synthesizes all rounds, computes final scores, produces evaluation JSON |
| **Secretary** | Converts Chairman's JSON into a formatted A4 PDF report |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python) |
| Agent Orchestration | LangGraph |
| LLM | Groq API — `llama-3.3-70b-versatile` |
| Vector Database | ChromaDB (session-namespaced) |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` (local) |
| Paper Sources | ArXiv API + Semantic Scholar API |
| Frontend | Next.js 14 + Apache ECharts |
| Real-time | Server-Sent Events (SSE) |
| PDF Generation | ReportLab |

---

## Project Structure

```
├── backend/
│   ├── agents/          # One file per agent
│   │   ├── orchestrator.py
│   │   ├── librarian.py
│   │   ├── innovator.py
│   │   ├── skeptic.py
│   │   ├── fact_checker.py
│   │   ├── chaos_agent.py
│   │   ├── chairman.py
│   ├── graph/
│   │   └── council_graph.py   # LangGraph StateGraph + retry loop
│   ├── fetchers/
│   │   ├── arxiv_fetcher.py
│   │   └── semantic_scholar.py
│   ├── rag/
│   │   ├── chromadb_client.py
│   │   └── embedder.py
│   ├── scoring/
│   │   └── ragas_scorer.py    # RAGAS faithfulness metric
│   ├── sse/
│   │   └── event_emitter.py   # Per-session asyncio queues
│   ├── pdf/
│   │   └── report_generator.py
│   ├── llm/
│   │   └── client.py
│   └── main.py                # FastAPI app + session endpoints
├── frontend/
│   └── app/
│       ├── page.tsx                          # Input page
│       ├── council/[session_id]/page.tsx     # Live debate feed
│       └── report/[session_id]/page.tsx      # Final report + charts
├── frontend-designs/          # Original design files (reference)
├── requirements.txt
└── .env.example
```

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/ayushwalunj1101/Autonomous-Research-Council.git
cd Autonomous-Research-Council
```

### 2. Backend

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your keys:

```env
GROQ_API_KEY=your_groq_api_key_here
SEMANTIC_SCHOLAR_API_KEY=your_s2_api_key_here   # optional
OPENROUTER_API_KEY=your_openrouter_api_key_here  # optional, for final demo
```

Start the backend:

```bash
uvicorn backend.main:app --reload
```

API runs at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:3000`.

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/session` | Start a session, returns `session_id` immediately (202) |
| `GET` | `/api/session/{id}/stream` | SSE stream — live debate events |
| `GET` | `/api/session/{id}/result` | Final evaluation JSON |
| `GET` | `/api/session/{id}/pdf` | Download PDF report |
| `GET` | `/api/health` | Health check |

### Request body for `/api/session`

```json
{
  "mode": 2,
  "user_input": "Psilocybin-assisted therapy produces more durable remission in treatment-resistant depression than 12 months of standard SSRI pharmacotherapy."
}
```

**Modes:**
- `1` — Research topic (ARC formulates the hypothesis)
- `2` — Full hypothesis (used as-is)
- `3` — Partial proposal / abstract (ARC extracts the core claim)

---

## How the Debate Works

```
User Input
    ↓
Orchestrator → keywords + hypothesis
    ↓
Librarian → fetch papers → ChromaDB
    ↓
┌─────────────── LangGraph Council ───────────────┐
│                                                  │
│  Innovator R1 → Fact-Checker → Skeptic R2       │
│  → Fact-Checker → Chaos Agent (constraint)      │
│  → Innovator R3 → Skeptic R3                    │
│  → Innovator R4 (defense) → Fact-Checker R4     │
│  → Chairman (RAGAS score + evaluation JSON)      │
│       ↓                                          │
│  RAGAS ≥ 0.7 → END                              │
│  RAGAS < 0.7 → retry (max 2×, stricter prompts) │
└──────────────────────────────────────────────────┘
    ↓
PDF Report (novelty / feasibility / confidence scores)
```

### Scoring

| Metric | How it works |
|---|---|
| **RAGAS Faithfulness** | `supported_claims / total_innovator_claims` — claims without a backing paper are hard-flagged and reduce the score |
| **Novelty Score** | Chairman LLM judgment (0–100) |
| **Feasibility Score** | Chairman LLM judgment (0–100) |
| **Research Gap Score** | Chairman LLM judgment (0–100) |
| **Overall Confidence** | Chairman LLM judgment (0–100) |

Fact-Checker thresholds tighten on each retry: `45/60` → `55/70` → `65/80` (hard/soft cutoffs against ChromaDB relevance scores).

---

## Sample Hypotheses to Test

- *"Regular aerobic exercise reduces cardiovascular disease risk in adults over 40"* — well-supported, expect high RAGAS
- *"Remote work increases individual productivity but decreases team collaboration quality"* — contested, good for multi-round debate
- *"Psilocybin-assisted therapy outperforms SSRIs for treatment-resistant depression"* — strong recent literature, recommended for first run
- *"Transformer architectures have reached a scaling ceiling"* — speculative, will challenge the Fact-Checker

---

## License

MIT
