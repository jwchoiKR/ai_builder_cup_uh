// Types mirroring backend/app/models/session.py (DEV_SPEC §6.3) and the /api payloads.
// All timestamps are server time, UTC milliseconds since epoch.

export type Role = "operator" | "host" | "viewer";
export type Route = "AUTO" | "HOST" | "OPERATOR";

export interface SwitchState {
  status: "idle" | "counting" | "pending";
  target_product_id: string | null;
  cue_count: number;
  cue_transcript_ids: string[];
  first_cue_at: number | null;
  commit_at: number | null;
  // D-349: `immediate` marks a switch the context judge made at once (the host's "Switched to … · Undo" bar)
  last_commit: { closed_segment_id: string; opened_segment_id: string; at: number; immediate?: boolean } | null;
  /** D-349: client only, the product an immediate switch verdict named, until its segment starts */
  decided_target?: string | null;
}

export interface HostCue {
  cue_id: string;
  text: string;
  preset_id: string | null;
  created_at: number;
  status: "active" | "done" | "cleared";
  done_by_transcript_id: string | null;
  /** client-side: when the cue became done (for the 2 s check then fade, §12.3.2) */
  done_at?: number;
}

export type PdCardKind =
  | "answer_question"
  | "read_question"
  | "clarify_product"
  | "shout_out"
  | "cover_point"
  | "promo"
  | "wrap_up"
  | "switch_product";
export type PdCardStatus = "active" | "done" | "dismissed" | "expired";
export type PdCardSource = "ai" | "rule";

export interface PdCard {
  card_id: string;
  kind: PdCardKind;
  say: string;
  detail: string | null;
  ref_id: string;
  created_at: number;
  hold_until: number;
  status: PdCardStatus;
  source: PdCardSource;
  /** question cards: how many viewers asked (D-113) */
  askers?: number | null;
  /** client-side: when the card became done (for short "done" fade) */
  done_at?: number;
}

export interface ActivePromo {
  promo_id: string;
  started_at: number;
  ends_at: number;
}

export interface HostSlot {
  group_id: string;
  pinned: boolean;
  on_host_since: number;
}

export interface Session {
  session_id: string;
  runsheet_id: string;
  title: string;
  status: "ready" | "live" | "ended";
  /** D-111: solo = the host runs the show alone; team = an operator is in the control room */
  show_mode?: "solo" | "team";
  started_at: number | null;
  ended_at: number | null;
  current_segment_id: string | null;
  active_promo_id: string | null;
  promo_started_at: number | null;
  pinned_notice: string | null;
  glossary_version: number;
  doc_version: number;
  settings_snapshot: Record<string, unknown>;
  pre_covered: Record<string, string[]>;
  switch: SwitchState;
  cue: HostCue | null;
  pd_card?: PdCard | null;
  host_slots: HostSlot[];
  active_promos: ActivePromo[];
  created_at: number;
}

export interface Segment {
  segment_id: string;
  product_id: string;
  order: number;
  started_at: number;
  ended_at: number | null;
  start_reason: "session_start" | "auto_speech" | "operator";
  planned_duration_sec: number;
  covered_point_ids: string[];
  ticked_item_ids?: string[]; // D-372: prompter items (prices, ingredients, cautions) the fact checker found said right
}

export interface Transcript {
  transcript_id: string;
  text: string;
  is_final: boolean;
  speech_start_at: number | null;
  speech_end_at: number;
  received_at: number;
  source: "mic" | "injected";
  segment_id: string;
  /** D-088: judged together with this previous unfinished final */
  merged_from_transcript_id?: string | null;
  judged_text?: string | null;
}

export type AlertStatus = "provisional" | "active" | "corrected" | "dismissed" | "cleared";

export interface Alert {
  alert_id: string;
  kind: "compliance" | "fact";
  status: AlertStatus;
  transcript_id: string;
  product_id: string;
  rule_id: string | null;
  severity: "HIGH" | "MEDIUM" | null;
  span: string | null;
  say_instead: string | null;
  unverified: boolean;
  /** D-303: a fact note shown as "check what was said" (one misheard number), not a correction */
  heard_check?: boolean;
  /** D-306: why the alert is unverified (the verifier's failure: http_504, client_timeout, http_429, other_error) */
  unverified_reason?: string | null;
  field: string | null;
  stated_value: string | null;
  correct_value: string | null;
  passage_id: string | null;
  quote: string | null;
  created_at: number;
  provisional_at: number | null;
  shown_at: number | null;
  host_rendered_at: number | null;
  escalated_at: number | null;
  resolved_at: number | null;
  corrected_by_transcript_id: string | null;
  corrected_text: string | null;
  host_hidden_at: number | null;
  dismissed_reason: string | null;
}

/** D-150: the session's market and broadcast language; "preview" until a sealed eval passes. */
export interface SessionMarket {
  market: string;
  name: string;
  lang: string;
  tier: "live" | "preview";
  law_checks?: boolean; // D-228: false when no law pack covers the product's category
  category?: string;
}

export interface Comment {
  comment_id: string;
  author_id: string;
  author_name: string;
  text: string;
  received_at: number;
  source: "viewer" | "script" | "pool";
  visibility: "visible" | "hidden";
  hide_category: string | null;
  kind: "pending" | "reaction" | "question" | "hide";
  analysis_id: string | null;
  group_id: string | null;
  armor?: "blocked" | "unscreened" | null; // D-125 Model Armor verdict; unscreened: never answered
}

export interface CommentAnalysis {
  analysis_id: string;
  comment_id: string;
  output: Record<string, unknown>;
  product_id: string | null;
  product_basis: "explicit" | "context" | "content" | "unknown" | "operator";
  context_product_id: string | null;
  route: Route | null;
  route_reason: string | null;
  source: "prefilter" | "cache" | "llm" | "fallback";
  latency_ms: number | null;
}

export type GroupStatus =
  | "new"
  | "composing"
  | "ready"
  | "auto_answered"
  | "needs_review"
  | "answered"
  | "rejected"
  | "closed";

export interface QuestionGroup {
  group_id: string;
  product_id: string | null;
  intent: string;
  condition_slots: Record<string, string | null>;
  canonical_question: string;
  member_comment_ids: string[];
  unique_author_ids: string[];
  first_at: number;
  last_at: number;
  route: Route;
  route_reason: string;
  status: GroupStatus;
  answer_id: string | null;
  host_slot: "none" | "on_host";
  on_host_since: number | null;
  pinned_by_operator_at: number | null;
  recalled_at: number | null;
  host_verbal_answer_transcript_id: string | null;
  host_confirmed: boolean;
  published_message_id: string | null;
  closed_reason: string | null;
  score: number;
  version: number;
}

export interface Citation {
  passage_id: string;
  quote: string;
  section?: string | null;
  doc?: string | null;
}

export interface Answer {
  answer_id: string;
  group_id: string | null;
  text: string;
  citations: Citation[];
  origin: "ai" | "operator_edit" | "operator_written";
  verified: boolean;
  verify_errors: string[];
  cache_key: string | null;
  needs_human: boolean;
  created_at: number;
}

export type MessageKind = "ai_answer" | "host_answer" | "brand_answer" | "notice" | "correction_notice";

export interface Message {
  message_id: string;
  kind: MessageKind;
  text: string;
  group_id: string | null;
  reply_to_comment_ids: string[];
  reply_to_author_names: string[];
  citations: Citation[];
  state: "pending" | "published" | "cancelled";
  created_at: number;
  publish_at: number | null;
  published_at: number | null;
  idempotency_key: string;
}

export interface AgentCall {
  call_id: string;
  agent: string;
  model: string;
  prompt_version: string;
  started_at: number;
  latency_ms: number;
  status: "ok" | "timeout" | "error" | "invalid";
  input_hash: string;
  input_preview: string;
  output: Record<string, unknown> | null;
  error: string | null;
}

export interface SessionEvent {
  seq: number;
  type: string;
  payload: any; // eslint-disable-line @typescript-eslint/no-explicit-any
}

// ---- snapshot (/api/sessions/{sid}/state) ---------------------------------------------------------

export interface FeedBurst {
  burst_id: string;
  scene: string | null;
  description: string | null;
  anchor: string;
  count: number;
}

export interface FeedState {
  pool_running: boolean;
  pool_available?: boolean; // D-337: false on a show with no demo chatter (a release show)
  armed: string[];
  fired: string[];
  bursts: FeedBurst[];
}

export interface AgentStats {
  p50_ms: number | null;
  p95_ms: number | null;
  max_ms: number | null;
  ok: number;
  timeout: number;
  error: number;
  invalid: number;
}

/** /metrics and `metrics.updated` (§8.16). Older snapshots may only carry the flat keys. */
export interface Metrics {
  header?: {
    alert_in_s: number | null; // last render latency (host ack), else server latency
    judge_p50_s: number | null;
    instant_answers: number;
    answers_total: number;
  };
  alert?: {
    last_server_ms: number | null;
    last_render_ms: number | null;
    server_p50_ms: number | null;
    server_p95_ms: number | null;
    render_p50_ms: number | null;
    render_p95_ms: number | null;
    count: number;
  };
  correction?: { p50_ms: number | null; p95_ms: number | null; count: number };
  agents?: Record<string, AgentStats>;
  answers?: { instant: number; composed: number; median_reply_ms: { instant: number | null; composed: number | null } };
  triage_cache?: { hits: number; misses: number };
  messages_by_kind?: Record<string, number>;
  comments?: number;
  instant_answers?: number;
  composed_answers?: number;
  triage_cache_hits?: number;
  triage_cache_misses?: number;
  [key: string]: unknown;
}

export interface PrompterPointView {
  point_id: string;
  text: string;
  required: boolean;
  covered: boolean;
}

export interface PrompterSnapshot {
  product_id: string;
  segment_id: string | null;
  next_product_id?: string | null;
  points?: PrompterPointView[];
  covered_point_ids: string[];
  ticked_item_ids?: string[]; // D-372
  required_total: number;
  required_covered: number;
}

export interface StateSnapshot {
  last_seq: number;
  server_time: number;
  session: Session;
  segments: Segment[];
  groups: QuestionGroup[];
  answers: Record<string, Answer>;
  host_slots: HostSlot[];
  comments: Comment[];
  messages: Message[];
  metrics: Metrics;
  feed?: FeedState;
  judge_health?: { degraded: string[] }; // D-137
  verify_health?: VerifyHealth; // D-306
  market?: SessionMarket; // D-150
  // P2 (planned): missing keys are treated as empty
  alerts?: Alert[];
  prompter?: PrompterSnapshot | null;
  transcripts?: Transcript[];
  agent_calls?: AgentCall[];
  analyses?: Record<string, CommentAnalysis>;
}

// ---- catalog (/api/catalog) -----------------------------------------------------------------------

export interface PrompterPoint {
  point_id: string;
  text: string;
  required: boolean;
}

export interface Product {
  product_id: string;
  code: string;
  name: string;
  short_name: string;
  eyebrow: string;
  tagline: string;
  doc: string;
  volume: string;
  list_price: number;
  live_price: number;
  hero_badge: string;
  aliases: string[];
  key_facts: Record<string, string>;
  prompter_points: PrompterPoint[];
  approved_claims: string[];
  not_approved_claims: string[];
  /** D-106: short host lines from the sheet's Cautions section */
  cautions?: string[];
  /** D-106: wording to avoid and an approved claim to say instead */
  avoid_saying?: { say_not: string; say: string }[];
  list_price_display: string;
  live_price_display: string;
}

export interface SetOffer {
  set_id: string;
  name: string;
  /** screen label, e.g. "Cream + Ampoule set" (D-085) */
  short_name?: string | null;
  product_ids: string[];
  live_price: number;
  live_price_display: string;
  /** promo_id -> promo set price display */
  promo_prices_display?: Record<string, string>;
}

export interface Promo {
  promo_id: string;
  kind: string;
  title: string;
  duration_sec: number;
  applies_to: string[];
  discount_pct_off_live_price: number | null;
  promo_prices: Record<string, number>;
  promo_prices_display: Record<string, string>;
  viewer_text: string;
  host_text: string;
  changes_prices: boolean;
}

export interface RunsheetItem {
  order: number;
  product_id: string;
  planned_duration_sec: number;
  required_point_ids: string[];
}

export interface Runsheet {
  runsheet_id: string;
  title: string;
  brand: string;
  language: string;
  market: string;
  items: RunsheetItem[];
  promo_ids: string[];
}

export interface Catalog {
  brand: string;
  currency: string;
  currency_symbol: string;
  products: Product[];
  set_offers: SetOffer[];
  promos: Promo[];
  runsheets: Runsheet[];
  /** passage metadata for source labels and citation side sheets */
  passages?: Record<string, { doc: string; section: string; product_id: string; text: string }>;
  /** data/templates/notices.json: cue presets, quick replies, notice templates */
  notices?: {
    host_cue_presets: { cue_id: string; label: string; text: string }[];
    operator_quick_replies: { reply_id: string; intent: string; text: string }[];
    correction_notices: { template_id: string; use_when?: string; text: string; placeholders: string[] }[];
    field_labels: Record<string, string>;
  };
  /** rule titles and source refs for alert cards */
  rules?: { rule_id: string; title: string; severity: "HIGH" | "MEDIUM"; source_ref: string; source_id?: string }[];
  intents?: {
    intent: string;
    group: string;
    route: Route;
    sensitive: boolean;
    purchase_impact: number;
    product_scope: "single" | "multi" | "none";
  }[];
  /** link to the Appendix III PDF */
  policy_pdf_url?: string;
}

export interface Health {
  status: string;
  app_env: string;
  providers: Record<string, string>;
  models: Record<string, unknown>;
  judge_mode: string;
  prompts: Record<string, string>;
  demo_tools_enabled: boolean;
  viewer_input_enabled: boolean;
}

export interface DemoStep {
  index: number;
  scene: string;
  who: string;
  action: string;
  text: string;
  arg: string | null;
  expected: string;
}

/** D-306: verifier calls with no answer this show, in total and by failure type. */
export interface VerifyHealth {
  no_answer: number;
  by: Record<string, number>;
}
