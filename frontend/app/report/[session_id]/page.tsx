"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useParams } from "next/navigation";
import Script from "next/script";
import {
  apiJson, apiUrl, formatCost, formatDate, withDefaults,
  type ClaimAuditRecord, type EvaluationJson, type SessionResult, type Transcript,
} from "@/lib/api";

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Strip "Step N: " prefix if present, return { num, text }. */
function parseStep(raw: string, fallbackIdx: number): { num: string; text: string } {
  const m = raw.match(/^Step\s*(\d+):\s*(.+)/s);
  if (m) return { num: m[1], text: m[2].trim() };
  return { num: String(fallbackIdx + 1), text: raw.trim() };
}

/** Extract a short 2-word label for the flow chart from a step title. */
function flowLabel(stepText: string): string {
  const stopWords = new Set(["&", "with", "via", "for", "the", "a", "an", "of", "in", "and", "to"]);
  const words = stepText
    .split(/[\s/]+/)
    .filter(w => w.length > 1 && !stopWords.has(w.toLowerCase()));
  return (words[0] ?? "") + (words[1] ? "\n" + words[1] : "");
}

const FLOW_COLORS = ["#B8935A", "#9A7D4A", "#3A7D5C", "#2C3E6B", "#7A5C8A"];
const BAR_COLOR_STOPS = [
  ["#B8935A", "#D4B07A"],
  ["#3A7D5C", "#5A9D7C"],
  ["#8B9BC4", "#AABBD4"],
  ["#7A5C8A", "#9A7CAA"],
  ["#C0503A", "#E0705A"],
];

const VERDICT_TEXT: Record<string, string> = {
  supported: "Supported",
  partial: "Partial",
  unsupported: "Unsupported",
  contradicted: "Contradicted",
};

function roundLabel(r: { agent: string; round: number; stage?: string; attempt?: number }): string {
  if (r.stage === "repair") return `Repair ${r.attempt ?? ""} — Innovator`.replace("  ", " ");
  return `Round ${r.round} — ${r.agent}`;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ReportPage() {
  const params = useParams<{ session_id: string }>();
  const sessionId = params.session_id;

  const [evalJson, setEvalJson] = useState<EvaluationJson | null>(null);
  const [meta, setMeta] = useState<SessionResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [echartsReady, setEchartsReady] = useState(false);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [transcriptOpen, setTranscriptOpen] = useState(false);
  const [transcriptError, setTranscriptError] = useState<string | null>(null);

  // Chart container refs
  const radarRef = useRef<HTMLDivElement>(null);
  const barRef = useRef<HTMLDivElement>(null);
  const flowRef = useRef<HTMLDivElement>(null);
  const gauge0Ref = useRef<HTMLDivElement>(null);
  const gauge1Ref = useRef<HTMLDivElement>(null);
  const gauge2Ref = useRef<HTMLDivElement>(null);
  const gauge3Ref = useRef<HTMLDivElement>(null);

  // Stable refs to chart instances for resize / dispose
  const chartInstances = useRef<unknown[]>([]);

  // ── Fetch data (polls while the debate is still running) ───────────────────

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const load = async () => {
      try {
        const res = await fetch(apiUrl(`/api/session/${sessionId}/result`));
        if (cancelled) return;
        if (res.status === 202) {
          setPending(true);
          setLoading(false);
          timer = setTimeout(load, 3000);
          return;
        }
        const body = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(typeof body.detail === "string" ? body.detail : `Request failed (${res.status})`);
        }
        setPending(false);
        setMeta(body as SessionResult);
        setEvalJson(withDefaults((body as SessionResult).evaluation_json));
        setLoading(false);
      } catch (err: unknown) {
        if (cancelled) return;
        const message = err instanceof TypeError
          ? "Cannot reach the backend. Is uvicorn running?"
          : err instanceof Error ? err.message : "Failed to load report.";
        setError(message);
        setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [sessionId]);

  // ── Init ECharts ───────────────────────────────────────────────────────────

  const initCharts = useCallback((d: EvaluationJson) => {
    const ec = ((window as unknown) as Record<string, unknown>)["echarts"] as {
      init: (el: HTMLElement) => {
        setOption: (opt: unknown) => void;
        resize: () => void;
        dispose: () => void;
      };
      getInstanceByDom: (el: HTMLElement) => { resize: () => void } | null;
    };
    if (!ec) return;

    const instances: ReturnType<typeof ec.init>[] = [];
    chartInstances.current = instances;

    const gaugeRefs = [gauge0Ref, gauge1Ref, gauge2Ref, gauge3Ref];
    const citationSupport = Math.round(d.ragas_score * 100);
    const gaugeData = [
      { label: "Novelty",          value: d.novelty_score,     color: "#B8935A" },
      { label: "Feasibility",      value: d.feasibility_score, color: "#3A7D5C" },
      { label: "Research Gap",     value: d.research_gap_score,color: "#2C3E6B" },
      { label: "Citation Support", value: citationSupport,     color: "#7A5C8A" },
    ];

    // Gauges
    gaugeData.forEach((g, i) => {
      const el = gaugeRefs[i].current;
      if (!el) return;
      const chart = ec.init(el);
      instances.push(chart);
      chart.setOption({
        animation: true, animationDuration: 1200, animationEasing: "cubicOut",
        series: [{
          type: "gauge",
          startAngle: 200, endAngle: -20,
          min: 0, max: 100,
          radius: "88%",
          pointer: { show: false },
          progress: {
            show: true, roundCap: true, width: 10,
            itemStyle: { color: g.color }
          },
          axisLine: { lineStyle: { width: 10, color: [[1, "#F0EDE8"]] } },
          axisTick: { show: false },
          splitLine: { show: false },
          axisLabel: { show: false },
          detail: {
            valueAnimation: true,
            formatter: "{value}",
            fontSize: 22, fontFamily: "Fraunces, serif",
            fontWeight: 400, color: g.color,
            offsetCenter: [0, "10%"]
          },
          data: [{ value: g.value }]
        }]
      });
    });

    // Radar
    const radarEl = radarRef.current;
    if (radarEl) {
      const radar = ec.init(radarEl);
      instances.push(radar);
      radar.setOption({
        animation: true, animationDuration: 1400, animationEasing: "cubicOut",
        tooltip: { trigger: "item" },
        radar: {
          indicator: [
            { name: "Novelty",          max: 100 },
            { name: "Feasibility",      max: 100 },
            { name: "Research Gap",     max: 100 },
            { name: "Citation Support", max: 100 },
            { name: "Overall",          max: 100 },
          ],
          shape: "polygon",
          radius: "65%",
          center: ["50%", "52%"],
          axisName: { color: "#6B6860", fontSize: 11, fontFamily: "Instrument Sans, sans-serif", fontWeight: 600 },
          splitLine: { lineStyle: { color: "#E2DFD8" } },
          splitArea: { show: true, areaStyle: { color: ["#FDFCFA", "#F7F5F0"] } },
          axisLine: { lineStyle: { color: "#E2DFD8" } },
        },
        series: [{
          type: "radar",
          data: [{
            value: [d.novelty_score, d.feasibility_score, d.research_gap_score, citationSupport, d.overall_confidence],
            name: "Research Profile",
            symbol: "circle", symbolSize: 5,
            areaStyle: { color: "rgba(184,147,90,0.15)" },
            lineStyle: { color: "#B8935A", width: 2 },
            itemStyle: { color: "#B8935A" }
          }]
        }]
      });
    }

    // Bar chart (top papers)
    const barEl = barRef.current;
    if (barEl && d.top_papers?.length) {
      const bar = ec.init(barEl);
      instances.push(bar);
      const papers = d.top_papers.slice(0, 5);
      bar.setOption({
        animation: true, animationDuration: 1200, animationEasing: "cubicOut",
        grid: { top: 10, bottom: 20, left: 16, right: 60, containLabel: true },
        tooltip: {
          trigger: "axis", axisPointer: { type: "shadow" },
          formatter: (p: { dataIndex: number; value: number }[]) =>
            `${(papers[p[0].dataIndex]?.title ?? "").replace(/[<>&]/g, "")}<br/>Relevance: <b>${p[0].value}</b>`
        },
        xAxis: {
          type: "value", max: 100,
          axisLabel: { fontSize: 10, color: "#C4C2BC" },
          splitLine: { lineStyle: { color: "#F0EDE8" } },
          axisLine: { show: false }, axisTick: { show: false }
        },
        yAxis: {
          type: "category",
          data: papers.map(p => {
            // Truncate long titles for the y-axis
            const t = (p.title || "Untitled").replace(/\(.*?\)/g, "").trim();
            return t.length > 28 ? t.slice(0, 26) + "…" : t;
          }),
          axisLabel: { fontSize: 11, color: "#6B6860", fontFamily: "Instrument Sans, sans-serif" },
          axisLine: { show: false }, axisTick: { show: false }
        },
        series: [{
          type: "bar", barMaxWidth: 20, barBorderRadius: [0, 6, 6, 0],
          data: papers.map((p, i) => ({
            value: Math.round(p.relevance_score),
            itemStyle: {
              color: {
                type: "linear", x: 0, y: 0, x2: 1, y2: 0,
                colorStops: [
                  { offset: 0, color: BAR_COLOR_STOPS[i]?.[0] ?? "#B8935A" },
                  { offset: 1, color: BAR_COLOR_STOPS[i]?.[1] ?? "#D4B07A" }
                ]
              }
            }
          })),
          label: {
            show: true, position: "right",
            fontSize: 11, fontWeight: 700,
            color: "#6B6860",
            formatter: "{c}"
          }
        }]
      });
    }

    // Flow chart (derived from methodology steps)
    const flowEl = flowRef.current;
    if (flowEl && d.proposed_methodology?.length) {
      const flow = ec.init(flowEl);
      instances.push(flow);

      const steps = d.proposed_methodology.slice(0, 5);
      const nodeCount = steps.length;
      // Evenly space nodes horizontally across the chart (60 → 680)
      const xPositions = nodeCount === 1
        ? [370]
        : steps.map((_, i) => Math.round(60 + i * (620 / (nodeCount - 1))));

      // Graph nodes need unique names; suffix duplicates with invisible spacing
      const seen = new Map<string, number>();
      const nodes = steps.map((raw, i) => {
        const { text } = parseStep(raw, i);
        let name = flowLabel(text) || `Step ${i + 1}`;
        const n = seen.get(name) ?? 0;
        seen.set(name, n + 1);
        if (n) name = `${name}${"​".repeat(n)}`;
        return { name, x: xPositions[i], y: 110, color: FLOW_COLORS[i] ?? "#B8935A" };
      });

      flow.setOption({
        animation: true, animationDuration: 1000,
        tooltip: { show: false },
        series: [{
          type: "graph",
          layout: "none",
          symbolSize: 60,
          roam: false,
          label: {
            show: true, fontSize: 10, fontFamily: "Instrument Sans, sans-serif",
            fontWeight: 600, color: "white", lineHeight: 14
          },
          edgeSymbol: ["none", "arrow"],
          edgeSymbolSize: [0, 8],
          lineStyle: { color: "#E2DFD8", width: 2, curveness: 0 },
          data: nodes.map(n => ({
            name: n.name, x: n.x, y: n.y,
            itemStyle: { color: n.color, borderColor: "white", borderWidth: 2 },
            symbol: "roundRect",
            symbolSize: [90, 52],
            label: { formatter: n.name }
          })),
          links: nodes.slice(0, -1).map((n, i) => ({
            source: n.name, target: nodes[i + 1].name,
            lineStyle: { color: "#D4C4A8", width: 2 }
          }))
        }]
      });
    }

    // Window resize handler
    const onResize = () => instances.forEach(c => c.resize());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    if (!echartsReady || !evalJson) return;
    const cleanup = initCharts(evalJson);
    return () => {
      cleanup?.();
      chartInstances.current.forEach((c: unknown) => {
        (c as { dispose: () => void }).dispose?.();
      });
      chartInstances.current = [];
    };
  }, [echartsReady, evalJson, initCharts]);

  // ── Downloads & transcript ─────────────────────────────────────────────────

  const handleDownloadPDF = () => {
    window.location.href = apiUrl(`/api/session/${sessionId}/pdf`);
  };

  const download = (fmt: "markdown" | "bibtex" | "docx") => {
    window.location.href = apiUrl(`/api/session/${sessionId}/export/${fmt}`);
  };

  const toggleTranscript = async () => {
    const next = !transcriptOpen;
    setTranscriptOpen(next);
    if (next && !transcript) {
      try {
        setTranscript(await apiJson<Transcript>(`/api/session/${sessionId}/transcript`));
      } catch (err: unknown) {
        setTranscriptError(err instanceof Error ? err.message : "Could not load the transcript.");
      }
    }
  };

  // ── Derived display values ─────────────────────────────────────────────────

  const sessionChip = sessionId ? sessionId.slice(0, 8).toUpperCase() : "——";
  const ragas = evalJson?.ragas_score ?? 0;
  const isLowConfidence = evalJson?.low_confidence_flag ?? false;
  const confidenceLabel = isLowConfidence
    ? `⚠ Low Confidence · RAGAS ${ragas.toFixed(2)}`
    : `✓ High Confidence · RAGAS ${ragas.toFixed(2)}`;
  const repairRounds = Math.max(0, (evalJson?.attempts.length ?? 1) - 1);
  const paperCount = evalJson ? (evalJson.references_meta.length || evalJson.references.length) : 0;
  const rationale = evalJson?.score_rationale;
  const hasRationale = !!rationale && Object.values(rationale).some(Boolean);
  const auditCounts = (evalJson?.claim_audit ?? []).reduce<Record<string, number>>((acc, r) => {
    if (!r.resolved) acc[r.verdict] = (acc[r.verdict] ?? 0) + 1;
    return acc;
  }, {});
  const rerunHref = evalJson
    ? `/?mode=2&input=${encodeURIComponent(evalJson.refined_hypothesis)}&parent=${sessionId}`
    : "/";

  function rangeText(key: "novelty" | "feasibility" | "research_gap" | "overall"): string | null {
    if (!evalJson) return null;
    const [lo, hi] = evalJson.score_ranges[key];
    if (lo === hi) return evalJson.score_samples > 1 ? `${evalJson.score_samples} reviewers agree` : null;
    return `range ${lo}–${hi} · ${evalJson.score_samples} reviewers`;
  }

  function evidenceFor(r: ClaimAuditRecord) {
    if (!r.paper_title) return <span className="audit-reason">{r.reason || "No retrieved paper addresses this claim."}</span>;
    return (
      <>
        {r.paper_url
          ? <a href={r.paper_url} target="_blank" rel="noreferrer" className="audit-paper">{r.paper_title}</a>
          : <span className="audit-paper">{r.paper_title}</span>}
        {r.quote && <div className="audit-quote">“{r.quote}”</div>}
        {!r.quote && r.reason && <div className="audit-reason">{r.reason}</div>}
      </>
    );
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <>
      {/* ECharts from CDN — loaded once, after interactive */}
      <Script
        src="https://cdnjs.cloudflare.com/ajax/libs/echarts/5.4.3/echarts.min.js"
        strategy="afterInteractive"
        // onReady also fires when the script is already cached (a second report visit in the same tab);
        // onLoad only fires on the first load, which left the charts blank on later visits.
        onReady={() => setEchartsReady(true)}
      />

      <style dangerouslySetInnerHTML={{ __html: `
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

        html { scroll-behavior: smooth; }

        body {
          background: var(--bg);
          font-family: 'Instrument Sans', sans-serif;
          color: var(--ink);
          font-size: 14px;
          line-height: 1.6;
        }

        .dot-grid {
          position: fixed; inset: 0;
          background-image: radial-gradient(circle, rgba(14,14,12,0.07) 1px, transparent 1px);
          background-size: 28px 28px;
          pointer-events: none; z-index: 0;
        }

        .topbar {
          position: sticky; top: 0; z-index: 100;
          background: rgba(247,245,240,0.92);
          backdrop-filter: blur(12px);
          border-bottom: 1px solid var(--border);
          display: flex; align-items: center; justify-content: space-between;
          padding: 0 48px; height: 60px;
        }

        .logo { display: flex; align-items: center; gap: 10px; }
        .logo-mark {
          width: 26px; height: 26px; border: 1.5px solid var(--amber);
          border-radius: 6px; display: flex; align-items: center; justify-content: center;
        }
        .logo-mark::before { content: ''; width: 9px; height: 9px; background: var(--amber); border-radius: 2px; }
        .logo-text { font-size: 13px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }

        .topbar-right { display: flex; align-items: center; gap: 12px; }

        .chip {
          font-size: 11px; font-weight: 600; letter-spacing: 0.06em;
          background: var(--white); border: 1px solid var(--border);
          padding: 5px 12px; border-radius: 20px; color: var(--ink-muted);
          text-transform: uppercase;
        }

        .download-btn {
          display: flex; align-items: center; gap: 8px;
          background: var(--ink); color: white;
          border: none; border-radius: 8px;
          padding: 9px 18px;
          font-family: 'Instrument Sans', sans-serif;
          font-size: 13px; font-weight: 600; cursor: pointer;
          transition: all 0.2s ease;
        }
        .download-btn:hover { background: var(--amber); transform: translateY(-1px); box-shadow: 0 4px 14px rgba(14,14,12,0.15); }

        .page {
          position: relative; z-index: 1;
          max-width: 900px; margin: 0 auto;
          padding: 52px 48px 100px;
        }

        .report-header {
          margin-bottom: 52px;
          opacity: 0; transform: translateY(12px);
          animation: fadeUp 0.6s ease 0.1s forwards;
        }

        .report-eyebrow {
          display: flex; align-items: center; gap: 8px; margin-bottom: 16px;
        }
        .eyebrow-line { width: 24px; height: 1px; background: var(--amber); }
        .eyebrow-text { font-size: 11px; font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase; color: var(--amber); }

        .report-title {
          font-family: 'Fraunces', serif;
          font-size: clamp(28px, 4vw, 42px);
          font-weight: 300; line-height: 1.15;
          letter-spacing: -0.02em; color: var(--ink);
          margin-bottom: 16px;
        }
        .report-title em { font-style: italic; color: var(--amber); }

        .report-meta { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
        .meta-item {
          display: flex; align-items: center; gap: 6px;
          font-size: 12px; color: var(--ink-muted);
        }
        .meta-dot { width: 4px; height: 4px; border-radius: 50%; background: var(--ink-faint); }

        .confidence-badge {
          display: inline-flex; align-items: center; gap: 6px;
          background: var(--green-pale); border: 1px solid rgba(58,125,92,0.25);
          color: var(--green); padding: 5px 12px; border-radius: 20px;
          font-size: 12px; font-weight: 600;
        }

        .section {
          margin-bottom: 52px;
          opacity: 0; transform: translateY(12px);
          animation: fadeUp 0.6s ease forwards;
        }

        .section-header {
          display: flex; align-items: center; gap: 12px;
          margin-bottom: 20px;
          padding-bottom: 12px;
          border-bottom: 1px solid var(--border);
        }

        .section-num {
          font-family: 'Fraunces', serif;
          font-size: 13px; color: var(--amber); font-weight: 400;
        }

        .section-title {
          font-size: 11px; font-weight: 700; letter-spacing: 0.1em;
          text-transform: uppercase; color: var(--ink);
        }

        .exec-summary {
          font-size: 16px; line-height: 1.75; color: var(--ink-muted);
          background: var(--white); border: 1px solid var(--border);
          border-left: 3px solid var(--amber);
          border-radius: 0 10px 10px 0;
          padding: 20px 24px;
        }
        .exec-summary strong { color: var(--ink); font-weight: 600; }

        .charts-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 16px;
          margin-bottom: 16px;
        }

        .chart-card {
          background: var(--white); border: 1px solid var(--border);
          border-radius: 12px; padding: 20px;
          transition: box-shadow 0.2s ease;
        }
        .chart-card:hover { box-shadow: 0 4px 20px rgba(14,14,12,0.07); }

        .chart-card.full { grid-column: 1 / -1; }

        .chart-label {
          font-size: 11px; font-weight: 700; letter-spacing: 0.08em;
          text-transform: uppercase; color: var(--ink-faint);
          margin-bottom: 12px;
        }

        .chart-container { width: 100%; }

        .gauges-row {
          display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
        }

        .gauge-card {
          background: var(--white); border: 1px solid var(--border);
          border-radius: 12px; padding: 16px 12px; text-align: center;
          transition: all 0.2s ease;
        }
        .gauge-card:hover { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(14,14,12,0.08); }

        .sw-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }

        .sw-card {
          background: var(--white); border: 1px solid var(--border);
          border-radius: 12px; padding: 20px;
        }

        .sw-card.strengths { border-top: 3px solid var(--green); }
        .sw-card.weaknesses { border-top: 3px solid var(--red); }

        .sw-title {
          font-size: 12px; font-weight: 700; letter-spacing: 0.08em;
          text-transform: uppercase; margin-bottom: 14px;
        }
        .sw-card.strengths .sw-title { color: var(--green); }
        .sw-card.weaknesses .sw-title { color: var(--red); }

        .sw-item {
          display: flex; gap: 10px; align-items: flex-start;
          margin-bottom: 10px; font-size: 13px; line-height: 1.5; color: var(--ink-muted);
        }
        .sw-icon { flex-shrink: 0; font-size: 12px; margin-top: 1px; }

        .chaos-callout {
          background: var(--chaos-pale);
          border: 1.5px solid #8B9BC4;
          border-radius: 12px; padding: 20px 24px;
          position: relative; overflow: hidden;
        }
        .chaos-callout::before {
          content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
          background: linear-gradient(90deg, var(--chaos), #8B9BC4, var(--chaos));
        }
        .chaos-header { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
        .chaos-badge {
          font-size: 10px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
          background: var(--chaos); color: white; padding: 3px 8px; border-radius: 4px;
        }
        .chaos-constraint {
          font-size: 14px; font-weight: 600; color: var(--chaos);
          margin-bottom: 10px; font-style: italic;
        }
        .chaos-response { font-size: 13px; color: var(--ink-muted); line-height: 1.6; }

        .methodology-steps {
          display: flex; flex-direction: column; gap: 8px;
        }
        .method-step {
          display: flex; gap: 14px; align-items: flex-start;
          background: var(--white); border: 1px solid var(--border);
          border-radius: 10px; padding: 14px 16px;
          transition: all 0.2s ease;
        }
        .method-step:hover { border-color: var(--amber-light); background: var(--amber-pale); }
        .step-num {
          font-family: 'Fraunces', serif;
          font-size: 20px; font-weight: 400; color: var(--amber);
          line-height: 1; flex-shrink: 0; width: 28px;
        }
        .step-body { flex: 1; }
        .step-title { font-size: 13px; font-weight: 600; color: var(--ink); margin-bottom: 3px; }
        .step-desc { font-size: 12px; color: var(--ink-muted); line-height: 1.5; }

        .references-list { display: flex; flex-direction: column; gap: 8px; }
        .ref-item {
          display: flex; gap: 12px;
          background: var(--white); border: 1px solid var(--border);
          border-radius: 8px; padding: 12px 16px;
          font-size: 12px; color: var(--ink-muted); line-height: 1.5;
        }
        .ref-num {
          font-family: 'Fraunces', serif; font-size: 14px;
          color: var(--amber); flex-shrink: 0; width: 20px;
        }


        .confidence-badge.low {
          background: var(--red-pale); border-color: rgba(192,80,58,0.3); color: var(--red);
        }

        .actions-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
        .action-btn {
          display: inline-flex; align-items: center; gap: 6px;
          font-family: 'Instrument Sans', sans-serif; font-size: 12px; font-weight: 600;
          color: var(--ink-muted); background: var(--white); border: 1px solid var(--border);
          padding: 7px 13px; border-radius: 8px; cursor: pointer; text-decoration: none;
          transition: all 0.2s ease;
        }
        .action-btn:hover { color: var(--amber); border-color: var(--amber-light); background: var(--amber-pale); }
        .action-btn.primary { color: white; background: var(--amber); border-color: var(--amber); }
        .action-btn.primary:hover { background: #A07848; color: white; }

        .gauge-range { font-size: 10px; color: var(--ink-faint); margin-top: 2px; }

        .rationale-card {
          background: var(--white); border: 1px solid var(--border);
          border-radius: 12px; padding: 16px 20px; margin-top: 16px;
        }
        .rationale-row { display: flex; gap: 12px; font-size: 12px; line-height: 1.55; color: var(--ink-muted); margin-bottom: 8px; }
        .rationale-row:last-child { margin-bottom: 0; }
        .rationale-key {
          flex-shrink: 0; width: 96px; font-size: 10px; font-weight: 700; letter-spacing: 0.08em;
          text-transform: uppercase; color: var(--ink); padding-top: 2px;
        }

        .audit-summary { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
        .audit-list { display: flex; flex-direction: column; gap: 8px; }
        .audit-row {
          display: grid; grid-template-columns: 104px 1fr; gap: 14px;
          background: var(--white); border: 1px solid var(--border);
          border-radius: 10px; padding: 12px 16px;
        }
        .audit-row.resolved { opacity: 0.6; }
        .verdict-badge {
          align-self: start; justify-self: start;
          font-size: 10px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
          padding: 3px 8px; border-radius: 4px; border: 1px solid var(--border);
          background: var(--bg); color: var(--ink-muted); white-space: nowrap;
        }
        .verdict-badge.supported { background: var(--green-pale); color: var(--green); border-color: rgba(58,125,92,0.25); }
        .verdict-badge.partial { background: var(--amber-pale); color: var(--amber); border-color: var(--amber-light); }
        .verdict-badge.unsupported, .verdict-badge.contradicted { background: var(--red-pale); color: var(--red); border-color: rgba(192,80,58,0.25); }
        .audit-claim { font-size: 13px; color: var(--ink); line-height: 1.5; }
        .audit-round { font-size: 10px; font-weight: 700; color: var(--ink-faint); letter-spacing: 0.06em; margin-right: 6px; }
        .audit-evidence { font-size: 12px; color: var(--ink-muted); margin-top: 6px; line-height: 1.5; }
        .audit-paper { color: var(--ink); font-weight: 600; text-decoration: none; }
        a.audit-paper:hover { color: var(--amber); }
        .audit-quote { font-style: italic; margin-top: 3px; }
        .audit-reason { font-style: normal; }
        .audit-resolution { font-size: 11px; font-weight: 600; color: var(--amber); margin-top: 4px; }

        .transcript-toggle { margin-bottom: 12px; }
        .transcript-round {
          background: var(--white); border: 1px solid var(--border);
          border-radius: 10px; padding: 16px 18px; margin-bottom: 8px;
        }
        .transcript-head {
          font-size: 11px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
          color: var(--amber); margin-bottom: 8px;
        }
        .transcript-body { font-size: 13px; line-height: 1.65; color: var(--ink-muted); white-space: pre-wrap; }
        .transcript-claims { margin-top: 10px; padding-left: 18px; font-size: 12px; color: var(--ink-muted); line-height: 1.55; }

        .ref-item a { color: var(--ink-muted); }
        .ref-item a:hover { color: var(--amber); }

        .section:nth-child(8) { animation-delay: 0.58s; }
        .section:nth-child(9) { animation-delay: 0.64s; }
        .section:nth-child(10) { animation-delay: 0.7s; }

        @media (max-width: 700px) {
          .audit-row { grid-template-columns: 1fr; gap: 6px; }
          .rationale-row { flex-direction: column; gap: 2px; }
        }

        @keyframes fadeUp { to { opacity: 1; transform: translateY(0); } }

        .section:nth-child(1) { animation-delay: 0.15s; }
        .section:nth-child(2) { animation-delay: 0.22s; }
        .section:nth-child(3) { animation-delay: 0.28s; }
        .section:nth-child(4) { animation-delay: 0.34s; }
        .section:nth-child(5) { animation-delay: 0.4s; }
        .section:nth-child(6) { animation-delay: 0.46s; }
        .section:nth-child(7) { animation-delay: 0.52s; }

        @media (max-width: 700px) {
          .page { padding: 32px 20px 80px; }
          .topbar { padding: 0 20px; }
          .charts-grid, .sw-grid, .gauges-row { grid-template-columns: 1fr; }
          .charts-grid .chart-card.full { grid-column: 1; }
        }
      ` }} />

      <div className="dot-grid" />

      {/* Topbar */}
      <nav className="topbar">
        <div className="logo">
          <div className="logo-mark" />
          <span className="logo-text">Research Council</span>
        </div>
        <div className="topbar-right">
          <span className="chip">Session #{sessionChip}</span>
          <button className="download-btn" onClick={handleDownloadPDF} disabled={!evalJson}>
            ↓ Download PDF
          </button>
        </div>
      </nav>

      {/* Loading / pending / error states — inside page wrapper so layout matches */}
      {(loading || error || pending) && (
        <main className="page">
          <div className="report-header">
            <div className="report-eyebrow">
              <div className="eyebrow-line" />
              <span className="eyebrow-text">Research Evaluation Report</span>
            </div>
            <p style={{ fontSize: 16, color: "var(--ink-muted)", marginTop: 12 }}>
              {loading ? "Loading report…"
                : error ? error
                : "The debate is still running — this page will update when the report is ready."}
            </p>
            {(error || pending) && (
              <div className="actions-row">
                {pending && <a className="action-btn" href={`/council/${sessionId}`}>Watch the debate →</a>}
                <a className="action-btn" href="/">← New session</a>
              </div>
            )}
          </div>
        </main>
      )}

      {/* Full report — only rendered when data is available */}
      {!loading && !error && !pending && evalJson && (
        <main className="page">

          {/* Report Header */}
          <div className="report-header">
            <div className="report-eyebrow">
              <div className="eyebrow-line" />
              <span className="eyebrow-text">Research Evaluation Report</span>
            </div>
            <h1 className="report-title">
              {evalJson.refined_hypothesis || meta?.hypothesis || "Untitled hypothesis"}
            </h1>
            <div className="report-meta">
              <div className="meta-item">📅 {meta?.created_at ? formatDate(meta.created_at) : "—"}</div>
              <div className="meta-dot" />
              <div className="meta-item">{paperCount} papers cited</div>
              <div className="meta-dot" />
              <div className="meta-item">5 debate rounds{repairRounds ? ` + ${repairRounds} repair` : ""}</div>
              {evalJson.model && (<><div className="meta-dot" /><div className="meta-item">{evalJson.model}</div></>)}
              {evalJson.cost_usd > 0 && (<><div className="meta-dot" /><div className="meta-item">{formatCost(evalJson.cost_usd)}</div></>)}
              <div className="meta-dot" />
              <div className={`confidence-badge ${isLowConfidence ? "low" : ""}`}>{confidenceLabel}</div>
            </div>
            <div className="actions-row">
              <a className="action-btn primary" href={rerunHref}>↻ Run again with refined hypothesis</a>
              {meta?.parent_session_id && (
                <a className="action-btn" href={`/compare?a=${meta.parent_session_id}&b=${sessionId}`}>⇄ Compare with previous run</a>
              )}
              <button className="action-btn" onClick={() => download("markdown")}>↓ Markdown</button>
              <button className="action-btn" onClick={() => download("docx")}>↓ Word</button>
              <button className="action-btn" onClick={() => download("bibtex")}>↓ BibTeX</button>
            </div>
          </div>

          {/* 1. Executive Summary */}
          <div className="section">
            <div className="section-header">
              <span className="section-num">01</span>
              <span className="section-title">Executive Summary</span>
            </div>
            <div className="exec-summary">
              {evalJson.refined_hypothesis}
              {evalJson.original_hypothesis && evalJson.original_hypothesis !== evalJson.refined_hypothesis && (
                <div style={{ fontSize: 13, marginTop: 10 }}>
                  <strong>Original hypothesis:</strong> {evalJson.original_hypothesis}
                </div>
              )}
            </div>
          </div>

          {/* 2. Idea Evaluation */}
          <div className="section">
            <div className="section-header">
              <span className="section-num">02</span>
              <span className="section-title">Idea Evaluation</span>
            </div>

            {/* Gauges */}
            <div className="gauges-row" style={{ marginBottom: 16 }}>
              {([
                { ref: gauge0Ref, label: "Novelty", key: "novelty" },
                { ref: gauge1Ref, label: "Feasibility", key: "feasibility" },
                { ref: gauge2Ref, label: "Research Gap", key: "research_gap" },
                { ref: gauge3Ref, label: "Citation Support", key: null },
              ] as const).map(({ ref, label, key }) => (
                <div key={label} className="gauge-card">
                  <div ref={ref} style={{ height: 120, width: "100%" }} />
                  <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--ink-faint)", marginTop: 4 }}>
                    {label}
                  </div>
                  {key && rangeText(key) && <div className="gauge-range">{rangeText(key)}</div>}
                </div>
              ))}
            </div>

            {/* Radar + Bar */}
            <div className="charts-grid">
              <div className="chart-card">
                <div className="chart-label">Research Profile — Radar</div>
                <div ref={radarRef} className="chart-container" style={{ height: 280 }} />
              </div>
              <div className="chart-card">
                <div className="chart-label">Literature Relevance — Top Papers</div>
                <div ref={barRef} className="chart-container" style={{ height: 280 }} />
              </div>
            </div>

            {hasRationale && rationale && (
              <div className="rationale-card">
                <div className="chart-label">Why these scores</div>
                {([
                  ["Novelty", rationale.novelty],
                  ["Feasibility", rationale.feasibility],
                  ["Research gap", rationale.research_gap],
                  ["Overall", rationale.overall],
                ] as const).filter(([, text]) => text).map(([label, text]) => (
                  <div key={label} className="rationale-row">
                    <span className="rationale-key">{label}</span>
                    <span>{text}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 3. Strengths & Weaknesses */}
          <div className="section">
            <div className="section-header">
              <span className="section-num">03</span>
              <span className="section-title">Strengths & Weaknesses</span>
            </div>
            <div className="sw-grid">
              <div className="sw-card strengths">
                <div className="sw-title">✓ Strengths</div>
                {evalJson.strengths.map((s, i) => (
                  <div key={i} className="sw-item">
                    <span className="sw-icon">→</span> {s}
                  </div>
                ))}
              </div>
              <div className="sw-card weaknesses">
                <div className="sw-title">✗ Weaknesses & Risks</div>
                {evalJson.weaknesses.map((w, i) => (
                  <div key={i} className="sw-item">
                    <span className="sw-icon">→</span> {w}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* 4. Chaos Protocol Response */}
          <div className="section">
            <div className="section-header">
              <span className="section-num">04</span>
              <span className="section-title">Chaos Protocol Response</span>
            </div>
            <div className="chaos-callout">
              <div className="chaos-header">
                <span className="chaos-badge">⚡ Injected Constraint</span>
              </div>
              <div className="chaos-constraint">"{evalJson.chaos_constraint}"</div>
              <div className="chaos-response">
                <strong style={{ color: "var(--chaos)" }}>Council response:</strong>{" "}
                {evalJson.chaos_response_summary}
              </div>
            </div>
          </div>

          {/* 5. Proposed Methodology */}
          <div className="section">
            <div className="section-header">
              <span className="section-num">05</span>
              <span className="section-title">Proposed Methodology</span>
            </div>
            <div className="methodology-steps">
              {evalJson.proposed_methodology.map((raw, i) => {
                const { num, text } = parseStep(raw, i);
                // Split on first " — " or ": " to separate title from description
                const colonIdx = text.indexOf(" — ") !== -1 ? text.indexOf(" — ") : text.indexOf(": ");
                const stepTitle = colonIdx > 0 ? text.slice(0, colonIdx) : text;
                const stepDesc  = colonIdx > 0 ? text.slice(colonIdx + (text[colonIdx + 1] === "—" ? 3 : 2)) : "";
                return (
                  <div key={i} className="method-step">
                    <div className="step-num">{num}</div>
                    <div className="step-body">
                      <div className="step-title">{stepTitle}</div>
                      {stepDesc && <div className="step-desc">{stepDesc}</div>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 6. Research Flow */}
          <div className="section">
            <div className="section-header">
              <span className="section-num">06</span>
              <span className="section-title">Research Flow</span>
            </div>
            <div className="chart-card full" style={{ padding: 24 }}>
              <div className="chart-label">End-to-End Methodology — Flow Diagram</div>
              <div ref={flowRef} style={{ height: 220, width: "100%" }} />
            </div>
          </div>

          {/* 7. Claim Evidence Audit */}
          {evalJson.claim_audit.length > 0 && (
            <div className="section">
              <div className="section-header">
                <span className="section-num">07</span>
                <span className="section-title">Claim Evidence Audit</span>
              </div>
              <div className="audit-summary">
                {Object.entries(auditCounts).map(([verdict, count]) => (
                  <span key={verdict} className={`verdict-badge ${verdict}`}>{count} {VERDICT_TEXT[verdict] ?? verdict}</span>
                ))}
                {evalJson.attempts.length > 1 && (
                  <span className="verdict-badge">
                    RAGAS by attempt: {evalJson.attempts.map(a => a.ragas_score.toFixed(2)).join(" → ")}
                  </span>
                )}
              </div>
              <div className="audit-list">
                {evalJson.claim_audit.map((r, i) => (
                  <div key={i} className={`audit-row ${r.resolved ? "resolved" : ""}`}>
                    <span className={`verdict-badge ${r.verdict}`}>{VERDICT_TEXT[r.verdict] ?? r.verdict}</span>
                    <div>
                      <div className="audit-claim">
                        <span className="audit-round">{r.stage === "repair" ? "REPAIR" : `R${r.round}`}</span>
                        {r.claim}
                      </div>
                      <div className="audit-evidence">{evidenceFor(r)}</div>
                      {r.resolved && (
                        <div className="audit-resolution">
                          {r.resolved === "retracted" ? "Retracted by the Innovator in a repair round"
                            : `Revised to: ${r.revised_to}`}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 8. Debate Transcript */}
          <div className="section">
            <div className="section-header">
              <span className="section-num">{evalJson.claim_audit.length > 0 ? "08" : "07"}</span>
              <span className="section-title">Debate Transcript</span>
            </div>
            <button className="action-btn transcript-toggle" onClick={toggleTranscript}>
              {transcriptOpen ? "Hide full transcript ▲" : "Show full transcript ▼"}
            </button>
            {transcriptOpen && (
              <div>
                {transcriptError && <div className="audit-reason">{transcriptError}</div>}
                {!transcript && !transcriptError && <div className="audit-reason">Loading transcript…</div>}
                {transcript?.round_outputs.map((r, i) => (
                  <div key={i} className="transcript-round">
                    <div className="transcript-head">{roundLabel(r)}</div>
                    <div className="transcript-body">{r.content}</div>
                    {r.claims?.length > 0 && (
                      <ul className="transcript-claims">
                        {r.claims.map((c, j) => <li key={j}>{c}</li>)}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 9. References */}
          <div className="section">
            <div className="section-header">
              <span className="section-num">{evalJson.claim_audit.length > 0 ? "09" : "08"}</span>
              <span className="section-title">Key References</span>
            </div>
            <div className="references-list">
              {evalJson.references_meta.length > 0
                ? evalJson.references_meta.map((ref, i) => (
                  <div key={ref.id || i} className="ref-item">
                    <div className="ref-num">{i + 1}</div>
                    <div>
                      {[ref.authors, ref.year ? `(${ref.year})` : ""].filter(Boolean).join(" ")}
                      {(ref.authors || ref.year) ? ". " : ""}
                      {ref.title}.{" "}
                      {ref.url && <a href={ref.url} target="_blank" rel="noreferrer">{ref.url}</a>}
                    </div>
                  </div>
                ))
                : evalJson.references.map((ref, i) => (
                  <div key={i} className="ref-item">
                    <div className="ref-num">{i + 1}</div>
                    <div>{ref}</div>
                  </div>
                ))}
            </div>
          </div>

        </main>
      )}
    </>
  );
}
