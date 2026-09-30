"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  apiJson, apiUrl, formatCost, postFile, postJson,
  type PaperSummary, type SessionResult,
} from "@/lib/api";

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

  /* Topbar actions */
  .topbar-actions { width: 180px; display: flex; justify-content: flex-end; }
  .stop-btn {
    font-family: 'Instrument Sans', sans-serif; font-size: 12px; font-weight: 600;
    color: var(--red); background: var(--red-pale); border: 1px solid rgba(192,80,58,0.25);
    padding: 7px 14px; border-radius: 8px; cursor: pointer; transition: all 0.2s ease;
  }
  .stop-btn:hover:not(:disabled) { background: #F5E0DB; }
  .stop-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .home-link {
    font-size: 12px; font-weight: 600; color: var(--ink-muted); text-decoration: none;
    border: 1px solid var(--border); background: var(--white); padding: 7px 14px; border-radius: 8px;
  }
  .home-link:hover { color: var(--amber); border-color: var(--amber-light); }

  /* Expandable full text */
  .expand-btn {
    background: none; border: none; padding: 0; margin-top: 6px;
    font-family: 'Instrument Sans', sans-serif; font-size: 11px; font-weight: 600;
    color: var(--amber); cursor: pointer; letter-spacing: 0.02em;
  }
  .event-full {
    white-space: pre-wrap; margin-top: 8px; padding-top: 8px;
    font-size: 13px; line-height: 1.6; color: var(--ink-muted);
    border-top: 1px dashed var(--border);
  }

  /* Paper review */
  .review-card {
    border: 1.5px solid var(--amber); background: var(--white);
    border-radius: 12px; padding: 18px 20px;
    animation: slideIn 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    opacity: 0; transform: translateY(8px);
  }
  .review-title { font-family: 'Fraunces', serif; font-size: 18px; font-weight: 300; margin-bottom: 4px; }
  .review-title em { font-style: italic; color: var(--amber); }
  .review-sub { font-size: 12px; color: var(--ink-muted); margin-bottom: 14px; line-height: 1.5; }
  .paper-list {
    display: flex; flex-direction: column; gap: 6px;
    max-height: 360px; overflow-y: auto; padding-right: 4px; margin-bottom: 14px;
  }
  .paper-row {
    display: flex; gap: 10px; align-items: flex-start;
    padding: 9px 10px; border: 1px solid var(--border); border-radius: 8px;
    background: var(--bg); cursor: pointer; transition: opacity 0.2s ease;
  }
  .paper-row.excluded { opacity: 0.45; }
  .paper-row input { accent-color: var(--amber); margin-top: 3px; flex-shrink: 0; }
  .paper-info { flex: 1; min-width: 0; }
  .paper-title { font-size: 12px; font-weight: 600; color: var(--ink); line-height: 1.4; }
  .paper-title a { color: inherit; text-decoration: none; }
  .paper-title a:hover { color: var(--amber); }
  .paper-meta { font-size: 11px; color: var(--ink-muted); margin-top: 2px; }
  .relevance-badge { font-family: 'Fraunces', serif; font-size: 14px; color: var(--amber); flex-shrink: 0; }
  .review-add { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
  .review-input {
    flex: 1; min-width: 200px; background: var(--bg); border: 1.5px solid var(--border);
    border-radius: 8px; padding: 8px 12px; font-family: 'Instrument Sans', sans-serif;
    font-size: 13px; color: var(--ink); outline: none;
  }
  .review-input:focus { border-color: var(--amber); background: var(--white); }
  .small-btn {
    font-family: 'Instrument Sans', sans-serif; font-size: 12px; font-weight: 600;
    padding: 8px 14px; border-radius: 8px; cursor: pointer; white-space: nowrap;
    border: 1px solid var(--border); background: var(--white); color: var(--ink);
    transition: all 0.2s ease;
  }
  .small-btn:hover:not(:disabled) { border-color: var(--amber); color: var(--amber); }
  .small-btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .review-error { font-size: 12px; color: var(--red); margin-bottom: 10px; }
  .review-actions { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
  .review-count { font-size: 12px; color: var(--ink-muted); }

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

// Every pipeline event carries an id; these two are sent without one
const EVENTS_WITHOUT_ID = new Set(["keepalive", "session_status"]);
const SSE_EVENTS = [
  "session_info", "queued", "papers_loaded", "papers_confirmed", "review_timeout",
  "round_start", "round_complete", "claims_verified", "citation_flag", "chaos_injection",
  "ragas_score", "retry", "retry_skipped", "pdf_failed", "report_ready", "pipeline_error",
  "cancelled", "session_status", "keepalive",
];

const VERDICT_LABELS: Record<string, string> = {
  unsupported: "Unsupported claim",
  contradicted: "Contradicted claim",
  partial: "Weak support",
  fabricated: "Fabricated fact",
};

function timestamp() {
  return new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

interface FeedEvent {
  id: number;
  type: "success" | "warning" | "flag" | "round" | "system" | "chaos";
  icon: string;
  agent: string;
  text: string;
  detail?: string;
  tag?: string | null;
  time: string;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type EventData = Record<string, any>;

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
  const [spend, setSpend] = useState(0);
  const [finished, setFinished] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [expanded, setExpanded] = useState<number[]>([]);

  // Paper review (between retrieval and debate)
  const [reviewPapers, setReviewPapers] = useState<PaperSummary[] | null>(null);
  const [excluded, setExcluded] = useState<string[]>([]);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [addInput, setAddInput] = useState("");

  const streamRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectDelay = useRef(1500);
  const isDoneRef = useRef(false);
  const lastEventIdRef = useRef(-1);
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

  function finish(nextStatus: "done" | "idle") {
    isDoneRef.current = true;
    setFinished(true);
    setStatus(nextStatus);
    setIsTyping(false);
    setReviewPapers(null);
    esRef.current?.close();
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
  }

  const goToReport = useCallback((sid: string, delayMs: number) => {
    setTimeout(() => router.push(`/report/${sid}`), delayMs);
  }, [router]);

  // ── SSE event handling (one dispatcher; kept in a ref so reconnects never use stale state) ──

  function handleEvent(name: string, data: EventData) {
    switch (name) {
      case "session_info": {
        if (data.hypothesis) setHypothesis(data.hypothesis);
        addEvent({
          type: "system", icon: "◎", agent: "Orchestrator",
          text: `Council convened${data.model ? ` · model ${data.model}` : ""}${data.budget_usd ? ` · cost limit $${Number(data.budget_usd).toFixed(2)}` : ""}.`,
        });
        setIsTyping(true);
        setTypingAgent("Librarian");
        setProgress(4);
        break;
      }
      case "queued":
        addEvent({ type: "warning", icon: "…", agent: "System",
          text: `Waiting for a free council chamber (position ${data.position ?? 1}). Other debates are running.` });
        break;

      case "papers_loaded": {
        const count = Number(data.count ?? 0);
        setPapersCount(count);
        setProgress(10);
        setIsTyping(false);
        const sources = data.sources && Object.keys(data.sources).length
          ? Object.entries(data.sources as Record<string, number>).map(([k, v]) => `${v} ${k.replace("_", " ")}`).join(", ")
          : "";
        addEvent({
          type: "success", icon: "✓", agent: "Librarian",
          text: `Fetched ${count} papers${sources ? ` (${sources})` : ""}${data.candidates ? `, ranked from ${data.candidates} candidates by relevance to the hypothesis` : ""}.${data.reused_cache ? " (cache reused)" : ""}`,
        });
        if (data.awaiting_review && Array.isArray(data.papers)) {
          setReviewPapers(data.papers as PaperSummary[]);
          setExcluded([]);
        } else {
          addEvent({ type: "success", icon: "✓", agent: "Librarian",
            text: "Knowledge base ready. ChromaDB collection created for this session." });
        }
        break;
      }
      case "papers_confirmed":
        setReviewPapers(null);
        setPapersCount(Number(data.count ?? 0));
        addEvent({ type: "success", icon: "✓", agent: "Librarian", text: `Debate will use ${data.count} papers.` });
        break;
      case "review_timeout":
        setReviewPapers(null);
        addEvent({ type: "warning", icon: "…", agent: "System", text: data.message ?? "Review timed out — continuing." });
        break;

      case "round_start": {
        const round = Number(data.round);
        const sidebarIdx = ROUND_NUM_TO_SIDEBAR[round] ?? 0;
        setActiveRound(sidebarIdx);
        completeRoundsUpTo(sidebarIdx);
        setIsTyping(true);
        setTypingAgent(data.agent);
        if (data.stage === "repair") {
          setProgress(85);
          addEvent({ type: "round", icon: "↻", agent: `Repair ${data.attempt ?? ""}`.trim(),
            text: "Innovator is revising or retracting the claims the Fact-Checker could not verify." });
        } else if (round === 1 || round === 2 || round === 4) {
          const label = ROUND_LABELS[round - 1] ?? `Round ${round}`;
          addEvent({
            type: "round",
            icon: ROUND_ICONS[round - 1] ?? String(round),
            agent: `Round ${round}`,
            text: `${label} — ${data.agent} ${round === 2 ? "analysing Innovator's argument" : round === 4 ? "addressing all objections" : "proposing research direction"}.`,
          });
        }
        break;
      }
      case "round_complete": {
        setIsTyping(false);
        setTypingAgent("");
        if (typeof data.cost_usd === "number") setSpend(data.cost_usd);
        const content: string = data.content ?? "";
        const summary: string = data.summary ?? "";
        const parts = [
          typeof data.claims === "number" ? `${data.claims} ${data.agent === "Skeptic" ? "objections" : "claims"}` : null,
          data.citations ? `${data.citations} paper${data.citations === 1 ? "" : "s"} cited` : null,
          data.retracted ? `${data.retracted} retracted` : null,
        ].filter(Boolean);
        addEvent({
          type: "success", icon: "✓", agent: data.stage === "repair" ? "Innovator · repair" : data.agent,
          text: summary || content,
          detail: content && content.length > summary.length ? content : undefined,
          tag: parts.length ? parts.join(" · ") : null,
        });
        setProgress(prev => Math.min(prev + 12, 80));
        break;
      }
      case "claims_verified": {
        const counts = (data.counts ?? {}) as Record<string, number>;
        const text = ["supported", "partial", "unsupported", "contradicted"]
          .filter(k => counts[k]).map(k => `${counts[k]} ${k}`).join(" · ");
        if (text) {
          addEvent({ type: "system", icon: "⚖", agent: "Fact-Checker",
            text: `${data.stage === "repair" ? "Repaired claims" : `Round ${data.round} claims`} checked against the paper abstracts: ${text}.` });
        }
        break;
      }
      case "citation_flag": {
        const verdict = VERDICT_LABELS[data.verdict] ?? "Citation flag";
        const text = `${verdict} on ${data.agent}: “${data.claim}”${data.reason ? ` — ${data.reason}` : ""}`;
        if (data.severity === "soft") {
          addEvent({ type: "warning", icon: "△", agent: "Fact-Checker", text });
        } else {
          setFlagCount(f => f + 1);
          addEvent({ type: "flag", icon: "⚑", agent: "Fact-Checker", text });
        }
        break;
      }
      case "chaos_injection":
        setIsTyping(false);
        setActiveRound(2);
        completeRoundsUpTo(2);
        setProgress(55);
        addEvent({
          type: "chaos", icon: "⚡", agent: "Chaos Agent", text: data.constraint,
          tag: data.selected_by === "user" ? "your constraint" : data.selected_by === "llm" ? "chosen as most relevant" : null,
        });
        break;

      case "ragas_score":
        setRagasScore(Number(data.score));
        setRagasPassed(Boolean(data.passed));
        setActiveRound(4);
        setCompletedRounds([0, 1, 2, 3]);
        setProgress(90);
        setIsTyping(true);
        setTypingAgent("Chairman");
        addEvent({
          type: "round", icon: "⑤", agent: data.attempt ? `Round 5 · attempt ${Number(data.attempt) + 1}` : "Round 5",
          text: "Consensus — Chairman synthesising debate and computing scores.",
        });
        break;

      case "retry":
        setRagasScore(null);
        if (data.mode === "full") {
          setActiveRound(0);
          setCompletedRounds([]);
          setProgress(10);
          addEvent({ type: "warning", icon: "↺", agent: "System",
            text: `RAGAS below threshold — restarting the debate (retry ${data.attempt}/${data.max_attempts ?? 2}). ${data.reason ?? ""}` });
        } else {
          setActiveRound(3);
          addEvent({ type: "warning", icon: "↺", agent: "System",
            text: `${data.reason ?? "RAGAS below threshold"} — repair round ${data.attempt}/${data.max_attempts ?? 2}: ${data.flagged_claims ?? "the"} flagged claims go back to the Innovator.` });
        }
        break;
      case "retry_skipped":
        addEvent({ type: "system", icon: "·", agent: "System", text: `No further repair: ${data.reason ?? ""}` });
        break;
      case "pdf_failed":
        addEvent({ type: "warning", icon: "!", agent: "Secretary",
          text: "The PDF could not be generated. The report page and the Markdown/Word exports are still available." });
        break;

      case "report_ready": {
        if (typeof data.cost_usd === "number") setSpend(data.cost_usd);
        setReportReady(true);
        setProgress(100);
        setActiveRound(-1);
        setCompletedRounds([0, 1, 2, 3, 4]);
        finish("done");
        const sid = data.session_id ?? sessionId;
        apiJson<SessionResult>(`/api/session/${sid}/result`)
          .then(res => { if (res.evaluation_json?.refined_hypothesis) setHypothesis(res.evaluation_json.refined_hypothesis); })
          .catch(() => { /* non-critical */ });
        goToReport(sid, 2500);
        break;
      }
      case "pipeline_error":
        addEvent({ type: "flag", icon: "✗", agent: "System", text: `Pipeline error: ${data.message}` });
        finish("idle");
        break;
      case "cancelled":
        addEvent({ type: "warning", icon: "■", agent: "System", text: data.message ?? "The debate was stopped." });
        finish("idle");
        break;
      case "session_status":
        // Sent when the server has no live stream for this session (finished earlier or restarted)
        if (data.status === "complete") {
          finish("done");
          goToReport(sessionId, 0);
        } else if (data.status === "error") {
          addEvent({ type: "flag", icon: "✗", agent: "System", text: `Pipeline error: ${data.error || "the session failed."}` });
          finish("idle");
        } else if (data.status === "cancelled") {
          addEvent({ type: "warning", icon: "■", agent: "System", text: "This debate was stopped." });
          finish("idle");
        } else if (data.status === "awaiting_confirmation" || data.status === "discarded") {
          addEvent({ type: "system", icon: "·", agent: "System", text: "This session was prepared but never started." });
          finish("idle");
        }
        break;
      default:
        break;
    }
  }

  const handlerRef = useRef(handleEvent);
  handlerRef.current = handleEvent;

  // ── SSE connection ───────────────────────────────────────────────────────────

  const connectSSE = useCallback(() => {
    if (isDoneRef.current) return;
    if (esRef.current) esRef.current.close();

    // EventSource cannot set Last-Event-ID on a new connection, so resume via query param
    const es = new EventSource(apiUrl(`/api/session/${sessionId}/stream?last_event_id=${lastEventIdRef.current}`));
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
      // Exponential backoff reconnect; the server replays everything after lastEventIdRef
      const delay = Math.min(reconnectDelay.current, 30_000);
      reconnectDelay.current = delay * 2;
      reconnectTimer.current = setTimeout(connectSSE, delay);
    };

    for (const name of SSE_EVENTS) {
      es.addEventListener(name, (e: Event) => {
        const msg = e as MessageEvent;
        if (!EVENTS_WITHOUT_ID.has(name)) {
          const id = Number(msg.lastEventId);
          if (msg.lastEventId !== "" && !isNaN(id)) {
            if (id <= lastEventIdRef.current) return; // already applied (replay overlap)
            lastEventIdRef.current = id;
          }
        }
        if (name === "keepalive") return;
        let data: EventData = {};
        try {
          data = JSON.parse(msg.data);
        } catch {
          return;
        }
        handlerRef.current(name, data);
      });
    }
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) return;

    // Reset state refs for this mount (React StrictMode mounts twice in dev)
    isDoneRef.current = false;
    reconnectDelay.current = 1500;

    fetch(apiUrl(`/api/session/${sessionId}/result`))
      .then(async res => {
        if (res.status === 404) {
          router.replace("/"); // unknown session id
          return;
        }
        if (res.status === 200) {
          router.replace(`/report/${sessionId}`); // already finished
          return;
        }
        if (res.status === 202) {
          const body = await res.json().catch(() => ({}));
          if (body.hypothesis) setHypothesis(body.hypothesis);
        }
        // 202 (running), 409 (cancelled) and 500 (failed): the stream replays what happened
        connectSSE();
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
  }, [events, isTyping, ragasScore, reportReady, reviewPapers]);

  // ── Actions ──────────────────────────────────────────────────────────────────

  async function stopDebate() {
    setStopping(true);
    try {
      await postJson(`/api/session/${sessionId}/cancel`, {});
    } catch (err: unknown) {
      addEvent({ type: "flag", icon: "✗", agent: "System", text: err instanceof Error ? err.message : "Could not stop the debate." });
      setStopping(false);
    }
  }

  async function addPaper() {
    const identifier = addInput.trim();
    if (!identifier) return;
    setReviewBusy(true);
    setReviewError(null);
    try {
      // Unticked papers are dropped first, so adding works at the 20-paper cap
      const res = await postJson<{ papers: PaperSummary[] }>(`/api/session/${sessionId}/papers`, {
        identifier, remove_ids: excluded,
      });
      setReviewPapers(res.papers);
      setExcluded([]);
      setAddInput("");
    } catch (err: unknown) {
      setReviewError(err instanceof Error ? err.message : "Could not add that paper.");
    } finally {
      setReviewBusy(false);
    }
  }

  async function uploadPaper(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setReviewBusy(true);
    setReviewError(null);
    try {
      const res = await postFile<{ papers: PaperSummary[] }>(
        `/api/session/${sessionId}/papers/upload`, file, { remove_ids: excluded.join(",") },
      );
      setReviewPapers(res.papers);
      setExcluded([]);
    } catch (err: unknown) {
      setReviewError(err instanceof Error ? err.message : "Could not read that PDF.");
    } finally {
      setReviewBusy(false);
    }
  }

  async function confirmPapers() {
    setReviewBusy(true);
    setReviewError(null);
    try {
      await postJson(`/api/session/${sessionId}/papers/confirm`, { remove_ids: excluded });
      setReviewPapers(null);
      setIsTyping(true);
      setTypingAgent("Innovator");
    } catch (err: unknown) {
      setReviewError(err instanceof Error ? err.message : "Could not start the debate.");
    } finally {
      setReviewBusy(false);
    }
  }

  function toggleExcluded(id: string) {
    setExcluded(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  }

  function toggleExpanded(id: number) {
    setExpanded(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  }

  // ── Render ───────────────────────────────────────────────────────────────────
  const sessionChip = sessionId ? sessionId.slice(0, 8).toUpperCase() : "——";
  const reportSubText = [
    "All rounds complete",
    ragasScore !== null ? `RAGAS ${ragasScore.toFixed(2)}` : null,
    papersCount > 0 ? `${papersCount} papers retrieved` : null,
    spend > 0 ? `${formatCost(spend)} spent` : null,
  ].filter(Boolean).join(" · ");
  const keptPapers = reviewPapers ? reviewPapers.length - excluded.length : 0;

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
              {status === "live" ? "Debate live" : status === "done" ? "Complete" : finished ? "Stopped" : "Connecting…"}
            </span>
            <span style={{ color: "var(--ink-faint)", fontSize: 12 }}>·</span>
            <span className="session-chip">Session #{sessionChip}</span>
          </div>
          <div className="topbar-actions">
            {finished ? (
              <a className="home-link" href="/">New session</a>
            ) : (
              <button className="stop-btn" onClick={stopDebate} disabled={stopping}>
                {stopping ? "Stopping…" : "■ Stop debate"}
              </button>
            )}
          </div>
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
              <div className="stat-item">
                <div className="stat-label">LLM Spend</div>
                <div className="stat-value">{spend > 0 ? formatCost(spend) : "—"}</div>
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
                    {ev.tag && <div className="citation-tag">{ev.tag}</div>}
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
                    {ev.detail && (
                      <>
                        <button className="expand-btn" onClick={() => toggleExpanded(ev.id)}>
                          {expanded.includes(ev.id) ? "Hide full argument ▲" : "Show full argument ▼"}
                        </button>
                        {expanded.includes(ev.id) && <div className="event-full">{ev.detail}</div>}
                      </>
                    )}
                  </div>
                </div>
              )
            ))}

            {/* Paper review — the user curates the corpus before any debate tokens are spent */}
            {reviewPapers && (
              <div className="review-card">
                <div className="review-title">Review the <em>papers</em></div>
                <div className="review-sub">
                  The debate is paused. Untick papers that are off-topic, or add your own by arXiv ID, DOI or PDF. Every claim will be checked against this set.
                </div>
                <div className="paper-list">
                  {reviewPapers.map(p => (
                    <label key={p.id} className={`paper-row ${excluded.includes(p.id) ? "excluded" : ""}`}>
                      <input type="checkbox" checked={!excluded.includes(p.id)} onChange={() => toggleExcluded(p.id)} />
                      <div className="paper-info">
                        <div className="paper-title">
                          {p.url ? <a href={p.url} target="_blank" rel="noreferrer">{p.title}</a> : p.title}
                        </div>
                        <div className="paper-meta">
                          {[p.authors, p.year, p.source.replace("_", " "), p.user_added ? "added by you" : ""].filter(Boolean).join(" · ")}
                        </div>
                      </div>
                      <span className="relevance-badge" title="Similarity to the hypothesis (0-100)">{Math.round(p.relevance)}</span>
                    </label>
                  ))}
                </div>
                <div className="review-add">
                  <input
                    className="review-input"
                    value={addInput}
                    placeholder="arXiv ID (2401.01234) or DOI (10.1038/…)"
                    onChange={e => setAddInput(e.target.value)}
                    onKeyDown={e => { if (e.key === "Enter") addPaper(); }}
                  />
                  <button className="small-btn" onClick={addPaper} disabled={reviewBusy || !addInput.trim()}>Add paper</button>
                  <label className="small-btn" style={{ opacity: reviewBusy ? 0.45 : 1 }}>
                    Upload PDF
                    <input type="file" accept=".pdf" hidden disabled={reviewBusy} onChange={uploadPaper} />
                  </label>
                </div>
                {reviewError && <div className="review-error">{reviewError}</div>}
                <div className="review-actions">
                  <span className="review-count">{keptPapers} of {reviewPapers.length} papers selected</span>
                  <button className="view-report-btn" onClick={confirmPapers} disabled={reviewBusy || keptPapers === 0}>
                    Begin debate →
                  </button>
                </div>
              </div>
            )}

            {/* Typing indicator */}
            {isTyping && !reviewPapers && (
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
                    {Math.round(ragasScore * 100)}% of standing claims are supported by retrieved papers.
                    {ragasPassed
                      ? " Threshold passed — proceeding to report generation."
                      : " Below threshold — flagged claims go to a repair round (max 2), otherwise the low-confidence flag is set."}
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
