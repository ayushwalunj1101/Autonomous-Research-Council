"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  apiJson, formatCost, formatDate, postFile, postJson,
  type SessionListItem,
} from "@/lib/api";

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

  .research-textarea.error-border {
    border-color: #C97A5A;
    box-shadow: 0 0 0 3px rgba(201,122,90,0.1);
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

  /* Error banner */
  .error-banner {
    display: flex;
    align-items: center;
    gap: 10px;
    background: #FEF2EE;
    border: 1px solid #F0C4B4;
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 14px;
    font-size: 13px;
    color: #9B3B1E;
    line-height: 1.4;
  }

  .error-icon {
    flex-shrink: 0;
    width: 16px;
    height: 16px;
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

  /* Upload (mode 3) */
  .upload-btn {
    font-size: 12px; font-weight: 600; color: var(--amber);
    background: var(--amber-pale); border: 1px solid var(--amber-light);
    padding: 5px 12px; border-radius: 20px; cursor: pointer;
    font-family: 'Instrument Sans', sans-serif; transition: all 0.2s ease;
  }
  .upload-btn:hover { border-color: var(--amber); }
  .upload-btn.disabled { opacity: 0.5; pointer-events: none; }

  .notice-banner {
    font-size: 12px; color: var(--ink-muted); background: var(--amber-pale);
    border: 1px solid var(--amber-light); border-radius: 10px;
    padding: 10px 14px; margin-bottom: 14px; line-height: 1.45;
  }

  /* Confirm panel */
  .confirm-panel {
    background: var(--white); border: 1.5px solid var(--amber-light);
    border-radius: 12px; padding: 22px 22px 18px; margin-bottom: 20px;
    box-shadow: 0 4px 16px rgba(184,147,90,0.08);
    opacity: 0; transform: translateY(10px);
    animation: fadeUp 0.4s ease forwards;
  }
  .confirm-title { font-family: 'Fraunces', serif; font-size: 20px; font-weight: 300; margin-bottom: 4px; }
  .confirm-title em { font-style: italic; color: var(--amber); }
  .confirm-sub { font-size: 13px; color: var(--ink-muted); margin-bottom: 18px; line-height: 1.5; }
  .field { margin-bottom: 16px; }
  .field-label {
    display: block; font-size: 11px; font-weight: 600; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--ink-muted); margin-bottom: 8px;
  }
  .field-hint { font-size: 12px; color: var(--ink-faint); margin-top: 6px; line-height: 1.45; }
  .text-input {
    width: 100%; background: var(--bg); border: 1.5px solid var(--border); border-radius: 10px;
    padding: 11px 14px; font-family: 'Instrument Sans', sans-serif; font-size: 14px; color: var(--ink);
    outline: none; transition: all 0.2s ease;
  }
  .text-input:focus { border-color: var(--amber); background: var(--white); box-shadow: 0 0 0 3px rgba(184,147,90,0.1); }
  textarea.text-input { resize: vertical; min-height: 84px; line-height: 1.55; }
  .keyword-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  .toggle-row {
    display: flex; align-items: flex-start; gap: 10px; font-size: 13px;
    color: var(--ink); cursor: pointer; line-height: 1.45; margin-bottom: 16px;
  }
  .toggle-row input { margin-top: 3px; accent-color: var(--amber); width: 15px; height: 15px; flex-shrink: 0; }
  .toggle-row small { display: block; color: var(--ink-muted); font-size: 12px; }
  .confirm-actions { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-top: 8px; }
  .ghost-btn {
    background: transparent; border: 1.5px solid var(--border); border-radius: 10px;
    padding: 12px 18px; font-family: 'Instrument Sans', sans-serif; font-size: 13px; font-weight: 600;
    color: var(--ink-muted); cursor: pointer; transition: all 0.2s ease; white-space: nowrap;
  }
  .ghost-btn:hover:not(:disabled) { border-color: var(--ink-faint); color: var(--ink); }
  .ghost-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  .mode-card:disabled { cursor: default; }
  .mode-card:disabled:hover { transform: none; box-shadow: none; }

  /* Recent sessions */
  .history { padding: 0 0 60px; opacity: 0; animation: fadeIn 0.5s ease 0.55s forwards; }
  .history-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; gap: 12px; }
  .history-list { display: flex; flex-direction: column; gap: 8px; }
  .history-item {
    display: flex; align-items: center; gap: 12px;
    background: var(--white); border: 1px solid var(--border); border-radius: 10px;
    padding: 12px 14px; transition: all 0.2s ease;
  }
  .history-item:hover { border-color: var(--ink-faint); box-shadow: 0 4px 16px rgba(14,14,12,0.05); }
  .history-item input { accent-color: var(--amber); width: 15px; height: 15px; flex-shrink: 0; }
  .history-main {
    flex: 1; min-width: 0; cursor: pointer; background: none; border: none; text-align: left;
    font-family: 'Instrument Sans', sans-serif; padding: 0;
  }
  .history-title { font-size: 13px; color: var(--ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .history-meta { font-size: 11px; color: var(--ink-faint); margin-top: 2px; }
  .status-pill {
    font-size: 10px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
    padding: 3px 9px; border-radius: 20px; flex-shrink: 0;
    background: var(--bg); color: var(--ink-muted); border: 1px solid var(--border);
  }
  .status-pill.complete { background: #EDF5F0; color: #3A7D5C; border-color: rgba(58,125,92,0.25); }
  .status-pill.error, .status-pill.cancelled { background: #FEF2EE; color: #9B3B1E; border-color: #F0C4B4; }
  .status-pill.active { background: var(--amber-pale); color: var(--amber); border-color: var(--amber-light); }

  /* Responsive */
  @media (max-width: 600px) {
    .mode-grid { grid-template-columns: 1fr; }
    .bottom-row { flex-direction: column; gap: 16px; align-items: stretch; }
    .submit-btn { justify-content: center; }
    .help-text { max-width: 100%; }
    .confirm-actions { flex-direction: column-reverse; align-items: stretch; }
    .history-item { flex-wrap: wrap; }
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

// Topics and hypotheses stay short; proposals (mode 3) can be a full abstract or methodology.
const MAX_CHARS_BY_MODE = [1200, 1200, 12000];
const ACTIVE_STATUSES = ["queued", "preparing", "fetching", "awaiting_review", "running"];

interface PreparedSession {
  session_id: string;
  hypothesis: string;
  keywords: string[];
  domain: string;
}

interface HealthInfo {
  model: string;
  budget_usd: number;
}

function parseKeywords(text: string): string[] {
  return text.split(",").map(k => k.trim()).filter(Boolean);
}

export default function InputPage() {
  const router = useRouter();
  const [selectedMode, setSelectedMode] = useState(1);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  // Confirm step (after the Orchestrator has read the input)
  const [prepared, setPrepared] = useState<PreparedSession | null>(null);
  const [hypothesisDraft, setHypothesisDraft] = useState("");
  const [keywordsDraft, setKeywordsDraft] = useState("");
  const [reviewPapers, setReviewPapers] = useState(true);
  const [chaosDraft, setChaosDraft] = useState("");
  const [parentId, setParentId] = useState<string | null>(null);

  const [history, setHistory] = useState<SessionListItem[]>([]);
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [health, setHealth] = useState<HealthInfo | null>(null);

  const MAX_CHARS = MAX_CHARS_BY_MODE[selectedMode];
  const mode = MODES[selectedMode];
  const canSubmit = inputValue.trim().length > 8 && !isLoading && !uploading;
  const draftKeywords = parseKeywords(keywordsDraft);
  const canStart = !!prepared && hypothesisDraft.trim().length > 8 && draftKeywords.length > 0 && !isLoading;

  // Prefill from "Run again with refined hypothesis" links: /?mode=2&input=...&parent=<session_id>
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const m = Number(params.get("mode"));
    const modeIdx = m >= 1 && m <= 3 ? m - 1 : null;
    if (modeIdx !== null) setSelectedMode(modeIdx);
    const input = params.get("input");
    if (input) setInputValue(input.slice(0, MAX_CHARS_BY_MODE[modeIdx ?? 1]));
    const parent = params.get("parent");
    if (parent) setParentId(parent);

    apiJson<{ sessions: SessionListItem[] }>("/api/sessions?limit=8")
      .then(d => setHistory(d.sessions))
      .catch(() => { /* history is optional */ });
    apiJson<HealthInfo>("/api/health").then(setHealth).catch(() => { /* optional */ });
  }, []);

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setIsLoading(true);
    setError(null);
    setNotice(null);

    try {
      const res = await postJson<PreparedSession>("/api/session/prepare", {
        mode: selectedMode + 1,
        user_input: inputValue,
        parent_session_id: parentId,
      });
      setPrepared(res);
      setHypothesisDraft(res.hypothesis);
      setKeywordsDraft(res.keywords.join(", "));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleStart = async () => {
    if (!prepared || !canStart) return;
    setIsLoading(true);
    setError(null);
    try {
      await postJson(`/api/session/${prepared.session_id}/start`, {
        hypothesis: hypothesisDraft.trim(),
        keywords: draftKeywords,
        review_papers: reviewPapers,
        chaos_constraint: chaosDraft.trim() || null,
      });
      router.push(`/council/${prepared.session_id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not start the debate.");
      setIsLoading(false);
    }
  };

  const handleBack = () => {
    if (prepared) {
      // Discard the prepared (never started) session so it does not linger in history
      postJson(`/api/session/${prepared.session_id}/cancel`, {}).catch(() => {});
    }
    setPrepared(null);
    setError(null);
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    setError(null);
    setNotice(null);
    try {
      const res = await postFile<{ text: string; truncated: boolean }>("/api/extract-text", file);
      setInputValue(res.text.slice(0, MAX_CHARS));
      if (res.truncated || res.text.length > MAX_CHARS) {
        setNotice(`"${file.name}" is long; only the first ${MAX_CHARS.toLocaleString()} characters were kept. Trim it to the abstract and methodology for best results.`);
      } else {
        setNotice(`Loaded text from "${file.name}".`);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not read that file.");
    } finally {
      setUploading(false);
    }
  };

  const openSession = (item: SessionListItem) => {
    router.push(item.status === "complete" ? `/report/${item.session_id}` : `/council/${item.session_id}`);
  };

  const toggleCompare = (id: string) => {
    setCompareIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id].slice(-2));
  };

  const locked = !!prepared || isLoading;

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: styles }} />
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
                  disabled={locked}
                  onClick={() => { setSelectedMode(i); setInputValue(""); setError(null); setNotice(null); }}
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
              {selectedMode === 2 ? (
                <label className={`upload-btn ${uploading || locked ? "disabled" : ""}`}>
                  {uploading ? "Reading file…" : "Upload PDF / DOCX"}
                  <input type="file" accept=".pdf,.docx,.txt,.md" hidden onChange={handleUpload} />
                </label>
              ) : (
                <span className="input-hint">
                  {selectedMode === 0 ? "Be specific for better results" : "State it as a testable claim"}
                </span>
              )}
            </div>
            <textarea
              className={`research-textarea${error ? " error-border" : ""}`}
              placeholder={mode.placeholder}
              value={inputValue}
              readOnly={locked}
              onChange={e => { setInputValue(e.target.value.slice(0, MAX_CHARS)); setError(null); }}
              rows={selectedMode === 2 ? 10 : 6}
            />
            <span className={`char-count ${inputValue.length > MAX_CHARS * 0.9 ? "warn" : ""}`}>
              {inputValue.length}/{MAX_CHARS}
            </span>
          </div>

          {notice && <div className="notice-banner">{notice}</div>}

          {/* Error Banner */}
          {error && (
            <div className="error-banner">
              <svg className="error-icon" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5"/>
                <path d="M8 5v3.5M8 11h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
              {error}
            </div>
          )}

          {/* Confirm step — review what the Orchestrator extracted before spending a full debate */}
          {prepared && (
            <div className="confirm-panel">
              <div className="confirm-title">Before the <em>Council</em> convenes</div>
              <div className="confirm-sub">
                The Orchestrator read your input as the hypothesis and search keywords below. Edit anything it got wrong — a bad keyword means the wrong papers.
              </div>

              <div className="field">
                <label className="field-label" htmlFor="hypothesis">Hypothesis to debate</label>
                <textarea
                  id="hypothesis"
                  className="text-input"
                  value={hypothesisDraft}
                  maxLength={2000}
                  onChange={e => setHypothesisDraft(e.target.value)}
                />
              </div>

              <div className="field">
                <label className="field-label" htmlFor="keywords">Search keywords</label>
                <input
                  id="keywords"
                  className="text-input"
                  value={keywordsDraft}
                  onChange={e => setKeywordsDraft(e.target.value)}
                  placeholder="federated learning, clinical prediction"
                />
                <div className="keyword-chips">
                  {draftKeywords.map(k => <span key={k} className="agent-pill highlight">{k}</span>)}
                </div>
                <div className="field-hint">Comma-separated. The first two keywords drive the arXiv query; all of them go to OpenAlex and Semantic Scholar.</div>
              </div>

              <label className="toggle-row">
                <input type="checkbox" checked={reviewPapers} onChange={e => setReviewPapers(e.target.checked)} />
                <span>
                  Let me review the papers before the debate starts
                  <small>Remove irrelevant papers or add your own (arXiv ID, DOI or PDF).</small>
                </span>
              </label>

              <div className="field">
                <label className="field-label" htmlFor="chaos">Chaos constraint (optional)</label>
                <input
                  id="chaos"
                  className="text-input"
                  value={chaosDraft}
                  maxLength={500}
                  onChange={e => setChaosDraft(e.target.value)}
                  placeholder="Leave empty to let the Chaos Agent pick the most relevant one"
                />
              </div>

              <div className="confirm-actions">
                <button className="ghost-btn" onClick={handleBack} disabled={isLoading}>← Edit input</button>
                <button className={`submit-btn ${isLoading ? "loading" : ""}`} onClick={handleStart} disabled={!canStart}>
                  {isLoading ? (
                    <>
                      <div className="spinner" />
                      <span>Starting…</span>
                    </>
                  ) : (
                    <>
                      <span>Start the Debate</span>
                      <svg className="btn-arrow" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M3 8H13M13 8L9 4M13 8L9 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

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
          {!prepared && (
            <div className="bottom-row">
              <p className="help-text">
                The Council will fetch real papers from arXiv, OpenAlex, Semantic Scholar and PubMed before the debate begins.
                {health && <> Model: {health.model} · cost limit ${health.budget_usd.toFixed(2)} per session.</>}
              </p>
              <button
                className={`submit-btn ${isLoading ? "loading" : ""}`}
                onClick={handleSubmit}
                disabled={!canSubmit}
              >
                {isLoading ? (
                  <>
                    <div className="spinner" />
                    <span>Reading your input…</span>
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
          )}

          {/* Recent sessions */}
          {history.length > 0 && (
            <section className="history">
              <div className="history-head">
                <div className="section-label" style={{ marginBottom: 0 }}>Recent sessions</div>
                <button
                  className="ghost-btn"
                  style={{ padding: "8px 14px", fontSize: 12 }}
                  disabled={compareIds.length !== 2}
                  onClick={() => router.push(`/compare?a=${compareIds[0]}&b=${compareIds[1]}`)}
                >
                  Compare selected ({compareIds.length}/2)
                </button>
              </div>
              <div className="history-list">
                {history.map(item => {
                  const statusClass = item.status === "complete" ? "complete"
                    : item.status === "error" || item.status === "cancelled" ? item.status
                    : ACTIVE_STATUSES.includes(item.status) ? "active" : "";
                  return (
                    <div key={item.session_id} className="history-item">
                      <input
                        type="checkbox"
                        title="Select to compare"
                        disabled={item.status !== "complete"}
                        checked={compareIds.includes(item.session_id)}
                        onChange={() => toggleCompare(item.session_id)}
                      />
                      <button className="history-main" onClick={() => openSession(item)}>
                        <div className="history-title">{item.refined_hypothesis || item.hypothesis || "Untitled session"}</div>
                        <div className="history-meta">
                          {formatDate(item.created_at)} · {MODES[item.mode - 1]?.name ?? "Session"}
                          {item.ragas_score !== null && <> · RAGAS {item.ragas_score.toFixed(2)}</>}
                          {item.overall_confidence !== null && <> · confidence {item.overall_confidence}</>}
                          {item.cost_usd > 0 && <> · {formatCost(item.cost_usd)}</>}
                        </div>
                      </button>
                      <span className={`status-pill ${statusClass}`}>{item.status.replace(/_/g, " ")}</span>
                    </div>
                  );
                })}
              </div>
            </section>
          )}

        </div>
      </div>
    </>
  );
}
