// Shape of GET /api/sessions/{sid}/summary (backend/app/pipelines/summary.py, logic/summary_stats.py).

export type SummaryStatus = "computing" | "ready" | "failed" | "not_ended";

export interface MissingPoint {
  point_id: string;
  text: string;
}

export interface UnansweredGroup {
  group_id: string;
  canonical_question: string;
  unique_askers: number;
  status?: string;
  intent?: string;
}

export interface ProductStats {
  product_id: string;
  name: string;
  duration_sec: number;
  planned_duration_sec: number;
  required_points_covered: number;
  required_points_total: number;
  missing_points: MissingPoint[];
  comments: number;
  questions: number;
  groups: number;
  answered_groups: { ai_answer: number; host_answer: number; brand_answer: number };
  unanswered_groups: UnansweredGroup[];
}

export interface ComplianceRow {
  alert_id: string;
  rule_id: string | null;
  rule_title: string | null;
  severity: "HIGH" | "MEDIUM" | null;
  span: string | null;
  shown_at: number;
  speech_end_to_shown_ms: number | null;
  shown_to_corrected_ms: number | "dismissed" | "uncorrected";
  corrected_text: string | null;
  unverified: boolean;
}

export interface FactRow {
  alert_id: string;
  field: string | null;
  stated_value: string | null;
  correct_value: string | null;
  corrected: boolean;
  time_to_correction_ms: number | null;
}

export interface PromoRow {
  promo_id: string;
  title: string;
  started_at: number;
  ended_at: number | null;
  duration_sec: number | null;
}

export interface SummaryStats {
  title: string;
  session_id: string;
  started_at: number | null;
  ended_at: number | null;
  duration_sec: number;
  products: ProductStats[];
  totals: {
    comments: number;
    questions: number;
    hidden_comments: number;
    groups: number;
    messages_by_kind: Record<string, number>;
    analysed_comments: number;
  };
  general_unanswered_groups: UnansweredGroup[];
  compliance_alerts: ComplianceRow[];
  fact_alerts: FactRow[];
  promos: PromoRow[];
  agent_latency: Record<string, { p50_ms: number | null; p95_ms: number | null; calls: number }>;
  cache: { instant_answers: number; composed_answers: number; triage_hits: number; triage_misses: number };
}

export interface Recap {
  headline: string;
  highlights: string[];
  watch_outs: string[];
  follow_ups: string[];
}

export interface SummaryData {
  status: SummaryStatus;
  stats: SummaryStats;
  recap: Recap | null;
  error: string | null;
}
