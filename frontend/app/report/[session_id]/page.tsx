"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useParams } from "next/navigation";
import Script from "next/script";

// ── Types ─────────────────────────────────────────────────────────────────────

interface TopPaper {
  title: string;
  relevance_score: number;
  summary: string;
}

interface EvaluationJson {
  novelty_score: number;
  feasibility_score: number;
  research_gap_score: number;
  overall_confidence: number;
  ragas_score: number;
  low_confidence_flag: boolean;
  refined_hypothesis: string;
  strengths: string[];
  weaknesses: string[];
  chaos_constraint: string;
  chaos_response_summary: string;
  proposed_methodology: string[];
  top_papers: TopPaper[];
  references: string[];
}

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

/** Format today's date as "D Month YYYY". */
function todayLabel(): string {
  return new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}

const FLOW_COLORS = ["#B8935A", "#9A7D4A", "#3A7D5C", "#2C3E6B", "#7A5C8A"];
const BAR_COLOR_STOPS = [
  ["#B8935A", "#D4B07A"],
  ["#3A7D5C", "#5A9D7C"],
  ["#8B9BC4", "#AABBD4"],
  ["#7A5C8A", "#9A7CAA"],
  ["#C0503A", "#E0705A"],
];

// ── Component ─────────────────────────────────────────────────────────────────

export default function ReportPage() {
  const params = useParams<{ session_id: string }>();
  const sessionId = params.session_id;

  const [evalJson, setEvalJson] = useState<EvaluationJson | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [echartsReady, setEchartsReady] = useState(false);

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

  // ── Fetch data ─────────────────────────────────────────────────────────────

  useEffect(() => {
    if (!sessionId) return;
    (async () => {
      try {
        const res = await fetch(`http://localhost:8000/api/session/${sessionId}/result`);
        if (res.status === 202) {
          setError("The report is not ready yet. Please wait for the debate to finish.");
          return;
        }
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail ?? `Request failed (${res.status})`);
        }
        const data = await res.json();
        setEvalJson(data.evaluation_json);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Failed to load report.");
      } finally {
        setLoading(false);
      }
    })();
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
          formatter: (p: { name: string; value: number }[]) =>
            `${p[0].name}<br/>Relevance: <b>${p[0].value}</b>`
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
            const t = p.title.replace(/\(.*?\)/g, "").trim();
            return t.length > 28 ? t.slice(0, 26) + "…" : t;
          }),
          axisLabel: { fontSize: 11, color: "#6B6860", fontFamily: "Instrument Sans, sans-serif" },
          axisLine: { show: false }, axisTick: { show: false }
        },
        series: [{
          type: "bar", barMaxWidth: 20, barBorderRadius: [0, 6, 6, 0],
          data: papers.map((p, i) => ({
            value: p.relevance_score,
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

      const nodes = steps.map((raw, i) => {
        const { text } = parseStep(raw, i);
        return { name: flowLabel(text) || `Step ${i + 1}`, x: xPositions[i], y: 110, color: FLOW_COLORS[i] ?? "#B8935A" };
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

  // ── Download PDF ───────────────────────────────────────────────────────────

  const handleDownloadPDF = () => {
    window.location.href = `http://localhost:8000/api/session/${sessionId}/pdf`;
  };

  // ── Derived display values ─────────────────────────────────────────────────

  const sessionChip = sessionId ? sessionId.slice(0, 8).toUpperCase() : "——";
  const ragas = evalJson?.ragas_score ?? 0;
  const isLowConfidence = evalJson?.low_confidence_flag ?? false;
  const confidenceLabel = isLowConfidence
    ? `⚠ Low Confidence · RAGAS ${ragas.toFixed(2)}`
    : `✓ High Confidence · RAGAS ${ragas.toFixed(2)}`;

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <>
      {/* ECharts from CDN — loaded once, after interactive */}
      <Script
        src="https://cdnjs.cloudflare.com/ajax/libs/echarts/5.4.3/echarts.min.js"
        strategy="afterInteractive"
        onLoad={() => setEchartsReady(true)}
      />

      <style>{`
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
      `}</style>

      <div className="dot-grid" />

      {/* Topbar */}
      <nav className="topbar">
        <div className="logo">
          <div className="logo-mark" />
          <span className="logo-text">Research Council</span>
        </div>
        <div className="topbar-right">
          <span className="chip">Session #{sessionChip}</span>
          <button className="download-btn" onClick={handleDownloadPDF}>
            ↓ Download PDF
          </button>
        </div>
      </nav>

      {/* Loading / error states — inside page wrapper so layout matches */}
      {(loading || error) && (
        <main className="page">
          <div className="report-header">
            <div className="report-eyebrow">
              <div className="eyebrow-line" />
              <span className="eyebrow-text">Research Evaluation Report</span>
            </div>
            <p style={{ fontSize: 16, color: "var(--ink-muted)", marginTop: 12 }}>
              {loading ? "Loading report…" : error}
            </p>
          </div>
        </main>
      )}

      {/* Full report — only rendered when data is available */}
      {!loading && !error && evalJson && (
        <main className="page">

          {/* Report Header */}
          <div className="report-header">
            <div className="report-eyebrow">
              <div className="eyebrow-line" />
              <span className="eyebrow-text">Research Evaluation Report</span>
            </div>
            <h1 className="report-title">
              {evalJson.refined_hypothesis}
            </h1>
            <div className="report-meta">
              <div className="meta-item">📅 {todayLabel()}</div>
              <div className="meta-dot" />
              <div className="meta-item">{evalJson.references.length} papers reviewed</div>
              <div className="meta-dot" />
              <div className="meta-item">5 debate rounds</div>
              <div className="meta-dot" />
              <div className="confidence-badge">{confidenceLabel}</div>
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
              {[
                { ref: gauge0Ref, label: "Novelty" },
                { ref: gauge1Ref, label: "Feasibility" },
                { ref: gauge2Ref, label: "Research Gap" },
                { ref: gauge3Ref, label: "Citation Support" },
              ].map(({ ref, label }) => (
                <div key={label} className="gauge-card">
                  <div ref={ref} style={{ height: 120, width: "100%" }} />
                  <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--ink-faint)", marginTop: 4 }}>
                    {label}
                  </div>
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

          {/* 7. References */}
          <div className="section">
            <div className="section-header">
              <span className="section-num">07</span>
              <span className="section-title">Key References</span>
            </div>
            <div className="references-list">
              {evalJson.references.map((ref, i) => (
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
