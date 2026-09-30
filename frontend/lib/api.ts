// Shared backend access for all pages.
// NEXT_PUBLIC_API_BASE overrides the backend URL (default: local FastAPI on :8000).
// SSE connects to the backend directly because dev-server rewrites buffer streamed responses.

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  body: Record<string, unknown>;
  constructor(status: number, message: string, body: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

/** fetch() + JSON with readable errors (FastAPI puts messages in `detail`). */
export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(apiUrl(path), init);
  } catch {
    throw new ApiError(0, `Cannot reach the backend at ${API_BASE}. Is uvicorn running?`);
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof body.detail === "string" ? body.detail : `Request failed (${res.status})`;
    throw new ApiError(res.status, detail, body);
  }
  return body as T;
}

export function postJson<T>(path: string, payload: unknown): Promise<T> {
  return apiJson<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function postFile<T>(path: string, file: File, fields: Record<string, string> = {}): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  for (const [key, value] of Object.entries(fields)) form.append(key, value);
  return apiJson<T>(path, { method: "POST", body: form });
}

// ── Types (mirror backend/scoring/evaluation.py) ─────────────────────────────

export interface PaperSummary {
  id: string;
  title: string;
  authors: string;
  year: string;
  source: string;
  url: string;
  relevance: number;
  user_added: boolean;
}

export interface TopPaper {
  paper_id: string;
  title: string;
  url: string;
  relevance_score: number;
  summary: string;
}

export interface ReferenceMeta {
  id: string;
  title: string;
  authors: string;
  year: string;
  url: string;
  source: string;
  doi: string;
  arxiv_id: string;
  relevance: number;
}

export type Verdict = "supported" | "partial" | "unsupported" | "contradicted";

export interface ClaimAuditRecord {
  claim: string;
  round: number;
  stage: string;
  verdict: Verdict | string;
  severity: string;
  method: string;
  reason: string;
  quote: string;
  paper_id: string;
  paper_title: string;
  paper_url: string;
  resolved: string;
  revised_to: string;
}

export type ScoreKey = "novelty" | "feasibility" | "research_gap" | "overall";

export interface EvaluationJson {
  novelty_score: number;
  feasibility_score: number;
  research_gap_score: number;
  overall_confidence: number;
  score_ranges: Record<ScoreKey, [number, number]>;
  score_samples: number;
  score_rationale: Record<ScoreKey, string>;
  ragas_score: number;
  low_confidence_flag: boolean;
  refined_hypothesis: string;
  original_hypothesis: string;
  strengths: string[];
  weaknesses: string[];
  chaos_constraint: string;
  chaos_response_summary: string;
  proposed_methodology: string[];
  top_papers: TopPaper[];
  references: string[];
  references_meta: ReferenceMeta[];
  claim_audit: ClaimAuditRecord[];
  signals: Record<string, unknown>;
  attempts: { attempt: number; ragas_score: number; passed: boolean }[];
  model: string;
  cost_usd: number;
}

export interface SessionResult {
  session_id: string;
  status: string;
  mode: number;
  created_at: string;
  hypothesis: string;
  keywords: string[];
  parent_session_id: string | null;
  cost_usd: number;
  evaluation_json: EvaluationJson;
}

export interface SessionListItem {
  session_id: string;
  created_at: string;
  mode: number;
  hypothesis: string;
  status: string;
  cost_usd: number;
  parent_session_id: string | null;
  ragas_score: number | null;
  overall_confidence: number | null;
  refined_hypothesis: string | null;
}

export interface RoundOutput {
  agent: string;
  round: number;
  stage?: string;
  attempt?: number;
  content: string;
  claims: string[];
}

export interface Transcript {
  round_outputs: RoundOutput[];
}

/** Fills any field a partial/older evaluation may lack, so rendering never crashes. */
export function withDefaults(ev: Partial<EvaluationJson> | null | undefined): EvaluationJson {
  const e = ev ?? {};
  const range = (k: ScoreKey, v: number): [number, number] => e.score_ranges?.[k] ?? [v, v];
  const n = (v: unknown) => (typeof v === "number" && isFinite(v) ? v : 0);
  const list = <T,>(v: T[] | undefined) => (Array.isArray(v) ? v : []);
  const novelty = n(e.novelty_score), feas = n(e.feasibility_score), gap = n(e.research_gap_score), overall = n(e.overall_confidence);
  return {
    novelty_score: novelty,
    feasibility_score: feas,
    research_gap_score: gap,
    overall_confidence: overall,
    score_ranges: {
      novelty: range("novelty", novelty),
      feasibility: range("feasibility", feas),
      research_gap: range("research_gap", gap),
      overall: range("overall", overall),
    },
    score_samples: n(e.score_samples) || 1,
    score_rationale: { novelty: "", feasibility: "", research_gap: "", overall: "", ...(e.score_rationale ?? {}) },
    ragas_score: n(e.ragas_score),
    low_confidence_flag: Boolean(e.low_confidence_flag),
    refined_hypothesis: e.refined_hypothesis ?? "",
    original_hypothesis: e.original_hypothesis ?? "",
    strengths: list(e.strengths),
    weaknesses: list(e.weaknesses),
    chaos_constraint: e.chaos_constraint ?? "",
    chaos_response_summary: e.chaos_response_summary ?? "",
    proposed_methodology: list(e.proposed_methodology).map(String),
    top_papers: list(e.top_papers),
    references: list(e.references),
    references_meta: list(e.references_meta),
    claim_audit: list(e.claim_audit),
    signals: e.signals ?? {},
    attempts: list(e.attempts),
    model: e.model ?? "",
    cost_usd: n(e.cost_usd),
  };
}

export function formatCost(usd: number | null | undefined): string {
  if (!usd) return "$0.00";
  return usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(3)}`;
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
