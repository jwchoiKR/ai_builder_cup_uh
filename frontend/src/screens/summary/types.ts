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
}

export interface FactRow {
  alert_id: string;
  field: string | null;
  stated_value: string | null;
  correct_value: string | null;
  corrected: boolean;
  time_to_correction_ms: number | null;
  // D-096: the compliance log's columns (absent in summaries stored before it)
  span?: string | null;
  shown_at?: number | null;
  speech_end_to_shown_ms?: number | null;
  shown_to_corrected_ms?: number | "dismissed" | "uncorrected";
  corrected_text?: string | null;
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
  // D-202: attempts, failures and deadline attainment next to the latency of the successful calls
  agent_latency: Record<
    string,
    {
      p50_ms: number | null;
      p95_ms: number | null;
      calls: number;
      attempts?: number;
      failure_rate?: number;
      deadline_attainment?: number;
    }
  >;
  cache: { instant_answers: number; composed_answers: number; triage_hits: number; triage_misses: number };
}

export interface Recap {
  headline: string;
  highlights: string[];
  watch_outs: string[];
  follow_ups: string[];
}

export interface InsightTopic {
  label: string;
  buying: boolean;
  questions: number;
  askers: number;
  auto_answered: number;
  answered_by_person: number;
  unanswered: number;
  examples: string[];
  products: string[];
}

/** What viewers asked: one analysis of the stored comments after the broadcast. Every number is counted by code. */
export interface CommentInsights {
  source: "firestore" | "store";
  /** analysis: topics sorted by the model; labels: the labels stored with each question; none: no questions */
  topic_source: "analysis" | "labels" | "none";
  comments: number;
  viewers: number;
  askers: number;
  questions: number;
  reply_time_sec: Record<"auto" | "person", { n: number; p50: number | null; p95: number | null }>;
  buying: { questions: number; topics: string[]; unanswered: number };
  not_in_product_information: { questions: number; examples: string[] };
  /** comments and questions per slice of the broadcast; peak is the busiest slice for questions */
  timeline?: {
    bin_sec: number;
    bins: { start_sec: number; comments: number; questions: number; product: string | null }[];
    peak: { start_sec: number; comments: number; questions: number; product: string | null } | null;
  } | null;
  reactions: number;
  hidden: number;
  stream_reports: number;
  outcomes: { auto_answered: number; answered_by_person: number; unanswered: number };
  waited_for_a_person_by_reason: Record<string, number>;
  question_languages: Record<string, number>;
  topics: InsightTopic[];
  notes: string[];
}

export interface SummaryData {
  status: SummaryStatus;
  stats: SummaryStats;
  recap: Recap | null;
  error: string | null;
  comment_insights?: CommentInsights | null;
}
