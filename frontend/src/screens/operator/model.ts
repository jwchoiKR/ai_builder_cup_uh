// Pure helpers for the operator control room (DEV_SPEC §12.4). No React here, so they are unit-tested.
import { translate, type Translate } from "../../app/i18n";
import { formatMmSs, onAirSegment, ownDocFirst, productById } from "../../app/selectors";
import type { ClientState, JudgeFailure } from "../../app/state";
import type { Alert, Answer, Catalog, Comment, Message, QuestionGroup, SetOffer, Transcript } from "../../app/types";

/** Default for the optional `t` of the label helpers below: English, as the tests expect. */
const EN: Translate = (en, vars) => translate("en", en, vars);

// ---- settings (values of §5 snapshotted on the session) -------------------------------------------

const SETTING_DEFAULTS: Record<string, number> = {
  HOST_TOP_N: 3,
  STALE_COMMENT_SEC: 300,
  UNDO_SWITCH_WINDOW_SEC: 60,
};

export function setting(state: ClientState, key: keyof typeof SETTING_DEFAULTS): number {
  const v = state.session?.settings_snapshot?.[key];
  return typeof v === "number" ? v : SETTING_DEFAULTS[key];
}

// ---- labels ---------------------------------------------------------------------------------------

export function sentenceCase(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

export const STREAM_ISSUE_WINDOW_MS = 120_000;

/** Viewers who reported a problem with the stream (no sound, frozen picture, lag) in the last two minutes, newest
 * comment first. The count is of viewers, so one viewer repeating it is one report. */
export function streamIssues(comments: Record<string, Comment>, now: number): { viewers: number; latest: Comment | null } {
  const recent = Object.values(comments)
    .filter((c) => c.signal === "stream_issue" && now - c.received_at <= STREAM_ISSUE_WINDOW_MS)
    .sort((a, b) => b.received_at - a.received_at);
  return { viewers: new Set(recent.map((c) => c.author_id)).size, latest: recent[0] ?? null };
}

export function intentLabel(intent: string): string {
  return sentenceCase(intent.replace(/_/g, " "));
}

/** "price", "set price", "ingredient amount" ... (templates/notices.json field_labels, else the id). */
export function fieldLabel(catalog: Catalog | null, field: string | null): string {
  if (!field) return "fact";
  return catalog?.notices?.field_labels?.[field] ?? field.replace(/_/g, " ");
}

export const PURCHASE_FIELDS = new Set(["price", "set_price", "promo", "volume", "ingredient_amount"]);

export function intentInfo(catalog: Catalog | null, intent: string) {
  return catalog?.intents?.find((i) => i.intent === intent) ?? null;
}

export const SET_INTENT = "set_price";

/** The set offer for a set-price question: the set containing the product, else the first set. */
export function setOfferFor(catalog: Catalog | null, productId: string | null | undefined) {
  const sets = catalog?.set_offers ?? [];
  return sets.find((s) => productId && s.product_ids.includes(productId)) ?? sets[0] ?? null;
}

/** Screen label of a set: its products.json short_name, else its full name (D-085). */
export function setLabel(set: SetOffer): string {
  return set.short_name || set.name;
}

/** Product label of a group; a set-price question is about the set, so it shows the set label. */
export function productLabel(catalog: Catalog | null, g: QuestionGroup, t: Translate = EN): string {
  if (g.intent === SET_INTENT) {
    const set = setOfferFor(catalog, g.product_id);
    if (set) return setLabel(set);
  }
  if (g.product_id) return productById(catalog, g.product_id)?.name ?? g.product_id;
  const scope = intentInfo(catalog, g.intent)?.product_scope;
  return scope === "multi" ? t("Both products") : scope === "none" ? t("General") : t("No product");
}

export function ruleInfo(catalog: Catalog | null, ruleId: string | null, pid?: string) {
  const rule = catalog?.rules?.find((r) => r.rule_id === ruleId);
  return rule ? { ...rule, source_ref: ownDocFirst(catalog, rule.source_ref, pid) } : null;
}

/** "Hydra Barrier Cream product sheet · Key facts", or "Active promotion" (§8.5). */
export function sourceLabel(catalog: Catalog | null, passageId: string | null, t: Translate = EN): string {
  if (!passageId) return t("Active promotion");
  if (passageId.startsWith("PROMO#")) return t("Active promotion");
  const p = catalog?.passages?.[passageId];
  if (!p) return t("Product sheet");
  const product = productById(catalog, p.product_id);
  return `${product ? t("{product} product sheet", { product: product.name }) : t("Product sheet")} · ${p.section}`;
}

export function citationLabel(section: string | null | undefined, t: Translate = EN): string {
  return `${t("Product sheet")} · ${section ?? t("source")}`;
}

export function seconds1(ms: number): string {
  return (Math.max(0, ms) / 1000).toFixed(1);
}

// ---- question desk ---------------------------------------------------------------------------------

export type ChipToneName = "neutral" | "accent" | "fact" | "risk" | "ok" | "live";

export function statusTone(label: string): ChipToneName {
  switch (label) {
    case "Needs your reply":
    case "Needs a reply · host can answer on air":
    case "Assign a product":
    case "Host answered on air · not posted":
      return "fact";
    case "Answered by AI":
    case "Answered by the host":
    case "Answered":
      return "ok";
    default:
      return "neutral";
  }
}

const DONE = new Set(["answered", "rejected", "closed"]);

export function isOpenGroup(g: QuestionGroup): boolean {
  return !DONE.has(g.status);
}

export function isStale(g: QuestionGroup, now: number, staleSec: number): boolean {
  const unanswered = !["answered", "auto_answered", "rejected", "closed"].includes(g.status);
  return unanswered && now - g.first_at >= staleSec * 1000;
}

export type ActionKey =
  | "push"
  | "recall"
  | "approve"
  | "edit"
  | "write"
  | "post_suggested"
  | "assign"
  | "reject";

export interface GroupAction {
  key: ActionKey;
  label: string;
  enabled: boolean;
  reason?: string;
}

/** Actions shown for a group and whether each is enabled (§12.4.7, §8.13, §12.10). */
export function groupActions(g: QuestionGroup, answer: Answer | null, pending: Message | null = null): GroupAction[] {
  const actions: GroupAction[] = [];
  const done = DONE.has(g.status);
  const onHost = g.host_slot === "on_host";
  const verified = Boolean(answer?.verified && answer.text);
  const verbal = Boolean(g.host_verbal_answer_transcript_id) && !done;
  if (done) return actions;
  if (onHost) actions.push({ key: "recall", label: "Take back", enabled: true });
  else actions.push({ key: "push", label: "Send to host", enabled: true });
  if (verbal) {
    actions.push({
      key: "post_suggested",
      label: "Post suggested answer",
      enabled: verified,
      reason: verified ? undefined : "No verified answer",
    });
  }
  if (g.status !== "auto_answered") {
    actions.push({
      key: "approve",
      label: "Post",
      enabled: verified && !pending,
      reason: verified ? (pending ? "A host answer is being posted" : undefined) : "Only a verified draft can be approved",
    });
    if (answer?.text) actions.push({ key: "edit", label: "Edit reply", enabled: !pending });
    actions.push({ key: "write", label: "Write reply", enabled: !pending });
    actions.push({ key: "assign", label: "Assign product", enabled: g.status !== "composing" });
  }
  actions.push({ key: "reject", label: "Reject", enabled: !pending });
  return actions;
}

export { deskTabCounts } from "../../app/selectors";

// ---- alerts ----------------------------------------------------------------------------------------

export const CORRECTED_VISIBLE_MS = 10_000;

/** Alerts for the stack: active ones, plus ones corrected less than 10 s ago (§12.4.2). */
export function stackAlerts(state: ClientState, now: number): Alert[] {
  const t = (a: Alert) => a.shown_at ?? a.created_at;
  return Object.values(state.alerts)
    .filter(
      (a) =>
        a.status === "active" ||
        (a.status === "corrected" && a.resolved_at !== null && now - a.resolved_at < CORRECTED_VISIBLE_MS),
    )
    .sort((a, b) => {
      const rank = (x: Alert) => (x.kind === "compliance" ? (x.severity === "HIGH" ? 0 : 1) : 2);
      return rank(a) - rank(b) || t(b) - t(a);
    });
}

export type AlertCardState = "active" | "escalated" | "corrected";

export function alertCardState(a: Alert): AlertCardState {
  if (a.status === "corrected") return "corrected";
  if (a.kind === "compliance" && a.escalated_at !== null) return "escalated";
  return "active";
}

export function complianceTitle(a: Alert, now: number, t: Translate = EN): string {
  if (a.status === "corrected") return t("Corrected");
  if (a.escalated_at !== null) return `${t("Not corrected")} · ${formatMmSs(now - (a.shown_at ?? a.created_at))}`;
  return t("Host correction required");
}

export function correctedLine(a: Alert, t: Translate = EN): string | null {
  if (a.status !== "corrected" || a.resolved_at === null || a.shown_at === null) return null;
  const text = a.corrected_text ? ` · '${a.corrected_text}'` : "";
  return `${t("Corrected in {s} s", { s: seconds1(a.resolved_at - a.shown_at) })}${text}`;
}

export function alertOutcome(a: Alert, t: Translate = EN): string {
  switch (a.status) {
    case "corrected":
      return a.shown_at !== null && a.resolved_at !== null ? t("Corrected in {s} s", { s: seconds1(a.resolved_at - a.shown_at) }) : t("Corrected");
    case "dismissed":
      return t("Dismissed");
    case "active":
      return a.escalated_at !== null ? t("Not corrected") : t("Active");
    default:
      return t("Checking");
  }
}

/** Speech end → alert shown (server latency), when the transcript is known. */
export function alertLatencyMs(a: Alert, transcripts: Record<string, Transcript>): number | null {
  const t = transcripts[a.transcript_id];
  return t && a.shown_at !== null ? a.shown_at - t.speech_end_at : null;
}

// ---- system cards (§12.4.4) ---------------------------------------------------------------------------

export interface SystemCard {
  key: string;
  kind: "missing_points" | "judge_failed" | "overtime" | "ai_delay";
  text: string;
  missingTexts?: string[];
}

/** D-412: the operator's words for a failed check, with the code where there is one */
export const FAILURE_CAUSES: Record<string, string> = {
  busy: "AI busy (429)",
  timeout: "AI timed out",
  error: "AI error",
  invalid: "AI answer unreadable",
};
export const FAILURE_WINDOW_MS = 300_000; // D-412: the same 5 minutes as the server's
/** D-420: which judge failed, in plain words */
const FAILURE_JUDGES: Record<string, string> = {
  compliance_judge: "Compliance check",
  fact_checker: "Fact check",
  context_judge: "Context check",
};

export function systemCards(state: ClientState, catalog: Catalog | null, now: number, t: Translate = EN): SystemCard[] {
  const cards: SystemCard[] = [];
  for (const m of state.missingPoints) {
    const texts = m.missing_texts ?? [];  // D-432: the server always sends the texts
    cards.push({
      key: `missing:${m.segment_id}`,
      kind: "missing_points",
      text: t("Switched with missing required points: {points}", { points: texts.join("; ") }),
      missingTexts: texts,
    });
  }
  // D-420: one card per unchecked line (whatever its age), listing each failed judge with its cause
  const lines = new Map<string, JudgeFailure[]>();
  for (const j of state.unchecked) lines.set(j.transcript_id, [...(lines.get(j.transcript_id) ?? []), j]);
  for (const [tid, fs] of lines) {
    const causes = fs.map((j) => `${t(FAILURE_JUDGES[j.agent ?? ""] ?? "AI check")}: ${t(FAILURE_CAUSES[j.cause ?? ""] ?? "AI error")}`);
    // D-422: the key is the failures the card covers, so a later failure on the line shows it again (live and after a
    // refresh, which carries the same events)
    const covered = fs.map((j) => j.agent ?? "").sort().join(",");
    cards.push({ key: `judge:${tid}:${covered}`, kind: "judge_failed",
      text: `${t("AI check unavailable for the last sentence")} · ${causes.join(" · ")}` });
  }
  // D-412/D-416: the failure events of the last 5 minutes, by cause (one per line and judge, as the server counts
  // them); a new failure shows the card again
  const recent = state.judgeFailures.filter((j) => j.cause && j.at !== undefined && now - j.at < FAILURE_WINDOW_MS);
  if (recent.length) {
    const by = new Map<string, number>();
    for (const j of recent) by.set(j.cause!, (by.get(j.cause!) ?? 0) + 1);
    const parts = [...by].map(([c, n]) => `${t(FAILURE_CAUSES[c] ?? "AI error")} ${n}`);
    cards.push({ key: `failures:${recent.length}:${recent[recent.length - 1].transcript_id}`, kind: "ai_delay",
      text: t("Last 5 min: {counts}", { counts: parts.join(" · ") }) });
  }
  const onAir = onAirSegment(state);
  for (const o of Object.values(state.overtime)) {
    const seg = state.segments[o.segment_id];
    const product = productById(catalog, o.product_id);
    let overMs = (o.overtime_sec ?? 0) * 1000;
    if (seg && onAir?.segment_id === seg.segment_id) {
      overMs = Math.max(overMs, now - seg.started_at - seg.planned_duration_sec * 1000);
    }
    cards.push({
      key: `overtime:${o.segment_id}`,
      kind: "overtime",
      text: t("Overtime +{time} on {product}", {
        time: formatMmSs(overMs).replace(/^0(\d:)/, "$1"),
        product: product?.name ?? o.product_id,
      }),
    });
  }
  return cards;
}

/** "Please cover: {missing_points}" filled with the closed segment's missing points. */
export function missingPointsCue(catalog: Catalog | null, texts: string[]): string {
  const preset = catalog?.notices?.host_cue_presets.find((p) => p.cue_id === "preset_missing_points");
  return (preset?.text ?? "Please cover: {missing_points}").replace("{missing_points}", texts.join("; "));
}

// ---- switch ----------------------------------------------------------------------------------------

export function undoRemainingMs(state: ClientState, now: number): number {
  const lc = state.session?.switch.last_commit;
  if (!lc || !lc.closed_segment_id) return 0;
  return Math.max(0, lc.at + setting(state, "UNDO_SWITCH_WINDOW_SEC") * 1000 - now);
}

// ---- live transcript chips ------------------------------------------------------------------------------

export interface TranscriptChip {
  tone: ChipToneName;
  text: string;
}

interface JudgeOutputLike {
  answer?: { is_answer?: boolean; matched_group_id?: string | null };
  prompter?: { covered_point_ids?: string[]; switch?: { is_transition?: boolean; target_product_id?: string | null } };
}

const CONTEXT_AGENTS = new Set(["context_judge", "utterance_judge", "judge_single"]);

export function transcriptChips(state: ClientState, catalog: Catalog | null, t: Transcript, tr: Translate = EN): TranscriptChip[] {
  const chips: TranscriptChip[] = [];
  for (const a of Object.values(state.alerts)) {
    if (a.transcript_id !== t.transcript_id) continue;
    if (a.kind === "compliance" && a.status !== "cleared") {
      chips.push({ tone: "risk", text: a.rule_id ?? tr("compliance") });
    } else if (a.kind === "fact") {
      chips.push({ tone: "fact", text: `${tr(fieldLabel(catalog, a.field))}` });
    }
  }
  // D-088: a final joined with the previous unfinished one was judged on the joined text.
  const judged = t.judged_text ?? t.text;
  if (t.merged_from_transcript_id) chips.push({ tone: "accent", text: tr("joined with previous") });
  // The judge call that carries answer and prompter: context_judge in split3 (D-099).
  const call = state.agentCalls.find(
    (c) => CONTEXT_AGENTS.has(c.agent) && c.status === "ok" && c.input_preview === judged.slice(0, 300),
  );
  const out = (call?.output ?? null) as JudgeOutputLike | null;
  if (out?.answer?.is_answer && out.answer.matched_group_id) {
    const g = state.groups[out.answer.matched_group_id];
    if (g) chips.push({ tone: "ok", text: tr("answered: {question}", { question: g.canonical_question }) });
  } else {
    const g = Object.values(state.groups).find((x) => x.host_verbal_answer_transcript_id === t.transcript_id);
    if (g) chips.push({ tone: "ok", text: tr("answered: {question}", { question: g.canonical_question }) });
  }
  for (const pid of out?.prompter?.covered_point_ids ?? []) chips.push({ tone: "accent", text: pid });
  return chips;
}

// ---- prices ----------------------------------------------------------------------------------------------

export function fillProductName(text: string, productName: string | null): string {
  return text.replace(/\{product_name\}/g, productName ?? "This product");
}
