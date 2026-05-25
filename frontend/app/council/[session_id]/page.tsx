"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";

const styles = `
  @import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,400;1,9..144,300&family=Instrument+Sans:wght@400;500;600&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg: #F7F5F0;
    --ink: #0E0E0C;
    --ink-muted: #6B6860;
    --ink-faint: #C4C2BC;
    --amber: #B8935A;
    --amber-light: #F0E6D3;
    --amber-pale: #FAF5EC;
    --border: #E2DFD8;
    --white: #FFFFFF;
    --green: #3A7D5C;
    --green-pale: #EDF5F0;
    --red: #C0503A;
    --red-pale: #FAF0EE;
    --chaos: #2C3E6B;
    --chaos-pale: #EEF0F8;
    --chaos-border: #8B9BC4;
  }

  body { background: var(--bg); font-family: 'Instrument Sans', sans-serif; color: var(--ink); }

  .dot-grid {
    position: fixed; inset: 0;
    background-image: radial-gradient(circle, rgba(14,14,12,0.07) 1px, transparent 1px);
    background-size: 28px 28px;
    pointer-events: none; z-index: 0;
  }

  .layout {
    position: relative; z-index: 1;
    display: grid;
    grid-template-columns: 260px 1fr;
    grid-template-rows: 64px 1fr;
    min-height: 100vh;
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 24px;
  }

  /* ── Header ── */
  .topbar {
    grid-column: 1 / -1;
    display: flex; align-items: center; justify-content: space-between;
    border-bottom: 1px solid var(--border);
    padding: 0 4px;
  }

  .logo { display: flex; align-items: center; gap: 10px; }
  .logo-mark {
    width: 26px; height: 26px; border: 1.5px solid var(--amber);
    border-radius: 6px; display: flex; align-items: center; justify-content: center;
  }
  .logo-mark::before { content: ''; width: 9px; height: 9px; background: var(--amber); border-radius: 2px; }
  .logo-text { font-size: 13px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }

  .topbar-center {
    display: flex; align-items: center; gap: 10px;
    font-size: 13px; color: var(--ink-muted);
  }

  .session-chip {
    font-size: 11px; font-weight: 600; letter-spacing: 0.06em;
    background: var(--white); border: 1px solid var(--border);
    padding: 4px 10px; border-radius: 20px; color: var(--ink-muted);
    text-transform: uppercase;
  }

  .live-dot {
    width: 7px; height: 7px; border-radius: 50%; background: var(--green);
    animation: pulse 1.5s ease-in-out infinite;
  }
  .live-dot.done { background: var(--amber); animation: none; }
  .live-dot.idle { background: var(--ink-faint); animation: none; }

  .live-label { font-size: 11px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--green); }
  .live-label.done { color: var(--amber); }
  .live-label.idle { color: var(--ink-faint); }

  /* ── Sidebar ── */
  .sidebar {
    border-right: 1px solid var(--border);
    padding: 28px 20px 28px 4px;
    display: flex; flex-direction: column; gap: 28px;
  }

  .sidebar-section-label {
    font-size: 10px; font-weight: 600; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--ink-faint); margin-bottom: 10px;
  }

  /* Round tracker */
  .rounds-list { display: flex; flex-direction: column; gap: 2px; }

  .round-item {
    display: flex; align-items: center; gap: 10px;
    padding: 9px 12px; border-radius: 8px;
    transition: all 0.2s ease; cursor: default;
  }

  .round-item.active {
    background: var(--amber-pale);
    border: 1px solid var(--amber-light);
  }

  .round-item.complete { opacity: 0.6; }
  .round-item.pending { opacity: 0.35; }

  .round-icon {
    width: 22px; height: 22px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 10px; font-weight: 700; flex-shrink: 0;
    border: 1.5px solid var(--border);
    color: var(--ink-faint);
    transition: all 0.3s ease;
  }

  .round-item.active .round-icon {
    background: var(--amber); border-color: var(--amber);
    color: white; animation: iconPulse 1.5s ease-in-out infinite;
  }

  .round-item.complete .round-icon {
    background: var(--ink); border-color: var(--ink); color: white;
  }

  .round-chaos .round-icon {
    background: var(--chaos) !important; border-color: var(--chaos) !important;
  }

  .round-name { font-size: 12px; font-weight: 600; color: var(--ink); }
  .round-agents { font-size: 11px; color: var(--ink-muted); }

  /* Stats panel */
  .stats-grid { display: flex; flex-direction: column; gap: 8px; }

  .stat-item {
    background: var(--white); border: 1px solid var(--border);
    border-radius: 8px; padding: 10px 12px;
  }

  .stat-label { font-size: 10px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-faint); margin-bottom: 4px; }
  .stat-value { font-family: 'Fraunces', serif; font-size: 22px; font-weight: 400; color: var(--ink); line-height: 1; }
  .stat-value.amber { color: var(--amber); }
  .stat-value.green { color: var(--green); }

  /* ── Main feed ── */
  .feed-area {
    padding: 28px 0 28px 28px;
    display: flex; flex-direction: column;
    min-height: 0; overflow: hidden;
  }

  .feed-header {
    display: flex; align-items: flex-start; justify-content: space-between;
    margin-bottom: 22px;
  }

  .feed-title { font-family: 'Fraunces', serif; font-size: 22px; font-weight: 300; color: var(--ink); }
  .feed-title em { font-style: italic; color: var(--amber); }

  .hypothesis-chip {
    max-width: 380px;
    font-size: 12px; color: var(--ink-muted);
    background: var(--white); border: 1px solid var(--border);
    padding: 8px 14px; border-radius: 8px; line-height: 1.4;
    font-style: italic;
  }

  /* Event stream */
  .event-stream {
    flex: 1;
    overflow-y: auto;
    display: flex; flex-direction: column; gap: 8px;
    padding-right: 8px;
    max-height: calc(100vh - 180px);
    scroll-behavior: smooth;
  }

  .event-stream::-webkit-scrollbar { width: 4px; }
  .event-stream::-webkit-scrollbar-track { background: transparent; }
  .event-stream::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }

  /* Event cards */
  .event-card {
    display: flex; gap: 12px; align-items: flex-start;
    padding: 12px 16px;
    border-radius: 10px;
    border: 1px solid var(--border);
    background: var(--white);
    animation: slideIn 0.35s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    opacity: 0; transform: translateY(8px);
  }

  .event-card.type-success { border-color: rgba(58,125,92,0.2); background: var(--green-pale); }
  .event-card.type-warning { border-color: rgba(184,147,90,0.3); background: var(--amber-pale); }
  .event-card.type-flag { border-color: rgba(192,80,58,0.25); background: var(--red-pale); }
  .event-card.type-round { border-color: var(--border); background: var(--white); }
  .event-card.type-system { border-color: var(--border); background: var(--bg); }

  /* CHAOS card — special treatment */
  .event-card.type-chaos {
    border-color: var(--chaos-border);
    background: var(--chaos-pale);
    position: relative; overflow: hidden;
    padding: 16px 18px;
  }

  .event-card.type-chaos::before {
    content: '';
    position: absolute; top: 0; left: 0; right: 0; height: 3px;
    background: linear-gradient(90deg, var(--chaos), var(--chaos-border), var(--chaos));
    animation: shimmer 2s ease-in-out infinite;
  }

  .event-icon {
    width: 28px; height: 28px; border-radius: 7px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    font-size: 13px; background: var(--bg); border: 1px solid var(--border);
  }

  .event-card.type-success .event-icon { background: #D4EDDA; border-color: rgba(58,125,92,0.2); }
  .event-card.type-flag .event-icon { background: #FAE0DA; border-color: rgba(192,80,58,0.2); }
  .event-card.type-chaos .event-icon { background: rgba(44,62,107,0.12); border-color: var(--chaos-border); font-size: 16px; }
  .event-card.type-warning .event-icon { background: var(--amber-light); border-color: rgba(184,147,90,0.3); }

  .event-body { flex: 1; min-width: 0; }

  .event-meta {
    display: flex; align-items: center; gap: 8px; margin-bottom: 4px;
  }

  .event-agent {
    font-size: 11px; font-weight: 700; letter-spacing: 0.06em;
    text-transform: uppercase; color: var(--ink);
  }

  .event-card.type-success .event-agent { color: var(--green); }
  .event-card.type-flag .event-agent { color: var(--red); }
  .event-card.type-chaos .event-agent { color: var(--chaos); }
  .event-card.type-warning .event-agent { color: var(--amber); }

  .event-time { font-size: 10px; color: var(--ink-faint); }

  .event-text {
    font-size: 13px; line-height: 1.55; color: var(--ink-muted);
  }

  .event-card.type-chaos .event-text {
    font-size: 14px; color: var(--chaos); font-weight: 500;
  }

  .chaos-label {
    display: inline-block;
    font-size: 10px; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: white;
    background: var(--chaos); padding: 3px 8px; border-radius: 4px;
    margin-bottom: 8px;
  }

  .citation-tag {
    display: inline-block;
    font-size: 11px; color: var(--amber);
    background: var(--amber-pale); border: 1px solid var(--amber-light);
    padding: 2px 8px; border-radius: 4px; margin-top: 6px;
    font-weight: 500;
  }

  /* RAGAS reveal */
  .ragas-card {
    border: 1.5px solid var(--amber);
    background: linear-gradient(135deg, var(--amber-pale), var(--white));
    border-radius: 12px; padding: 18px 20px;
    display: flex; align-items: center; gap: 20px;
    animation: slideIn 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    opacity: 0; transform: translateY(8px);
  }

  .ragas-score-display {
    font-family: 'Fraunces', serif;
    font-size: 42px; font-weight: 400; color: var(--amber); line-height: 1;
    flex-shrink: 0;
  }

  .ragas-info { flex: 1; }
  .ragas-title { font-size: 13px; font-weight: 700; color: var(--ink); letter-spacing: 0.02em; margin-bottom: 4px; }
  .ragas-desc { font-size: 12px; color: var(--ink-muted); line-height: 1.5; }

  .ragas-badge {
    font-size: 11px; font-weight: 700; letter-spacing: 0.06em;
    text-transform: uppercase; padding: 5px 12px; border-radius: 20px;
    background: var(--green); color: white;
  }
  .ragas-badge.fail { background: var(--red); }

  /* Report ready banner */
  .report-ready {
    border: 1.5px solid var(--ink);
    background: var(--ink);
    border-radius: 12px; padding: 18px 20px;
    display: flex; align-items: center; justify-content: space-between;
    gap: 16px;
    animation: slideIn 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    opacity: 0; transform: translateY(8px);
  }

  .report-ready-text { flex: 1; }
  .report-ready-title { font-family: 'Fraunces', serif; font-size: 16px; font-weight: 300; color: white; margin-bottom: 2px; }
  .report-ready-title em { font-style: italic; color: var(--amber); }
  .report-ready-sub { font-size: 12px; color: rgba(255,255,255,0.5); }

  .view-report-btn {
    display: flex; align-items: center; gap: 8px;
    background: var(--amber); color: white;
    border: none; border-radius: 8px;
    padding: 10px 18px;
    font-family: 'Instrument Sans', sans-serif;
    font-size: 13px; font-weight: 600; cursor: pointer;
    transition: all 0.2s ease; white-space: nowrap;
  }

  .view-report-btn:hover { background: #A07848; transform: translateY(-1px); }

  /* Typing indicator */
  .typing-indicator {
    display: flex; align-items: center; gap: 10px;
    padding: 12px 16px; opacity: 0.6;
    animation: fadeIn 0.3s ease forwards;
  }

  .typing-dots { display: flex; gap: 4px; align-items: center; }
  .typing-dot {
    width: 5px; height: 5px; border-radius: 50%;
    background: var(--ink-faint);
    animation: typingBounce 1.2s ease-in-out infinite;
  }
  .typing-dot:nth-child(2) { animation-delay: 0.15s; }
  .typing-dot:nth-child(3) { animation-delay: 0.3s; }
  .typing-agent { font-size: 12px; color: var(--ink-faint); font-style: italic; }

  /* Progress bar at top */
  .progress-bar-track {
    position: fixed; top: 64px; left: 0; right: 0;
    height: 2px; background: var(--border); z-index: 10;
  }

  .progress-bar-fill {
    height: 100%; background: var(--amber);
    transition: width 0.6s ease;
  }

  /* Animations */
  @keyframes slideIn { to { opacity: 1; transform: translateY(0); } }
  @keyframes fadeIn { to { opacity: 1; } }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
  @keyframes iconPulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(184,147,90,0.4); } 50% { box-shadow: 0 0 0 5px rgba(184,147,90,0); } }
  @keyframes shimmer { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
  @keyframes typingBounce { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-3px); } }
`;

// ── Round definitions ─────────────────────────────────────────────────────────
const ROUNDS = [
  { label: "Opening",   agents: "Innovator · Fact-Checker", chaos: false },
  { label: "Rebuttal",  agents: "Skeptic · Fact-Checker",   chaos: false },
  { label: "Chaos",     agents: "All Agents",               chaos: true  },
  { label: "Defense",   agents: "Innovator · Fact-Checker", chaos: false },
  { label: "Consensus", agents: "Chairman",                  chaos: false },
];

// Round number (1-5) → sidebar index (0-4)
const ROUND_NUM_TO_SIDEBAR: Record<number, number> = { 1: 0, 2: 1, 3: 2, 4: 3, 5: 4 };
const ROUND_ICONS = ["①", "②", "③", "④", "⑤"];
const ROUND_LABELS = ["Opening", "Rebuttal", "Chaos Response", "Defense", "Consensus"];

function timestamp() {
  return new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

interface FeedEvent {
  id: number;
  type: "success" | "warning" | "flag" | "round" | "system" | "chaos";
  icon: string;
  agent: string;
  text: string;
  tag?: string | null;
  time: string;
}

// ── Component ─────────────────────────────────────────────────────────────────
export default function CouncilPage() {
  const params = useParams<{ session_id: string }>();
  const router = useRouter();
  const sessionId = params.session_id;

  const [events, setEvents] = useState<FeedEvent[]>([]);
  const [activeRound, setActiveRound] = useState(0);
  const [completedRounds, setCompletedRounds] = useState<number[]>([]);
  const [status, setStatus] = useState<"live" | "done" | "idle">("idle");
  const [isTyping, setIsTyping] = useState(false);
  const [typingAgent, setTypingAgent] = useState("");
  const [papersCount, setPapersCount] = useState(0);
  const [flagCount, setFlagCount] = useState(0);
  const [ragasScore, setRagasScore] = useState<number | null>(null);
  const [ragasPassed, setRagasPassed] = useState(true);
  const [reportReady, setReportReady] = useState(false);
  const [progress, setProgress] = useState(0);
  const [hypothesis, setHypothesis] = useState<string | null>(null);

  const streamRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectDelay = useRef(1500);
  const isDoneRef = useRef(false);
  const eventIdCounter = useRef(0);

  // ── Helpers ─────────────────────────────────────────────────────────────────

  function addEvent(ev: Omit<FeedEvent, "id" | "time">) {
    setEvents(prev => [...prev, { ...ev, id: eventIdCounter.current++, time: timestamp() }]);
  }

  function completeRoundsUpTo(sidebarIdx: number) {
    setCompletedRounds(prev => {
      const next = new Set(prev);
      for (let i = 0; i < sidebarIdx; i++) next.add(i);
      return Array.from(next);
    });
  }

  // ── SSE event handlers ───────────────────────────────────────────────────────

  const handlePapersLoaded = useCallback((data: { papers_loaded: number; reused_cache: boolean }) => {
    setPapersCount(data.papers_loaded);
    setProgress(10);
    addEvent({
      type: "success", icon: "✓", agent: "Librarian",
      text: `Fetched ${data.papers_loaded} papers from ArXiv and Semantic Scholar.${data.reused_cache ? " (cache reused)" : ""}`,
    });
    addEvent({
      type: "success", icon: "✓", agent: "Librarian",
      text: "Knowledge base ready. ChromaDB collection created for this session.",
    });
  }, []);

  const handleRoundStart = useCallback((data: { round: number; agent: string }) => {
    const sidebarIdx = ROUND_NUM_TO_SIDEBAR[data.round] ?? 0;
    setActiveRound(sidebarIdx);
    completeRoundsUpTo(sidebarIdx);
    setIsTyping(true);
    setTypingAgent(data.agent);

    // Add round announcement card for first visit to each sidebar round
    if (data.round === 1 || data.round === 2 || data.round === 4) {
      const label = ROUND_LABELS[data.round - 1] ?? `Round ${data.round}`;
      const agentLabel = `Round ${data.round}`;
      addEvent({
        type: "round",
        icon: ROUND_ICONS[data.round - 1] ?? String(data.round),
        agent: agentLabel,
        text: `${label} — ${data.agent} ${data.round === 2 ? "analysing Innovator's argument" : data.round === 4 ? "addressing all objections" : "proposing research direction"}.`,
      });
    }
  }, []);

  const handleRoundComplete = useCallback((data: { round: number; agent: string; summary: string }) => {
    setIsTyping(false);
    setTypingAgent("");

    addEvent({
      type: "success", icon: "✓", agent: data.agent,
      text: data.summary,
    });

    setProgress(prev => Math.min(prev + 15, 80));
  }, []);

  const handleChaosInjection = useCallback((data: { constraint: string }) => {
    setIsTyping(false);
    setActiveRound(2); // Chaos sidebar index
    completeRoundsUpTo(2);
    setProgress(55);
    addEvent({
      type: "chaos", icon: "⚡", agent: "Chaos Agent",
      text: data.constraint,
    });
  }, []);

  const handleCitationFlag = useCallback((data: { claim: string; agent: string }) => {
    setFlagCount(f => f + 1);
    addEvent({
      type: "flag", icon: "⚑", agent: "Fact-Checker",
      text: `Citation Flag on ${data.agent} — "${data.claim}" is not supported by any retrieved paper.`,
    });
  }, []);

  const handleRagasScore = useCallback((data: { score: number; passed: boolean }) => {
    setRagasScore(data.score);
    setRagasPassed(data.passed);
    setActiveRound(4); // Consensus
    setCompletedRounds([0, 1, 2, 3]);
    setProgress(90);
    addEvent({
      type: "round", icon: "⑤", agent: "Round 5",
      text: "Consensus — Chairman synthesising debate and computing scores.",
    });
  }, []);

  const handleRetry = useCallback((data: { attempt: number; reason: string }) => {
    setActiveRound(0);
    setCompletedRounds([]);
    setProgress(10);
    setRagasScore(null);
    addEvent({
      type: "warning", icon: "↺", agent: "System",
      text: `RAGAS below threshold — starting retry ${data.attempt}/2. ${data.reason}`,
    });
  }, []);

  const handleReportReady = useCallback(async (sid: string) => {
    setReportReady(true);
    setStatus("done");
    setProgress(100);
    setActiveRound(-1);
    setCompletedRounds([0, 1, 2, 3, 4]);
    isDoneRef.current = true;
    esRef.current?.close();

    // Fetch result to populate hypothesis chip, then auto-navigate to report
    try {
      const res = await fetch(`/api/session/${sid}/result`);
      if (res.ok) {
        const data = await res.json();
        const h = data.evaluation_json?.refined_hypothesis ?? null;
        if (h) setHypothesis(h);
      }
    } catch {
      // non-critical
    }

    // Auto-navigate to report after a short pause so user sees the "complete" state
    setTimeout(() => {
      router.push(`/report/${sid}`);
    }, 2000);
  }, [router]);

  const handleError = useCallback((data: { message: string }) => {
    setStatus("idle");
    addEvent({
      type: "flag", icon: "✗", agent: "System",
      text: `Pipeline error: ${data.message}`,
    });
  }, []);

  // ── SSE connection ───────────────────────────────────────────────────────────

  const connectSSE = useCallback(() => {
    if (isDoneRef.current) return;
    if (esRef.current) esRef.current.close();

    const url = `http://localhost:8000/api/session/${sessionId}/stream`;
    const es = new EventSource(url);
    esRef.current = es;

    es.onopen = () => {
      if (!isDoneRef.current) {
        setStatus("live");
        reconnectDelay.current = 1500; // reset backoff on successful connection
      }
    };

    es.onerror = () => {
      if (isDoneRef.current) return;
      setStatus("idle");
      es.close();
      // Exponential backoff reconnect — EventSource Last-Event-ID replay handled by server
      const delay = Math.min(reconnectDelay.current, 30_000);
      reconnectDelay.current = delay * 2;
      reconnectTimer.current = setTimeout(connectSSE, delay);
    };

    es.addEventListener("papers_loaded", (e: MessageEvent) => {
      handlePapersLoaded(JSON.parse(e.data));
    });

    es.addEventListener("round_start", (e: MessageEvent) => {
      handleRoundStart(JSON.parse(e.data));
    });

    es.addEventListener("round_complete", (e: MessageEvent) => {
      handleRoundComplete(JSON.parse(e.data));
    });

    es.addEventListener("chaos_injection", (e: MessageEvent) => {
      handleChaosInjection(JSON.parse(e.data));
    });

    es.addEventListener("citation_flag", (e: MessageEvent) => {
      handleCitationFlag(JSON.parse(e.data));
    });

    es.addEventListener("ragas_score", (e: MessageEvent) => {
      handleRagasScore(JSON.parse(e.data));
    });

    es.addEventListener("retry", (e: MessageEvent) => {
      handleRetry(JSON.parse(e.data));
    });

    es.addEventListener("report_ready", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      handleReportReady(data.session_id ?? sessionId);
    });

    es.addEventListener("error_event", (e: MessageEvent) => {
      // Named "error_event" to avoid clashing with the built-in "error" event
      handleError(JSON.parse(e.data));
    });

    // The backend emits event type "error" — wire separately
    es.addEventListener("error", (e: MessageEvent) => {
      // Only handle message events (not connection errors, which fire on es.onerror)
      if (e instanceof MessageEvent) {
        handleError(JSON.parse(e.data));
      }
    });

    es.addEventListener("keepalive", () => {
      // no-op — just keeps connection alive
    });
  }, [sessionId, handlePapersLoaded, handleRoundStart, handleRoundComplete,
      handleChaosInjection, handleCitationFlag, handleRagasScore,
      handleRetry, handleReportReady, handleError]);

  useEffect(() => {
    if (!sessionId) return;

    // Reset state refs for this mount (React StrictMode mounts twice in dev)
    isDoneRef.current = false;
    reconnectDelay.current = 1500;

    // Check session validity before connecting SSE
    fetch(`/api/session/${sessionId}/result`)
      .then(res => {
        if (res.status === 404) {
          // Session not found (server restarted or invalid ID) — go home
          router.replace("/");
        } else {
          // 200 (complete) or 202 (running) — connect SSE either way
          connectSSE();
        }
      })
      .catch(() => connectSSE());

    return () => {
      isDoneRef.current = true;
      esRef.current?.close();
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    };
  }, [sessionId, connectSSE, router]);

  // ── Auto-scroll ──────────────────────────────────────────────────────────────
  useEffect(() => {
    if (streamRef.current) {
      streamRef.current.scrollTop = streamRef.current.scrollHeight;
    }
  }, [events, isTyping, ragasScore, reportReady]);

  // ── Render ───────────────────────────────────────────────────────────────────
  const sessionChip = sessionId ? sessionId.slice(0, 8).toUpperCase() : "——";
  const reportSubText = [
    "All 5 rounds complete",
    ragasScore !== null ? `RAGAS ${ragasScore.toFixed(2)}` : null,
    papersCount > 0 ? `${papersCount} papers cited` : null,
  ].filter(Boolean).join(" · ");

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: styles }} />
      <div className="dot-grid" />

      {/* Progress bar */}
      <div className="progress-bar-track">
        <div className="progress-bar-fill" style={{ width: `${progress}%` }} />
      </div>

      <div className="layout">

        {/* ── Top bar ── */}
        <header className="topbar">
          <div className="logo">
            <div className="logo-mark" />
            <span className="logo-text">Research Council</span>
          </div>
          <div className="topbar-center">
            <div className={`live-dot ${status}`} />
            <span className={`live-label ${status}`}>
              {status === "live" ? "Debate live" : status === "done" ? "Complete" : "Connecting…"}
            </span>
            <span style={{ color: "var(--ink-faint)", fontSize: 12 }}>·</span>
            <span className="session-chip">Session #{sessionChip}</span>
          </div>
          <div style={{ width: 180 }} />
        </header>

        {/* ── Sidebar ── */}
        <aside className="sidebar">
          {/* Rounds */}
          <div>
            <div className="sidebar-section-label">Debate Rounds</div>
            <div className="rounds-list">
              {ROUNDS.map((r, i) => (
                <div
                  key={i}
                  className={`round-item ${r.chaos ? "round-chaos" : ""} ${
                    activeRound === i ? "active" :
                    completedRounds.includes(i) ? "complete" : "pending"
                  }`}
                >
                  <div className="round-icon">
                    {completedRounds.includes(i) ? "✓" : i + 1}
                  </div>
                  <div>
                    <div className="round-name">{r.label}</div>
                    <div className="round-agents">{r.agents}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Stats */}
          <div>
            <div className="sidebar-section-label">Session Stats</div>
            <div className="stats-grid">
              <div className="stat-item">
                <div className="stat-label">Papers Loaded</div>
                <div className={`stat-value ${papersCount > 0 ? "amber" : ""}`}>
                  {papersCount > 0 ? papersCount : "—"}
                </div>
              </div>
              <div className="stat-item">
                <div className="stat-label">Flags Raised</div>
                <div className={`stat-value ${flagCount > 0 ? "amber" : ""}`}>
                  {flagCount > 0 ? flagCount : "—"}
                </div>
              </div>
              <div className="stat-item">
                <div className="stat-label">RAGAS Score</div>
                <div className={`stat-value ${ragasScore !== null ? "green" : ""}`}>
                  {ragasScore !== null ? ragasScore.toFixed(2) : "—"}
                </div>
              </div>
            </div>
          </div>
        </aside>

        {/* ── Main feed ── */}
        <main className="feed-area">
          <div className="feed-header">
            <div>
              <div className="feed-title">
                Council <em>in session</em>
              </div>
            </div>
            <div className="hypothesis-chip">
              {hypothesis ?? "Awaiting hypothesis…"}
            </div>
          </div>

          <div className="event-stream" ref={streamRef}>
            {events.map(ev => (
              ev.type === "chaos" ? (
                <div key={ev.id} className="event-card type-chaos">
                  <div className="event-icon">{ev.icon}</div>
                  <div className="event-body">
                    <div className="chaos-label">⚡ Chaos Injection</div>
                    <div className="event-text">{ev.text}</div>
                    <div className="event-time" style={{ marginTop: 6 }}>{ev.time}</div>
                  </div>
                </div>
              ) : (
                <div key={ev.id} className={`event-card type-${ev.type}`}>
                  <div className="event-icon">{ev.icon}</div>
                  <div className="event-body">
                    <div className="event-meta">
                      <span className="event-agent">{ev.agent}</span>
                      <span className="event-time">{ev.time}</span>
                    </div>
                    <div className="event-text">{ev.text}</div>
                    {ev.tag && <div className="citation-tag">📎 {ev.tag}</div>}
                  </div>
                </div>
              )
            ))}

            {/* Typing indicator */}
            {isTyping && (
              <div className="typing-indicator">
                <div className="typing-dots">
                  <div className="typing-dot" />
                  <div className="typing-dot" />
                  <div className="typing-dot" />
                </div>
                <span className="typing-agent">{typingAgent} is thinking…</span>
              </div>
            )}

            {/* RAGAS reveal */}
            {ragasScore !== null && (
              <div className="ragas-card">
                <div className="ragas-score-display">{ragasScore.toFixed(2)}</div>
                <div className="ragas-info">
                  <div className="ragas-title">RAGAS Faithfulness Score</div>
                  <div className="ragas-desc">
                    {Math.round(ragasScore * 100)}% of claims are supported by retrieved papers.
                    {ragasPassed
                      ? " Threshold passed — proceeding to report generation."
                      : " Below threshold — low confidence flag set."}
                  </div>
                </div>
                <div className={`ragas-badge ${ragasPassed ? "" : "fail"}`}>
                  {ragasPassed ? "Passed ✓" : "Failed ✗"}
                </div>
              </div>
            )}

            {/* Report ready */}
            {reportReady && (
              <div className="report-ready">
                <div className="report-ready-text">
                  <div className="report-ready-title">Your <em>evaluation report</em> is ready</div>
                  <div className="report-ready-sub">{reportSubText}</div>
                </div>
                <button
                  className="view-report-btn"
                  onClick={() => router.push(`/report/${sessionId}`)}
                >
                  View Report →
                </button>
              </div>
            )}
          </div>
        </main>

      </div>
    </>
  );
}
