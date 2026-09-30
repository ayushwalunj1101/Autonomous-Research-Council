"use client";

import { useEffect, useState } from "react";
import {
  apiJson, formatCost, formatDate, withDefaults,
  type EvaluationJson, type SessionResult,
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
  }

  body { background: var(--bg); font-family: 'Instrument Sans', sans-serif; color: var(--ink); font-size: 14px; line-height: 1.6; }

  .dot-grid {
    position: fixed; inset: 0;
    background-image: radial-gradient(circle, rgba(14,14,12,0.07) 1px, transparent 1px);
    background-size: 28px 28px; pointer-events: none; z-index: 0;
  }

  .topbar {
    position: sticky; top: 0; z-index: 100;
    background: rgba(247,245,240,0.92); backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border);
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 48px; height: 60px;
  }
  .logo { display: flex; align-items: center; gap: 10px; text-decoration: none; color: var(--ink); }
  .logo-mark {
    width: 26px; height: 26px; border: 1.5px solid var(--amber);
    border-radius: 6px; display: flex; align-items: center; justify-content: center;
  }
  .logo-mark::before { content: ''; width: 9px; height: 9px; background: var(--amber); border-radius: 2px; }
  .logo-text { font-size: 13px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
  .back-link {
    font-size: 12px; font-weight: 600; color: var(--ink-muted); text-decoration: none;
    border: 1px solid var(--border); background: var(--white); padding: 7px 14px; border-radius: 8px;
  }
  .back-link:hover { color: var(--amber); border-color: var(--amber-light); }

  .page { position: relative; z-index: 1; max-width: 1040px; margin: 0 auto; padding: 48px 48px 100px; }

  .eyebrow { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; }
  .eyebrow-line { width: 24px; height: 1px; background: var(--amber); }
  .eyebrow-text { font-size: 11px; font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase; color: var(--amber); }
  .title { font-family: 'Fraunces', serif; font-size: clamp(28px, 4vw, 38px); font-weight: 300; letter-spacing: -0.02em; margin-bottom: 28px; }
  .title em { font-style: italic; color: var(--amber); }

  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 28px; }
  .run-card {
    background: var(--white); border: 1px solid var(--border); border-radius: 12px; padding: 18px 20px;
    border-top: 3px solid var(--amber);
  }
  .run-card.b { border-top-color: var(--chaos); }
  .run-label { font-size: 10px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: var(--ink-faint); margin-bottom: 6px; }
  .run-hypothesis { font-family: 'Fraunces', serif; font-size: 17px; font-weight: 300; line-height: 1.4; margin-bottom: 10px; }
  .run-meta { font-size: 11px; color: var(--ink-muted); line-height: 1.6; }
  .run-meta a { color: var(--amber); font-weight: 600; text-decoration: none; }

  .section-header {
    display: flex; align-items: center; gap: 12px; margin: 28px 0 14px;
    padding-bottom: 10px; border-bottom: 1px solid var(--border);
  }
  .section-title { font-size: 11px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; }

  .score-table { background: var(--white); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
  .score-row {
    display: grid; grid-template-columns: 150px 1fr 1fr 70px; gap: 16px; align-items: center;
    padding: 12px 18px; border-bottom: 1px solid var(--border);
  }
  .score-row:last-child { border-bottom: none; }
  .score-row.head { background: var(--bg); font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-faint); }
  .score-name { font-size: 12px; font-weight: 600; }
  .score-cell { display: flex; align-items: center; gap: 10px; }
  .bar-track { flex: 1; height: 6px; background: #F0EDE8; border-radius: 3px; overflow: hidden; }
  .bar-fill { height: 100%; border-radius: 3px; background: var(--amber); }
  .bar-fill.b { background: var(--chaos); }
  .score-value { font-family: 'Fraunces', serif; font-size: 18px; width: 36px; text-align: right; }
  .score-range { font-size: 10px; color: var(--ink-faint); width: 56px; }
  .delta { font-size: 12px; font-weight: 700; text-align: right; }
  .delta.up { color: var(--green); }
  .delta.down { color: var(--red); }
  .delta.same { color: var(--ink-faint); }

  .list-card { background: var(--white); border: 1px solid var(--border); border-radius: 12px; padding: 16px 18px; }
  .list-card ul { padding-left: 18px; font-size: 13px; color: var(--ink-muted); line-height: 1.55; }
  .list-card li { margin-bottom: 6px; }
  .list-title { font-size: 11px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 10px; }
  .list-title.green { color: var(--green); }
  .list-title.red { color: var(--red); }
  .chaos-text { font-size: 13px; font-style: italic; color: var(--chaos); font-weight: 600; margin-bottom: 6px; }
  .muted { font-size: 13px; color: var(--ink-muted); }

  .badges { display: flex; flex-wrap: wrap; gap: 6px; }
  .badge {
    font-size: 10px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
    padding: 3px 8px; border-radius: 4px; border: 1px solid var(--border); background: var(--bg); color: var(--ink-muted);
  }
  .badge.supported { background: var(--green-pale); color: var(--green); border-color: rgba(58,125,92,0.25); }
  .badge.partial { background: var(--amber-pale); color: var(--amber); border-color: var(--amber-light); }
  .badge.unsupported, .badge.contradicted, .badge.low { background: var(--red-pale); color: var(--red); border-color: rgba(192,80,58,0.25); }

  @media (max-width: 760px) {
    .page { padding: 32px 20px 80px; }
    .topbar { padding: 0 20px; }
    .cols { grid-template-columns: 1fr; }
    .score-row { grid-template-columns: 1fr; gap: 6px; }
    .score-row.head { display: none; }
    .delta { text-align: left; }
  }
`;

type Run = { meta: SessionResult; ev: EvaluationJson };

const SCORES = [
  { label: "Novelty", field: "novelty_score", range: "novelty" },
  { label: "Feasibility", field: "feasibility_score", range: "feasibility" },
  { label: "Research gap", field: "research_gap_score", range: "research_gap" },
  { label: "Overall confidence", field: "overall_confidence", range: "overall" },
] as const;

function verdictCounts(ev: EvaluationJson): Record<string, number> {
  return ev.claim_audit.reduce<Record<string, number>>((acc, r) => {
    if (!r.resolved) acc[r.verdict] = (acc[r.verdict] ?? 0) + 1;
    return acc;
  }, {});
}

function Delta({ a, b, scale = 1 }: { a: number; b: number; scale?: number }) {
  const d = Math.round((b - a) * scale * 100) / 100;
  if (d === 0) return <span className="delta same">±0</span>;
  return <span className={`delta ${d > 0 ? "up" : "down"}`}>{d > 0 ? "+" : ""}{d}</span>;
}

export default function ComparePage() {
  const [runs, setRuns] = useState<[Run, Run] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const a = params.get("a");
    const b = params.get("b");
    if (!a || !b) {
      setError("Pick two completed sessions to compare (from the home page's recent sessions).");
      return;
    }
    const load = (id: string) => apiJson<SessionResult>(`/api/session/${id}/result`)
      .then(meta => ({ meta, ev: withDefaults(meta.evaluation_json) }));
    Promise.all([load(a), load(b)])
      .then(([ra, rb]) => setRuns([ra, rb]))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Could not load both sessions."));
  }, []);

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: styles }} />
      <div className="dot-grid" />

      <nav className="topbar">
        <a className="logo" href="/">
          <div className="logo-mark" />
          <span className="logo-text">Research Council</span>
        </a>
        <a className="back-link" href="/">← New session</a>
      </nav>

      <main className="page">
        <div className="eyebrow">
          <div className="eyebrow-line" />
          <span className="eyebrow-text">Side-by-side</span>
        </div>
        <h1 className="title">Compare <em>two runs</em></h1>

        {error && <p className="muted">{error}</p>}
        {!error && !runs && <p className="muted">Loading both reports…</p>}

        {runs && (
          <>
            <div className="cols">
              {runs.map(({ meta, ev }, i) => (
                <div key={meta.session_id} className={`run-card ${i ? "b" : ""}`}>
                  <div className="run-label">Run {i ? "B" : "A"} · #{meta.session_id.slice(0, 8).toUpperCase()}</div>
                  <div className="run-hypothesis">{ev.refined_hypothesis || meta.hypothesis}</div>
                  <div className="run-meta">
                    {formatDate(meta.created_at)} · RAGAS {ev.ragas_score.toFixed(2)}
                    {ev.low_confidence_flag && " · low confidence"}
                    {ev.model && <> · {ev.model}</>}
                    {ev.cost_usd > 0 && <> · {formatCost(ev.cost_usd)}</>}
                    <br />
                    <a href={`/report/${meta.session_id}`}>Open full report →</a>
                  </div>
                </div>
              ))}
            </div>

            <div className="section-header"><span className="section-title">Scores</span></div>
            <div className="score-table">
              <div className="score-row head">
                <span>Metric</span><span>Run A</span><span>Run B</span><span style={{ textAlign: "right" }}>B − A</span>
              </div>
              {SCORES.map(s => {
                const [ra, rb] = runs;
                const va = ra.ev[s.field];
                const vb = rb.ev[s.field];
                const rangeA = ra.ev.score_ranges[s.range];
                const rangeB = rb.ev.score_ranges[s.range];
                return (
                  <div key={s.field} className="score-row">
                    <span className="score-name">{s.label}</span>
                    {[{ v: va, r: rangeA, b: false }, { v: vb, r: rangeB, b: true }].map((c, i) => (
                      <span key={i} className="score-cell">
                        <span className="score-value">{c.v}</span>
                        <span className="bar-track"><span className={`bar-fill ${c.b ? "b" : ""}`} style={{ width: `${c.v}%`, display: "block" }} /></span>
                        <span className="score-range">{c.r[0] !== c.r[1] ? `${c.r[0]}–${c.r[1]}` : ""}</span>
                      </span>
                    ))}
                    <Delta a={va} b={vb} />
                  </div>
                );
              })}
              <div className="score-row">
                <span className="score-name">RAGAS faithfulness</span>
                {runs.map(({ ev }, i) => (
                  <span key={i} className="score-cell">
                    <span className="score-value">{ev.ragas_score.toFixed(2)}</span>
                    <span className="bar-track"><span className={`bar-fill ${i ? "b" : ""}`} style={{ width: `${Math.round(ev.ragas_score * 100)}%`, display: "block" }} /></span>
                    <span className="score-range" />
                  </span>
                ))}
                <Delta a={runs[0].ev.ragas_score} b={runs[1].ev.ragas_score} />
              </div>
            </div>

            <div className="section-header"><span className="section-title">Claim verdicts</span></div>
            <div className="cols">
              {runs.map(({ meta, ev }) => {
                const counts = verdictCounts(ev);
                return (
                  <div key={meta.session_id} className="list-card">
                    <div className="badges">
                      {Object.keys(counts).length === 0 && <span className="muted">No claim audit recorded.</span>}
                      {Object.entries(counts).map(([v, n]) => <span key={v} className={`badge ${v}`}>{n} {v}</span>)}
                      {ev.attempts.length > 1 && <span className="badge">{ev.attempts.length - 1} repair round(s)</span>}
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="section-header"><span className="section-title">Strengths & weaknesses</span></div>
            <div className="cols">
              {runs.map(({ meta, ev }) => (
                <div key={meta.session_id} className="list-card">
                  <div className="list-title green">Strengths</div>
                  <ul>{ev.strengths.map((s, i) => <li key={i}>{s}</li>)}</ul>
                  <div className="list-title red" style={{ marginTop: 12 }}>Weaknesses</div>
                  <ul>{ev.weaknesses.map((w, i) => <li key={i}>{w}</li>)}</ul>
                </div>
              ))}
            </div>

            <div className="section-header"><span className="section-title">Chaos constraint</span></div>
            <div className="cols">
              {runs.map(({ meta, ev }) => (
                <div key={meta.session_id} className="list-card">
                  <div className="chaos-text">“{ev.chaos_constraint}”</div>
                  <div className="muted">{ev.chaos_response_summary}</div>
                </div>
              ))}
            </div>
          </>
        )}
      </main>
    </>
  );
}
