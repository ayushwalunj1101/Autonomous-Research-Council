# The Autonomous Research Council

## What this project is
A multi-agent AI system where a council of adversarial agents debates 
a user's research hypothesis, stress-tests it, and outputs a 
professional evaluation report with infographics.

## Full implementation plan
See ARC_Implementation_Plan.docx in project root for complete details.
Always read it before making architectural decisions.

## Tech Stack
- Backend: FastAPI + LangGraph (Python)
- LLM: Groq API (env: GROQ_API_KEY) → OpenRouter for final demo
- Groq base_url: https://api.groq.com/openai/v1
- Model: llama-3.3-70b-versatile
- Vector DB: ChromaDB (session-namespaced by uuid4)
- Embeddings: sentence-transformers (local, no API cost)
- Paper Sources: ArXiv API + Semantic Scholar API
- Frontend: Next.js + Apache ECharts
- Real-time: Server-Sent Events (SSE)
- PDF: ReportLab

## Agent Roster
1. Orchestrator — mode routing + keyword extraction
2. Librarian — paper fetching + ChromaDB storage
3. Innovator — hypothesis + argument (Round 1, 4)
4. Skeptic — logical critique (Round 2)
5. Fact-Checker — citation auditing (all rounds)
6. Chaos Agent — constraint injection (Round 3)
7. Chairman — consensus + scoring + evaluation JSON
8. Secretary — PDF generation

## Key Rules
- ChromaDB collections namespaced by session_id
- Max 20 papers per session
- All agents are separate files in backend/agents/
- LangGraph state schema lives in graph/council_graph.py
- Max 2 debate retries on RAGAS < 0.7
- Chairman produces single JSON — source of truth for entire output
- Never build beyond the current phase without explicit instruction




## Current Phase
Phase 5 — Frontend Integration
Phases 1-4 complete — backend fully working.

## Frontend Files
Three designed pages are ready in /frontend-designs/ folder:
- InputPage.jsx → integrate as frontend/app/page.tsx
- DebateFeed.jsx → integrate as frontend/app/council/[session_id]/page.tsx  
- ReportPage.html → convert and integrate as frontend/app/report/[session_id]/page.tsx

Do NOT redesign or restyle these files. Only wire up backend connections.