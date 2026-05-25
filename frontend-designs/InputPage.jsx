import { useState, useEffect } from "react";

const styles = `
  @import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,400;0,9..144,500;1,9..144,300&family=Instrument+Sans:wght@400;500;600&display=swap');

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
    --card-hover: #FDFCFA;
    --selected-border: #B8935A;
    --selected-bg: #FDF8F1;
  }

  body {
    background: var(--bg);
    font-family: 'Instrument Sans', sans-serif;
    color: var(--ink);
    min-height: 100vh;
  }

  .page-wrapper {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    background: var(--bg);
    background-image:
      radial-gradient(circle at 15% 20%, rgba(184,147,90,0.06) 0%, transparent 50%),
      radial-gradient(circle at 85% 80%, rgba(184,147,90,0.04) 0%, transparent 50%);
  }

  /* Dot grid overlay */
  .dot-grid {
    position: fixed;
    inset: 0;
    background-image: radial-gradient(circle, rgba(14,14,12,0.08) 1px, transparent 1px);
    background-size: 28px 28px;
    pointer-events: none;
    z-index: 0;
  }

  .content {
    position: relative;
    z-index: 1;
    flex: 1;
    display: flex;
    flex-direction: column;
    max-width: 780px;
    margin: 0 auto;
    padding: 0 32px;
    width: 100%;
  }

  /* Header */
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 28px 0 0;
    opacity: 0;
    transform: translateY(-8px);
    animation: fadeUp 0.5s ease forwards;
  }

  .logo {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .logo-mark {
    width: 28px;
    height: 28px;
    border: 1.5px solid var(--amber);
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
  }

  .logo-mark::before {
    content: '';
    width: 10px;
    height: 10px;
    background: var(--amber);
    border-radius: 2px;
  }

  .logo-text {
    font-family: 'Instrument Sans', sans-serif;
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink);
  }

  .header-badge {
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--ink-muted);
    background: var(--white);
    border: 1px solid var(--border);
    padding: 5px 12px;
    border-radius: 20px;
  }

  /* Hero section */
  .hero {
    padding: 72px 0 52px;
    opacity: 0;
    transform: translateY(12px);
    animation: fadeUp 0.6s ease 0.1s forwards;
  }

  .hero-eyebrow {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 20px;
  }

  .eyebrow-line {
    width: 24px;
    height: 1px;
    background: var(--amber);
  }

  .eyebrow-text {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--amber);
  }

  .hero-title {
    font-family: 'Fraunces', serif;
    font-size: clamp(36px, 5vw, 52px);
    font-weight: 300;
    line-height: 1.1;
    color: var(--ink);
    letter-spacing: -0.02em;
    margin-bottom: 18px;
  }

  .hero-title em {
    font-style: italic;
    color: var(--amber);
  }

  .hero-sub {
    font-size: 16px;
    line-height: 1.6;
    color: var(--ink-muted);
    max-width: 520px;
    font-weight: 400;
  }

  /* Divider */
  .divider {
    height: 1px;
    background: var(--border);
    margin-bottom: 40px;
    opacity: 0;
    animation: fadeIn 0.5s ease 0.25s forwards;
  }

  /* Form section */
  .form-section {
    opacity: 0;
    transform: translateY(12px);
    animation: fadeUp 0.6s ease 0.2s forwards;
  }

  .section-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--ink-muted);
    margin-bottom: 14px;
  }

  /* Mode cards */
  .mode-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
    margin-bottom: 36px;
  }

  .mode-card {
    position: relative;
    background: var(--white);
    border: 1.5px solid var(--border);
    border-radius: 12px;
    padding: 20px 18px;
    cursor: pointer;
    transition: all 0.2s ease;
    text-align: left;
    overflow: hidden;
  }

  .mode-card::before {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, var(--amber-pale), transparent);
    opacity: 0;
    transition: opacity 0.2s ease;
    border-radius: 10px;
  }

  .mode-card:hover {
    border-color: var(--ink-faint);
    transform: translateY(-1px);
    box-shadow: 0 4px 16px rgba(14,14,12,0.06);
  }

  .mode-card:hover::before {
    opacity: 0.5;
  }

  .mode-card.selected {
    border-color: var(--selected-border);
    background: var(--selected-bg);
    box-shadow: 0 0 0 3px rgba(184,147,90,0.12), 0 4px 16px rgba(184,147,90,0.1);
  }

  .mode-card.selected::before {
    opacity: 1;
  }

  .mode-num {
    font-family: 'Fraunces', serif;
    font-size: 22px;
    font-weight: 400;
    color: var(--ink-faint);
    line-height: 1;
    margin-bottom: 10px;
    transition: color 0.2s;
  }

  .mode-card.selected .mode-num {
    color: var(--amber);
  }

  .mode-name {
    font-size: 13px;
    font-weight: 600;
    color: var(--ink);
    margin-bottom: 5px;
    letter-spacing: -0.01em;
  }

  .mode-desc {
    font-size: 12px;
    color: var(--ink-muted);
    line-height: 1.5;
  }

  .mode-check {
    position: absolute;
    top: 14px;
    right: 14px;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: var(--amber);
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0;
    transform: scale(0.6);
    transition: all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
  }

  .mode-card.selected .mode-check {
    opacity: 1;
    transform: scale(1);
  }

  .mode-check::after {
    content: '';
    width: 5px;
    height: 8px;
    border-right: 1.5px solid white;
    border-bottom: 1.5px solid white;
    transform: rotate(45deg) translate(-1px, -1px);
  }

  /* Input area */
  .input-wrapper {
    position: relative;
    margin-bottom: 14px;
    opacity: 0;
    transform: translateY(10px);
    animation: fadeUp 0.5s ease 0.3s forwards;
  }

  .input-label-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
  }

  .input-hint {
    font-size: 12px;
    color: var(--ink-faint);
    transition: color 0.2s;
  }

  .research-textarea {
    width: 100%;
    min-height: 148px;
    background: var(--white);
    border: 1.5px solid var(--border);
    border-radius: 12px;
    padding: 18px 20px;
    font-family: 'Instrument Sans', sans-serif;
    font-size: 15px;
    line-height: 1.65;
    color: var(--ink);
    resize: none;
    outline: none;
    transition: all 0.2s ease;
    box-shadow: 0 1px 3px rgba(14,14,12,0.04);
  }

  .research-textarea::placeholder {
    color: var(--ink-faint);
    font-style: italic;
  }

  .research-textarea:focus {
    border-color: var(--amber);
    box-shadow: 0 0 0 3px rgba(184,147,90,0.1), 0 1px 3px rgba(14,14,12,0.04);
  }

  .char-count {
    position: absolute;
    bottom: 14px;
    right: 16px;
    font-size: 11px;
    color: var(--ink-faint);
    pointer-events: none;
    transition: color 0.2s;
  }

  .char-count.warn {
    color: #C97A5A;
  }

  /* Bottom row */
  .bottom-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-bottom: 52px;
    opacity: 0;
    animation: fadeIn 0.5s ease 0.45s forwards;
  }

  .help-text {
    font-size: 12px;
    color: var(--ink-faint);
    max-width: 320px;
    line-height: 1.5;
  }

  .submit-btn {
    display: flex;
    align-items: center;
    gap: 10px;
    background: var(--ink);
    color: white;
    border: none;
    border-radius: 10px;
    padding: 14px 24px;
    font-family: 'Instrument Sans', sans-serif;
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 0.01em;
    cursor: pointer;
    transition: all 0.2s ease;
    white-space: nowrap;
    position: relative;
    overflow: hidden;
  }

  .submit-btn::before {
    content: '';
    position: absolute;
    inset: 0;
    background: var(--amber);
    opacity: 0;
    transition: opacity 0.2s ease;
  }

  .submit-btn:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 6px 20px rgba(14,14,12,0.18);
  }

  .submit-btn:hover:not(:disabled)::before {
    opacity: 1;
  }

  .submit-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .submit-btn span, .submit-btn svg {
    position: relative;
    z-index: 1;
  }

  .btn-arrow {
    width: 16px;
    height: 16px;
    transition: transform 0.2s ease;
  }

  .submit-btn:hover:not(:disabled) .btn-arrow {
    transform: translateX(2px);
  }

  /* Loading state */
  .submit-btn.loading {
    pointer-events: none;
  }

  .spinner {
    width: 14px;
    height: 14px;
    border: 2px solid rgba(255,255,255,0.3);
    border-top-color: white;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
    position: relative;
    z-index: 1;
  }

  /* Agent pills */
  .agents-row {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 16px 0 40px;
    flex-wrap: wrap;
    opacity: 0;
    animation: fadeIn 0.5s ease 0.5s forwards;
  }

  .agents-label {
    font-size: 11px;
    color: var(--ink-faint);
    font-weight: 500;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    margin-right: 4px;
  }

  .agent-pill {
    font-size: 11px;
    font-weight: 500;
    color: var(--ink-muted);
    background: var(--white);
    border: 1px solid var(--border);
    padding: 4px 10px;
    border-radius: 20px;
    letter-spacing: 0.01em;
  }

  .agent-pill.highlight {
    color: var(--amber);
    border-color: var(--amber-light);
    background: var(--amber-pale);
  }

  /* Animations */
  @keyframes fadeUp {
    to { opacity: 1; transform: translateY(0); }
  }

  @keyframes fadeIn {
    to { opacity: 1; }
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  /* Responsive */
  @media (max-width: 600px) {
    .mode-grid { grid-template-columns: 1fr; }
    .bottom-row { flex-direction: column; gap: 16px; align-items: stretch; }
    .submit-btn { justify-content: center; }
    .help-text { max-width: 100%; }
  }
`;

const MODES = [
  {
    num: "01",
    name: "Topic Exploration",
    desc: "Start with a broad topic. The Council will surface a hypothesis from real papers.",
    placeholder: "e.g. Federated Learning in Healthcare",
  },
  {
    num: "02",
    name: "Hypothesis Test",
    desc: "Submit a clear hypothesis. The Council will debate and stress-test it.",
    placeholder: "e.g. Federated learning can reduce patient data privacy risks in cross-hospital ML models",
  },
  {
    num: "03",
    name: "Proposal Review",
    desc: "Paste a draft proposal. The Council acts as a peer review committee.",
    placeholder: "Paste your abstract or methodology draft here...",
  },
];

const AGENTS = ["Orchestrator", "Librarian", "Innovator", "Skeptic", "Fact-Checker", "Chaos", "Chairman", "Secretary"];
const HIGHLIGHT_AGENTS = ["Innovator", "Skeptic", "Fact-Checker"];

export default function InputPage() {
  const [selectedMode, setSelectedMode] = useState(1);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const MAX_CHARS = 1200;

  const mode = MODES[selectedMode];
  const canSubmit = inputValue.trim().length > 8 && !isLoading;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setIsLoading(true);
    // Integration point: POST /api/session { mode: selectedMode + 1, input: inputValue }
    await new Promise(r => setTimeout(r, 2000));
    setIsLoading(false);
    alert(`Session started!\nMode: ${selectedMode + 1}\nInput: ${inputValue.slice(0, 60)}...`);
  };

  return (
    <>
      <style>{styles}</style>
      <div className="page-wrapper">
        <div className="dot-grid" />
        <div className="content">

          {/* Header */}
          <header className="header">
            <div className="logo">
              <div className="logo-mark" />
              <span className="logo-text">Research Council</span>
            </div>
            <div className="header-badge">v1.0 Prototype</div>
          </header>

          {/* Hero */}
          <section className="hero">
            <div className="hero-eyebrow">
              <div className="eyebrow-line" />
              <span className="eyebrow-text">Multi-Agent Research System</span>
            </div>
            <h1 className="hero-title">
              Submit your idea.<br />
              Let the <em>Council</em> decide.
            </h1>
            <p className="hero-sub">
              A board of adversarial AI agents will debate, stress-test, and verify your research hypothesis — grounded in real academic papers.
            </p>
          </section>

          <div className="divider" />

          {/* Mode Selection */}
          <div className="form-section">
            <div className="section-label">Select input mode</div>
            <div className="mode-grid">
              {MODES.map((m, i) => (
                <button
                  key={i}
                  className={`mode-card ${selectedMode === i ? "selected" : ""}`}
                  onClick={() => { setSelectedMode(i); setInputValue(""); }}
                >
                  <div className="mode-num">{m.num}</div>
                  <div className="mode-name">{m.name}</div>
                  <div className="mode-desc">{m.desc}</div>
                  <div className="mode-check" />
                </button>
              ))}
            </div>
          </div>

          {/* Text Input */}
          <div className="input-wrapper">
            <div className="input-label-row">
              <div className="section-label" style={{ marginBottom: 0 }}>
                {selectedMode === 0 ? "Your research topic" : selectedMode === 1 ? "Your hypothesis" : "Your draft proposal"}
              </div>
              <span className="input-hint">
                {selectedMode === 0 ? "Be specific for better results" : selectedMode === 1 ? "State it as a testable claim" : "Abstract or methodology works"}
              </span>
            </div>
            <textarea
              className="research-textarea"
              placeholder={mode.placeholder}
              value={inputValue}
              onChange={e => setInputValue(e.target.value.slice(0, MAX_CHARS))}
              rows={6}
            />
            <span className={`char-count ${inputValue.length > MAX_CHARS * 0.9 ? "warn" : ""}`}>
              {inputValue.length}/{MAX_CHARS}
            </span>
          </div>

          {/* Agent Pills */}
          <div className="agents-row">
            <span className="agents-label">Council</span>
            {AGENTS.map(a => (
              <span key={a} className={`agent-pill ${HIGHLIGHT_AGENTS.includes(a) ? "highlight" : ""}`}>
                {a}
              </span>
            ))}
          </div>

          {/* Submit Row */}
          <div className="bottom-row">
            <p className="help-text">
              The Council will fetch real papers from ArXiv and Semantic Scholar before the debate begins.
            </p>
            <button
              className={`submit-btn ${isLoading ? "loading" : ""}`}
              onClick={handleSubmit}
              disabled={!canSubmit}
            >
              {isLoading ? (
                <>
                  <div className="spinner" />
                  <span>Convening Council…</span>
                </>
              ) : (
                <>
                  <span>Convene the Council</span>
                  <svg className="btn-arrow" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M3 8H13M13 8L9 4M13 8L9 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </>
              )}
            </button>
          </div>

        </div>
      </div>
    </>
  );
}
