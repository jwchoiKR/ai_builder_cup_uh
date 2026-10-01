// Pure helpers for the operator control room (DEV_SPEC §12.4). No React here, so they are unit-tested.
import { formatMmSs, onAirSegment, productById } from "../../app/selectors";
import type { ClientState } from "../../app/state";
import type { Alert, Answer, Catalog, Message, QuestionGroup, SetOffer, Transcript } from "../../app/types";

// ---- settings (values of §5 snapshotted on the session) -------------------------------------------

const SETTING_DEFAULTS: Record<string, number> = {
  HOST_TOP_N: 3,
  STALE_COMMENT_SEC: 300,
  UNDO_SWITCH_WINDOW_SEC: 60,
  SWITCH_CONSECUTIVE_CUES: 2,
  FACT_NOTE_HOST_MAX_SEC: 45,
};

export function setting(state: ClientState, key: keyof typeof SETTING_DEFAULTS): number {
  const v = state.session?.settings_snapshot?.[key];
  return typeof v === "number" ? v : SETTING_DEFAULTS[key];
}

// ---- labels ---------------------------------------------------------------------------------------

export function sentenceCase(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
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
export function productLabel(catalog: Catalog | null, g: QuestionGroup): string {
  if (g.intent === SET_INTENT) {
    const set = setOfferFor(catalog, g.product_id);
    if (set) return setLabel(set);
  }
  if (g.product_id) return productById(catalog, g.product_id)?.name ?? g.product_id;
  const scope = intentInfo(catalog, g.intent)?.product_scope;
  return scope === "multi" ? "Both products" : scope === "none" ? "General" : "No product";
}

export function ruleInfo(catalog: Catalog | null, ruleId: string | null) {
  return catalog?.rules?.find((r) => r.rule_id === ruleId) ?? null;
}

/** "Hydra Barrier Cream product sheet · Key facts", or "Active promotion" (§8.5). */
export function sourceLabel(catalog: Catalog | null, passageId: string | null): string {
  if (!passageId) return "Active promotion";
  if (passageId.startsWith("PROMO#")) return "Active promotion";
  const p = catalog?.passages?.[passageId];
  if (!p) return "Product sheet";
  const product = productById(catalog, p.product_id);
  return `${product ? `${product.name} product sheet` : "Product sheet"} · ${p.section}`;
}

export function citationLabel(section: string | null | undefined): string {
  return `Product sheet · ${section ?? "source"}`;
}

export function seconds1(ms: number): string {
  return (Math.max(0, ms) / 1000).toFixed(1);
}

// ---- question desk ---------------------------------------------------------------------------------

export type ChipToneName = "neutral" | "accent" | "fact" | "risk" | "ok" | "live";

export function statusTone(label: string): ChipToneName {
  switch (label) {
    case "Needs review":
    case "Assign a product":
    case "Host answered on air · not posted":
      return "fact";
    case "On host":
      return "accent";
    case "AI answered":
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
  if (onHost) actions.push({ key: "recall", label: "Recall", enabled: true });
  else actions.push({ key: "push", label: "Push to host", enabled: true });
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
      label: "Approve",
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

export type AlertCardState = "active" | "escalated" | "corrected" | "hidden_from_host";

export function alertCardState(a: Alert): AlertCardState {
  if (a.status === "corrected") return "corrected";
  if (a.kind === "compliance" && a.escalated_at !== null) return "escalated";
  if (a.kind === "fact" && a.host_hidden_at !== null) return "hidden_from_host";
  return "active";
}

export function complianceTitle(a: Alert, now: number): string {
  if (a.status === "corrected") return "Corrected";
  if (a.escalated_at !== null) return `Not corrected · ${formatMmSs(now - (a.shown_at ?? a.created_at))}`;
  return "Host correction required";
}

export function correctedLine(a: Alert): string | null {
  if (a.status !== "corrected" || a.resolved_at === null || a.shown_at === null) return null;
  const text = a.corrected_text ? ` · '${a.corrected_text}'` : "";
  return `Corrected in ${seconds1(a.resolved_at - a.shown_at)} s${text}`;
}

export function alertOutcome(a: Alert): string {
  switch (a.status) {
    case "corrected":
      return a.shown_at !== null && a.resolved_at !== null ? `Corrected in ${seconds1(a.resolved_at - a.shown_at)} s` : "Corrected";
    case "dismissed":
      return "Dismissed";
    case "active":
      return a.escalated_at !== null || a.host_hidden_at !== null ? "Not corrected" : "Active";
    case "cleared":
      return "Cleared";
    default:
      return "Checking";
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
  kind: "missing_points" | "judge_failed" | "overtime";
  text: string;
  missingTexts?: string[];
}

export function systemCards(state: ClientState, catalog: Catalog | null, now: number): SystemCard[] {
  const cards: SystemCard[] = [];
  for (const m of state.missingPoints) {
    const product = productById(catalog, m.product_id);
    const texts =
      m.missing_texts && m.missing_texts.length
        ? m.missing_texts
        : m.missing_point_ids.map((id) => product?.prompter_points.find((p) => p.point_id === id)?.text ?? id);
    cards.push({
      key: `missing:${m.segment_id}`,
      kind: "missing_points",
      text: `Switched with missing required points: ${texts.join("; ")}`,
      missingTexts: texts,
    });
  }
  for (const j of state.judgeFailures) {
    cards.push({ key: `judge:${j.transcript_id}`, kind: "judge_failed", text: "AI check unavailable for the last sentence" });
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
      text: `Overtime +${formatMmSs(overMs).replace(/^0(\d:)/, "$1")} on ${product?.name ?? o.product_id}`,
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

export function switchSecondsLeft(state: ClientState, now: number): number | null {
  const sw = state.session?.switch;
  if (!sw || sw.status !== "pending" || sw.commit_at === null) return null;
  return Math.max(0, Math.ceil((sw.commit_at - now) / 1000));
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

export function transcriptChips(state: ClientState, catalog: Catalog | null, t: Transcript): TranscriptChip[] {
  const chips: TranscriptChip[] = [];
  for (const a of Object.values(state.alerts)) {
    if (a.transcript_id !== t.transcript_id) continue;
    if (a.kind === "compliance" && a.status !== "cleared" && a.status !== "provisional") {
      chips.push({ tone: "risk", text: a.rule_id ?? "compliance" });
    } else if (a.kind === "fact") {
      chips.push({ tone: "fact", text: `${fieldLabel(catalog, a.field)}` });
    }
  }
  const call = state.agentCalls.find(
    (c) => (c.agent === "utterance_judge" || c.agent === "judge_single") && c.status === "ok" && c.input_preview === t.text.slice(0, 300),
  );
  const out = (call?.output ?? null) as JudgeOutputLike | null;
  if (out?.answer?.is_answer && out.answer.matched_group_id) {
    const g = state.groups[out.answer.matched_group_id];
    if (g) chips.push({ tone: "ok", text: `answered: ${g.canonical_question}` });
  } else {
    const g = Object.values(state.groups).find((x) => x.host_verbal_answer_transcript_id === t.transcript_id);
    if (g) chips.push({ tone: "ok", text: `answered: ${g.canonical_question}` });
  }
  for (const pid of out?.prompter?.covered_point_ids ?? []) chips.push({ tone: "accent", text: pid });
  const cue = state.switchChips[t.transcript_id];
  if (cue) chips.push({ tone: "ok", text: `switch cue ${cue}/${setting(state, "SWITCH_CONSECUTIVE_CUES")}` });
  return chips;
}

// ---- prices ----------------------------------------------------------------------------------------------

export function fillProductName(text: string, productName: string | null): string {
  return text.replace(/\{product_name\}/g, productName ?? "This product");
}
