import { useState, useEffect, useRef } from "react";

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

// ── Mock event sequence (replace with real SSE) ──────────────────────────────
const MOCK_EVENTS = [
  { delay: 600,  type: "system",  icon: "📡", agent: "System",       text: "Session initialised. Connecting to Knowledge Forge..." },
  { delay: 1400, type: "success", icon: "✓",  agent: "Librarian",    text: "Fetched 18 papers from ArXiv and Semantic Scholar.", tag: null },
  { delay: 2200, type: "success", icon: "✓",  agent: "Librarian",    text: "Knowledge base ready. ChromaDB collection created for this session.", tag: null },
  { delay: 3000, type: "round",   icon: "①",  agent: "Round 1",      text: "Opening — Innovator proposing research direction." },
  { delay: 4200, type: "success", icon: "✓",  agent: "Innovator",    text: "Hypothesis refined: Federated learning with differential privacy can reduce re-identification risk in multi-hospital ML pipelines by 62%, while retaining model accuracy within 4% of centralised baselines.", tag: "4 citations" },
  { delay: 5400, type: "flag",    icon: "⚑",  agent: "Fact-Checker", text: "Citation Flag on Claim 2 — '62% risk reduction' is not supported by any retrieved paper. Flagged for Innovator acknowledgement.", tag: null },
  { delay: 6400, type: "warning", icon: "↩",  agent: "Innovator",    text: "Acknowledged Flag on Claim 2. Retracting the 62% figure — replacing with qualitative reduction pending empirical validation.", tag: null },
  { delay: 7200, type: "round",   icon: "②",  agent: "Round 2",      text: "Rebuttal — Skeptic analysing Innovator's argument." },
  { delay: 8600, type: "flag",    icon: "✗",  agent: "Skeptic",      text: "Objection 1: Methodology assumes IID data distribution across hospitals — a well-documented false assumption in clinical datasets.", tag: null },
  { delay: 9400, type: "flag",    icon: "✗",  agent: "Skeptic",      text: "Objection 2: No proposed mechanism for hyperparameter tuning across federated nodes without central coordination.", tag: null },
  { delay: 10200,type: "flag",    icon: "✗",  agent: "Skeptic",      text: "Objection 3: Privacy budget ε is not defined — renders any differential privacy claim non-falsifiable.", tag: null },
  { delay: 11000,type: "success", icon: "✓",  agent: "Fact-Checker", text: "Skeptic audit complete — all 3 objections are logically grounded. No fabricated weaknesses detected.", tag: null },
  { delay: 12000,type: "chaos",   icon: "⚡", agent: "Chaos Agent",  text: "Assume the primary training dataset has 35% label noise due to inconsistent annotation protocols across hospital sites." },
  { delay: 13400,type: "round",   icon: "③",  agent: "Round 3",      text: "Agents adapting to chaos constraint..." },
  { delay: 14600,type: "warning", icon: "↺",  agent: "Innovator",    text: "Chaos response: Proposing label-noise-robust aggregation using FedProx with μ=0.01 and noise-aware loss weighting. Benchmark on MIMIC-III with synthetic noise injection.", tag: null },
  { delay: 15800,type: "round",   icon: "④",  agent: "Round 4",      text: "Defense — Innovator addressing all objections." },
  { delay: 17200,type: "success", icon: "✓",  agent: "Innovator",    text: "Addressed Objection 1: Proposing personalized federated learning (pFedMe) to handle non-IID distributions. Addressed Objection 3: Setting ε = 1.0, δ = 1e-5 as privacy budget.", tag: "3 citations" },
  { delay: 18400,type: "success", icon: "✓",  agent: "Fact-Checker", text: "Final audit complete. All remaining claims are citation-backed. 0 unresolved flags.", tag: null },
  { delay: 19400,type: "round",   icon: "⑤",  agent: "Round 5",      text: "Chairman synthesising debate and computing scores..." },
];

const ROUNDS = [
  { label: "Opening",     agents: "Innovator · Fact-Checker", chaos: false },
  { label: "Rebuttal",    agents: "Skeptic · Fact-Checker",   chaos: false },
  { label: "Chaos",       agents: "All Agents",               chaos: true  },
  { label: "Defense",     agents: "Innovator · Fact-Checker", chaos: false },
  { label: "Consensus",   agents: "Chairman",                  chaos: false },
];

function timestamp() {
  return new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function DebateFeed() {
  const [events, setEvents] = useState([]);
  const [activeRound, setActiveRound] = useState(0);
  const [completedRounds, setCompletedRounds] = useState([]);
  const [status, setStatus] = useState("live"); // live | done | idle
  const [isTyping, setIsTyping] = useState(false);
  const [typingAgent, setTypingAgent] = useState("");
  const [papersCount, setPapersCount] = useState(0);
  const [flagCount, setFlagCount] = useState(0);
  const [ragasScore, setRagasScore] = useState(null);
  const [reportReady, setReportReady] = useState(false);
  const [progress, setProgress] = useState(0);
  const streamRef = useRef(null);
  const timers = useRef([]);

  useEffect(() => {
    let eventIdx = 0;

    MOCK_EVENTS.forEach((ev, i) => {
      const t1 = setTimeout(() => {
        setIsTyping(true);
        setTypingAgent(ev.agent);
      }, ev.delay - 600);

      const t2 = setTimeout(() => {
        setIsTyping(false);
        setEvents(prev => [...prev, { ...ev, id: i, time: timestamp() }]);
        setProgress(Math.round(((i + 1) / (MOCK_EVENTS.length + 3)) * 100));

        if (ev.type === "success" && ev.agent === "Librarian" && ev.text.includes("18")) setPapersCount(18);
        if (ev.type === "flag" && ev.agent === "Fact-Checker" && ev.text.includes("Flag")) setFlagCount(f => f + 1);
        if (ev.type === "flag" && ev.agent === "Skeptic") setFlagCount(f => f + 1);

        if (ev.agent.startsWith("Round")) {
          const rNum = parseInt(ev.agent.split(" ")[1]) - 1;
          setActiveRound(rNum);
          setCompletedRounds(prev => {
            const next = [...prev];
            if (rNum > 0 && !next.includes(rNum - 1)) next.push(rNum - 1);
            return next;
          });
        }
      }, ev.delay);

      timers.current.push(t1, t2);
    });

    // RAGAS reveal
    const t3 = setTimeout(() => {
      setRagasScore(0.86);
      setCompletedRounds([0, 1, 2, 3, 4]);
      setActiveRound(-1);
      setProgress(95);
    }, 20600);

    // Report ready
    const t4 = setTimeout(() => {
      setReportReady(true);
      setStatus("done");
      setProgress(100);
    }, 22000);

    timers.current.push(t3, t4);

    return () => timers.current.forEach(clearTimeout);
  }, []);

  // Auto-scroll
  useEffect(() => {
    if (streamRef.current) {
      streamRef.current.scrollTop = streamRef.current.scrollHeight;
    }
  }, [events, isTyping, ragasScore, reportReady]);

  return (
    <>
      <style>{styles}</style>
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
              {status === "live" ? "Debate live" : status === "done" ? "Complete" : "Idle"}
            </span>
            <span style={{ color: "var(--ink-faint)", fontSize: 12 }}>·</span>
            <span className="session-chip">Session #A3F8</span>
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
                <div className={`stat-value ${ragasScore ? "green" : ""}`}>
                  {ragasScore ? ragasScore.toFixed(2) : "—"}
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
              "Federated learning can reduce patient data privacy risks in cross-hospital ML models"
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
            {ragasScore && (
              <div className="ragas-card">
                <div className="ragas-score-display">{ragasScore.toFixed(2)}</div>
                <div className="ragas-info">
                  <div className="ragas-title">RAGAS Faithfulness Score</div>
                  <div className="ragas-desc">
                    {Math.round(ragasScore * 100)}% of claims are supported by retrieved papers.
                    Threshold passed — proceeding to report generation.
                  </div>
                </div>
                <div className={`ragas-badge ${ragasScore >= 0.7 ? "" : "fail"}`}>
                  {ragasScore >= 0.7 ? "Passed ✓" : "Failed ✗"}
                </div>
              </div>
            )}

            {/* Report ready */}
            {reportReady && (
              <div className="report-ready">
                <div className="report-ready-text">
                  <div className="report-ready-title">Your <em>evaluation report</em> is ready</div>
                  <div className="report-ready-sub">All 5 rounds complete · RAGAS 0.86 · 18 papers cited</div>
                </div>
                <button
                  className="view-report-btn"
                  onClick={() => alert("Navigate to /report/A3F8")}
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
