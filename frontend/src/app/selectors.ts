// Pure selectors over ClientState (+ catalog, + server now). Screens read these, never raw events.
import type { Translate } from "./i18n";
import type { ClientState } from "./state";
import type {
  Alert,
  Answer,
  Catalog,
  Comment,
  HostSlot,
  Message,
  PdCard,
  Product,
  PrompterItem,
  Promo,
  QuestionGroup,
  Segment,
  Transcript,
} from "./types";

// ---- time ------------------------------------------------------------------------------------------

export function formatClock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(h)}:${pad(m)}:${pad(s)}`;
}

export function formatMmSs(ms: number): string {
  const total = Math.max(0, Math.ceil(ms / 1000));
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

/** "now", "12s", "3m", "2h" (§12.3.8). */
export function relativeTime(at: number, now: number): string {
  const s = Math.max(0, Math.floor((now - at) / 1000));
  if (s < 5) return "now";
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  return `${Math.floor(s / 3600)}h`;
}

// ---- products and segments -------------------------------------------------------------------------

export function productById(catalog: Catalog | null, pid: string | null | undefined): Product | null {
  if (!catalog || !pid) return null;
  return catalog.products.find((p) => p.product_id === pid) ?? null;
}

/** D-348: a rule source that lists several files ("A.pdf Page 2 §7; B.pdf Page 2") puts the alert product's file first. */
export function ownDocFirst(catalog: Catalog | null, sourceRef: string, pid: string | null | undefined): string {
  const docs = Object.values(catalog?.passages ?? {}).filter((p) => p.product_id === pid && p.doc).map((p) => p.doc);
  const parts = sourceRef.split("; ");
  const own = parts.filter((s) => docs.some((d) => s.startsWith(d)));
  return [...own, ...parts.filter((s) => !own.includes(s))].join("; ");
}

export function runsheetOf(state: ClientState, catalog: Catalog | null) {
  if (!catalog) return null;
  const id = state.session?.runsheet_id;
  return catalog.runsheets.find((r) => r.runsheet_id === id) ?? catalog.runsheets[0] ?? null;
}

export function productOrder(state: ClientState, catalog: Catalog | null): string[] {
  const rs = runsheetOf(state, catalog);
  return rs ? [...rs.items].sort((a, b) => a.order - b.order).map((i) => i.product_id) : [];
}

export function onAirSegment(state: ClientState): Segment | null {
  const open = Object.values(state.segments).filter((s) => s.ended_at === null);
  if (open.length) return open.sort((a, b) => b.started_at - a.started_at)[0];
  const cur = state.session?.current_segment_id;
  if (state.session?.status === "ended" && cur) return state.segments[cur] ?? null;
  return null;
}

export function onAirProduct(state: ClientState, catalog: Catalog | null): Product | null {
  return productById(catalog, onAirSegment(state)?.product_id);
}

/** Next run-sheet product; the first product before start; null after the last ("End of run sheet"). */
export function nextProduct(state: ClientState, catalog: Catalog | null): Product | null {
  const order = productOrder(state, catalog);
  const seg = onAirSegment(state);
  if (!seg) return state.session?.status === "ended" ? null : productById(catalog, order[0]);
  const i = order.indexOf(seg.product_id);
  return i >= 0 && i + 1 < order.length ? productById(catalog, order[i + 1]) : null;
}

export interface RunOfShowItem {
  order: number;
  product: Product | null;
  status: "on_air" | "next" | "done" | "planned";
  segment: Segment | null;
  elapsedMs: number;
  plannedMs: number;
  overtimeMs: number;
  requiredIds: string[];
  coveredRequired: number;
}

export function runOfShow(state: ClientState, catalog: Catalog | null, now: number): RunOfShowItem[] {
  const rs = runsheetOf(state, catalog);
  if (!rs) return [];
  const onAir = onAirSegment(state);
  const segs = Object.values(state.segments);
  const next = nextProduct(state, catalog);
  return [...rs.items]
    .sort((a, b) => a.order - b.order)
    .map((item) => {
      const mine = segs.filter((s) => s.product_id === item.product_id).sort((a, b) => b.started_at - a.started_at);
      const seg = mine[0] ?? null;
      const live = onAir?.product_id === item.product_id && onAir.ended_at === null;
      const status: RunOfShowItem["status"] = live
        ? "on_air"
        : seg && seg.ended_at !== null
          ? "done"
          : next?.product_id === item.product_id
            ? "next"
            : "planned";
      const elapsedMs = seg ? (seg.ended_at ?? now) - seg.started_at : 0;
      // D-138: the segment's own plan (it can be extended); the run-sheet plan before it starts
      const plannedMs = (seg?.planned_duration_sec ?? item.planned_duration_sec) * 1000;
      const covered = new Set([...(seg?.covered_point_ids ?? []), ...(state.session?.pre_covered[item.product_id] ?? [])]);
      return {
        order: item.order,
        product: productById(catalog, item.product_id),
        status,
        segment: seg,
        elapsedMs,
        plannedMs,
        overtimeMs: Math.max(0, elapsedMs - plannedMs),
        requiredIds: item.required_point_ids,
        coveredRequired: item.required_point_ids.filter((p) => covered.has(p)).length,
      };
    });
}

// ---- prices and promos -----------------------------------------------------------------------------

export function activePricePromo(state: ClientState, catalog: Catalog | null): Promo | null {
  const id = state.session?.active_promo_id;
  return id && catalog ? catalog.promos.find((p) => p.promo_id === id) ?? null : null;
}

export interface ActivePromoView {
  promo: Promo;
  startedAt: number;
  endsAt: number;
  remainingMs: number;
}

export function activePromos(state: ClientState, catalog: Catalog | null, now: number): ActivePromoView[] {
  if (!catalog || !state.session) return [];
  return state.session.active_promos
    .map((a) => {
      const promo = catalog.promos.find((p) => p.promo_id === a.promo_id);
      return promo ? { promo, startedAt: a.started_at, endsAt: a.ends_at, remainingMs: Math.max(0, a.ends_at - now) } : null;
    })
    .filter((x): x is ActivePromoView => x !== null);
}

export interface PriceView {
  label: "LIVE PRICE" | "TIME SALE";
  current: string; // large price
  struck: string; // small, struck-through price
  set: string; // set price (promo set price during the time sale)
  symbol: string; // D-179: the market's currency symbol ("S$", "RM")
  /** D-372: the prompter item key of each line (the server's snapshot ids, without the product code) */
  keys: { current: string; struck: string; set: string | null };
}

export function priceView(state: ClientState, catalog: Catalog | null, product: Product | null): PriceView | null {
  if (!product || !catalog) return null;
  const promo = activePricePromo(state, catalog);
  const set = catalog.set_offers.find((s) => s.product_ids.includes(product.product_id));
  const promoPrice = promo?.promo_prices_display[product.product_id];
  if (promo && promoPrice) {
    const promoSet = set ? promo.promo_prices_display[set.set_id] : undefined;
    return {
      label: "TIME SALE",
      current: promoPrice,
      struck: product.live_price_display,
      set: promoSet || set?.live_price_display || "",
      symbol: catalog.currency_symbol,
      keys: { current: `sale-price-${promo.promo_id}`, struck: "live-price",
        set: set ? (promoSet ? `set-${set.set_id}-${promo.promo_id}` : `set-${set.set_id}`) : null },
    };
  }
  return { label: "LIVE PRICE", current: product.live_price_display, struck: product.list_price_display,
    set: set?.live_price_display ?? "", symbol: catalog.currency_symbol,
    keys: { current: "live-price", struck: "list-price", set: set ? `set-${set.set_id}` : null } };
}

// ---- prompter --------------------------------------------------------------------------------------

// D-091: the prompter is the product's information for reference, not a script read in order, so it
// has no "next point".
export interface PrompterPointRow {
  point_id: string;
  text: string;
  required: boolean;
  covered: boolean;
}

export interface PrompterViewModel {
  product: Product | null;
  points: PrompterPointRow[];
  /** D-423: the server's item list for this product, rendered as is (prices, sets, ingredients, cautions) */
  items: PrompterItem[];
  /** D-372: the prompter item ids said right (the fact checker's verdicts); the only source of their ticks */
  ticked: string[];
  requiredTotal: number;
  requiredCovered: number;
}

export function prompterView(state: ClientState, catalog: Catalog | null): PrompterViewModel {
  const seg = onAirSegment(state);
  const product = productById(catalog, seg?.product_id ?? state.prompter?.product_id);
  if (!product) return { product: null, points: [], items: [], ticked: [], requiredTotal: 0, requiredCovered: 0 };
  const rs = runsheetOf(state, catalog);
  const item = rs?.items.find((i) => i.product_id === product.product_id);
  const required = new Set(item?.required_point_ids ?? []);
  const fromServer = state.prompter?.product_id === product.product_id ? state.prompter : null;
  const covered = new Set([...(fromServer?.covered_point_ids ?? []), ...(seg?.covered_point_ids ?? [])]);
  const base = fromServer?.points?.length
    ? fromServer.points.map((p) => ({ point_id: p.point_id, text: p.text, required: p.required }))
    : product.prompter_points.map((p) => ({ point_id: p.point_id, text: p.text, required: required.has(p.point_id) }));
  const points = base.map((p) => ({ ...p, covered: covered.has(p.point_id) }));
  const req = points.filter((p) => p.required);
  const ticked = [...new Set([...(fromServer?.ticked_item_ids ?? []), ...(seg?.ticked_item_ids ?? [])])];
  return {
    product,
    points,
    items: (fromServer?.items ?? []).filter((i) => i.product_id === product.product_id),
    ticked,
    requiredTotal: req.length,
    requiredCovered: req.filter((p) => p.covered).length,
  };
}

// ---- alerts ----------------------------------------------------------------------------------------

const alertTime = (a: Alert) => a.shown_at ?? a.created_at;

export function activeComplianceAlerts(state: ClientState): Alert[] {
  return Object.values(state.alerts)
    .filter((a) => a.kind === "compliance" && a.status === "active")
    .sort((a, b) => alertTime(b) - alertTime(a));
}

export interface HighAlertView {
  alert: Alert;
  position: number; // always 1: the host sees the newest (§8.4.2)
  total: number;
}

/** D-161, D-177: a red alert blocks AI PD cards this long after it was created; it stays full size on the
 *  prompter until it is corrected or dismissed, and cards show below it after the block. Same value as the server's. */
export const RED_BLOCK_MS = 20_000;

/** The red alert on the prompter: the newest active one, until corrected or dismissed (D-177). */
export function activeHighAlert(state: ClientState): HighAlertView | null {
  const high = activeComplianceAlerts(state).filter((a) => a.severity === "HIGH");
  return high.length ? { alert: high[0], position: 1, total: high.length } : null;
}

/** D-161, D-177: an alert created less than RED_BLOCK_MS ago (server time) blocks AI PD cards. The same claim said
 *  again is a new alert, so it blocks again. D-402 (user): every alert, red or orange (a MEDIUM banner or a fact
 *  note), the same way. Same rule as the server's. */
export function alertBlocking(state: ClientState, now: number): boolean {
  return Object.values(state.alerts).some((a) => (a.kind === "compliance" || a.kind === "fact") && a.status === "active"
    && now - a.created_at < RED_BLOCK_MS);
}

export function activeMediumAlerts(state: ClientState): Alert[] {
  return activeComplianceAlerts(state).filter((a) => a.severity === "MEDIUM");
}

export function factNotesForHost(state: ClientState): Alert[] {
  return Object.values(state.alerts)
    .filter((a) => a.kind === "fact" && a.status === "active")  // D-402: until corrected or dismissed
    .sort((a, b) => alertTime(b) - alertTime(a));
}

/** D-399: the newest of each group (the list is newest first) and how many there are; a null key is never grouped. */
function groupNewest<T>(items: T[], key: (x: T) => string | null): { item: T; count: number; members: T[] }[] {
  const out: { item: T; count: number; members: T[] }[] = [];
  const at = new Map<string, number>();
  for (const x of items) {
    const k = key(x);
    if (k !== null && at.has(k)) {
      const g = out[at.get(k)!];
      g.count += 1;
      g.members.push(x);
    } else {
      if (k !== null) at.set(k, out.length);
      out.push({ item: x, count: 1, members: [x] });
    }
  }
  return out;
}

/** Host banners. D-342 (review H20):
 *  a sentence with an active HIGH alert shows only that alert: its MEDIUM banners and fact notes wait in the log.
 *  D-399 (user): on the host screen only, MEDIUM alerts are grouped by the rule the model cited and fact notes by the
 *  passage id they cite (ids, never text; a note with no passage is not grouped): one card, the newest, with its count.
 *  Every alert stays its own record and handle; the operator screen lists each one. */
export function hostBanners(state: ClientState): {
  mediums: { alert: Alert; count: number; ids: string[] }[];
  facts: { alert: Alert; count: number; ids: string[] }[];
} {
  const high = new Set(activeComplianceAlerts(state).filter((a) => a.severity === "HIGH").map((a) => a.transcript_id));
  const box = ({ item: alert, count, members }: { item: Alert; count: number; members: Alert[] }) =>
    ({ alert, count, ids: members.map((a) => a.alert_id) });
  const mediums = groupNewest(activeMediumAlerts(state).filter((a) => !high.has(a.transcript_id)), (a) => a.rule_id)
    .map(box);
  const facts = groupNewest(factNotesForHost(state).filter((f) => !high.has(f.transcript_id)), (f) => f.passage_id)
    .map(box);
  return { mediums, facts };
}

/** D-420: the host's strip: how many lines are unchecked and the latest failure's cause among them, by the server's
 *  order (at, then n); after a partial recovery it is the latest of the lines still unchecked. */
export function uncheckedStrip(state: ClientState): { count: number; cause: string | null } {
  const latest = [...state.unchecked].sort((a, b) => (a.at ?? 0) - (b.at ?? 0) || (a.n ?? 0) - (b.n ?? 0)).at(-1);
  return { count: new Set(state.unchecked.map((j) => j.transcript_id)).size, cause: latest?.cause ?? null };
}

/** D-402: at most this many alert boxes on the host screen. */
export const MAX_ALERT_BOXES = 2;

export type HostBox =
  | { kind: "high"; view: HighAlertView; ids: string[]; units: number }
  | { kind: "fact"; alert: Alert; count: number; ids: string[]; units: number }
  | { kind: "medium"; alert: Alert; count: number; ids: string[]; units: number };

/** Where an active alert is for the host: in a box shown now, held behind a red on its line (D-342), or beyond the
 *  box limit (counted in "+N"). */
export type HostVisibility = "shown" | "held" | "more";

/** D-402, D-404: the host's alert stack in order (red first, then fact notes, then MEDIUM; D-342 and the grouping
 *  apply): the boxes shown, "+N" and each active alert's visibility. D-407 (user): every active red is its own box,
 *  newest first, so two reds fill the two boxes and the rest is in "+N". "+N" counts, by alert id, every active alert not
 *  visible in the boxes shown: the other reds, the alerts held by D-342 and the members of the boxes not shown. The
 *  host and operator screens both read this. */
export function hostAlertStack(state: ClientState): {
  shown: HostBox[];
  more: number;
  visibility: Record<string, HostVisibility>;
} {
  const reds = activeComplianceAlerts(state).filter((a) => a.severity === "HIGH");
  const { mediums, facts } = hostBanners(state);
  const boxes: HostBox[] = [
    ...reds.map((alert, i) => ({ kind: "high" as const, view: { alert, position: i + 1, total: reds.length },
      ids: [alert.alert_id], units: 1 })),
    ...facts.map((f) => ({ kind: "fact" as const, ...f, units: f.count })),
    ...mediums.map((m) => ({ kind: "medium" as const, ...m, units: m.count })),
  ];
  const shown = boxes.slice(0, MAX_ALERT_BOXES);
  const visibility: Record<string, HostVisibility> = {};
  for (const b of shown) for (const id of b.ids) visibility[id] = "shown";
  let more = 0;
  for (const b of boxes.slice(MAX_ALERT_BOXES)) {
    more += b.units;
    for (const id of b.ids) visibility[id] = "more";
  }
  for (const a of [...activeComplianceAlerts(state), ...factNotesForHost(state)]) {
    if (a.alert_id in visibility) continue;
    visibility[a.alert_id] = "held";  // every red is a box (D-407): what is left waits behind a red (D-342)
    more += 1;
  }
  return { shown, more, visibility };
}

// ---- D-439: how fast an alert was shown and cleared, on server times only --------------------------------

/** From the end of a line (its transcript's speech_end_at) to a server time; `typed`: the line was typed or injected,
 *  so its "speech end" is only when it was submitted. */
export interface LineTiming {
  ms: number;
  typed: boolean;
}

function fromLine(t: Transcript | undefined, at: number | null): LineTiming | null {
  return t && at !== null ? { ms: at - t.speech_end_at, typed: t.source !== "mic" } : null;
}

/** The alert's line (a merged line's last final) -> the alert shown; null when either is unknown. */
export function shownTiming(a: Alert, transcripts: Record<string, Transcript>): LineTiming | null {
  return fromLine(transcripts[a.transcript_id], a.shown_at);
}

/** The correcting line -> the alert cleared (corrected); null when either is unknown. */
export function clearedTiming(a: Alert, transcripts: Record<string, Transcript>): LineTiming | null {
  if (a.status !== "corrected" || !a.corrected_by_transcript_id) return null;
  return fromLine(transcripts[a.corrected_by_transcript_id], a.resolved_at);
}

function seconds(ms: number): string {
  return (Math.max(0, ms) / 1000).toFixed(1);
}

/** "Shown in 4.2 s" / "Cleared in 3.1 s", "(typed)" after a typed line's number; null without the data. */
export function timingLabel(kind: "shown" | "cleared", x: LineTiming | null, t: Translate): string | null {
  if (!x) return null;
  const text = t(kind === "shown" ? "Shown in {s} s" : "Cleared in {s} s", { s: seconds(x.ms) });
  return x.typed ? `${text} ${t("(typed)")}` : text;
}

/** The operator header's line: the show's alerts with a spoken line (typed lines are not counted). */
export function alertTimingStats(state: ClientState): { count: number; within5: number; slowestMs: number } | null {
  const spoken = Object.values(state.alerts)
    .filter((a) => a.status !== "cleared")
    .map((a) => shownTiming(a, state.transcripts))
    .filter((x): x is LineTiming => x !== null && !x.typed);
  if (!spoken.length) return null;
  return { count: spoken.length, within5: spoken.filter((x) => x.ms <= 5000).length,
           slowestMs: Math.max(...spoken.map((x) => x.ms)) };
}

export function alertLog(state: ClientState): Alert[] {
  return Object.values(state.alerts)
    .filter((a) => a.status !== "cleared")
    .sort((a, b) => alertTime(b) - alertTime(a));
}

/** The green "Corrected" toast: a compliance alert corrected within the last `windowMs`. */
export function recentlyCorrected(state: ClientState, now: number, windowMs = 1500): Alert | null {
  return (
    Object.values(state.alerts)
      .filter((a) => a.kind === "compliance" && a.status === "corrected" && a.resolved_at !== null && now - a.resolved_at < windowMs)
      .sort((a, b) => (b.resolved_at ?? 0) - (a.resolved_at ?? 0))[0] ?? null
  );
}

// ---- questions -------------------------------------------------------------------------------------

export function verifiedAnswer(state: ClientState, g: QuestionGroup): Answer | null {
  const a = g.answer_id ? state.answers[g.answer_id] : undefined;
  return a && a.verified ? a : null;
}

export function draftAnswer(state: ClientState, g: QuestionGroup): Answer | null {
  return g.answer_id ? state.answers[g.answer_id] ?? null : null;
}

export function pendingMessages(state: ClientState): Message[] {
  return Object.values(state.messages)
    .filter((m) => m.state === "pending")
    .sort((a, b) => a.created_at - b.created_at);
}

export interface HostSlotView {
  index: number; // 1-based
  slot: HostSlot;
  group: QuestionGroup;
  answer: Answer | null; // verified suggested answer
  pending: Message | null; // "Posting answer…"
  tag: "From your PD" | "AI answered" | "For you";
  /** D-113: where the question stands in the host's waiting list */
  waiting: "Drafting…" | "Which product?" | "Read out" | "Ready to answer" | "No answer yet";
}

export function hostSlots(state: ClientState): HostSlotView[] {
  const pending = pendingMessages(state);
  return state.hostSlots
    .map((slot) => state.groups[slot.group_id] ? { slot, group: state.groups[slot.group_id] } : null)
    .filter((x): x is { slot: HostSlot; group: QuestionGroup } => x !== null)
    .map(({ slot, group }, i) => ({
      index: i + 1,
      slot,
      group,
      answer: verifiedAnswer(state, group),
      pending: pending.find((m) => m.group_id === group.group_id) ?? null,
      tag: slot.pinned ? "From your PD" : group.status === "auto_answered" ? "AI answered" : "For you",
      waiting: waitingState(group, verifiedAnswer(state, group)),
    }));
}

const DRAFT_STEPS = {
  evidence: "Finding evidence…",
  writing: "Writing the reply…",
} as const;

/** Which step a draft is in while it is being written (the server's compose_step). */
export function draftingLabel(g: QuestionGroup): string {
  return (g.status === "composing" && g.compose_step && DRAFT_STEPS[g.compose_step]) || "Drafting…";
}

/** D-429: no question card any more, so no "On your card" state */
function waitingState(group: QuestionGroup, answer: Answer | null): HostSlotView["waiting"] {
  if (group.status === "composing") return "Drafting…";
  if (group.status === "needs_review" && group.route_reason === "unresolved_product") return "Which product?";
  if (group.status === "auto_answered") return "Read out";
  return answer ? "Ready to answer" : "No answer yet";
}

/** D-178: questions the product info does not answer, shop policy and the previous product's questions wait for the
 *  operator. In a solo show nobody watches that list, so the host sees only how many there are. */
export function unansweredCount(state: ClientState): number {
  if (state.session?.show_mode !== "solo") return 0;
  return Object.values(state.groups).filter((g) => g.route === "OPERATOR"
    && ["new", "composing", "ready", "needs_review"].includes(g.status) && !g.host_verbal_answer_transcript_id).length;
}

/** The three tabs of the question desk: what waits for a person, what is answered, and everything. */
export type DeskTab = "todo" | "answered" | "all";
/** The one list a group belongs to. Closed and rejected groups are listed only under All. */
export type DeskStatusTab = "todo" | "answered" | "closed";

export interface DeskStatus {
  label: string; // the one status chip of the row, in plain words
  tab: DeskStatusTab; // the one list the group is counted and listed under
}

const DONE_STATUSES = ["answered", "rejected", "closed"];

/** The single source of a group's desk status: its row chip and its tab always agree, and every group is in
 * exactly one of To do / Answered / closed. `publishedKind` is the kind of the message that answered the group
 * (state.messages[g.published_message_id]?.kind): it tells "Answered by the host" from a plain "Answered". */
export function deskStatus(g: QuestionGroup, publishedKind?: string | null): DeskStatus {
  const done = DONE_STATUSES.includes(g.status);
  if (g.status === "auto_answered") return { label: "Answered by AI", tab: "answered" };
  if (g.status === "answered") {
    return { label: publishedKind === "host_answer" ? "Answered by the host" : "Answered", tab: "answered" };
  }
  if (done) return { label: "Closed", tab: "closed" };
  if (g.host_verbal_answer_transcript_id) return { label: "Host answered on air · not posted", tab: "todo" };
  if (g.status === "needs_review" && g.route_reason === "unresolved_product") return { label: "Assign a product", tab: "todo" };
  if (g.status === "new" || g.status === "composing") return { label: draftingLabel(g), tab: "todo" };
  // waits for a person: the host may also say it on air (it is on the host's card, or routed to the host), or only
  // the operator can answer it
  return g.host_slot === "on_host" || g.route === "HOST"
    ? { label: "Needs a reply · host can answer on air", tab: "todo" }
    : { label: "Needs your reply", tab: "todo" };
}

export function deskTabOf(g: QuestionGroup, publishedKind?: string | null): DeskStatusTab {
  return deskStatus(g, publishedKind).tab;
}

/** Counts per list; `all` equals todo + answered + closed (closed and rejected have no tab of their own). */
export function deskTabCounts(groups: QuestionGroup[]): Record<DeskTab | "closed", number> {
  const counts: Record<DeskTab | "closed", number> = { all: groups.length, todo: 0, answered: 0, closed: 0 };
  for (const g of groups) counts[deskTabOf(g)] += 1;
  return counts;
}

/** Order inside a list: what only the operator can answer first, then what the host may say, drafts, answers. */
export function deskBucket(g: QuestionGroup): number {
  switch (deskStatus(g).label) {
    case "Needs your reply":
    case "Assign a product":
    case "Host answered on air · not posted":
      return 0;
    case "Needs a reply · host can answer on air":
      return 1;
    case "Drafting…":
      return 3;
    case "Answered by AI":
      return 4;
    case "Answered":
    case "Answered by the host":
      return 5;
    default:
      return 6;
  }
}

export function groupStatusLabel(g: QuestionGroup, publishedKind?: string | null): string {
  return deskStatus(g, publishedKind).label;
}

/** Why a question waits for a person, in plain words (the approval reason first, then the route's); null when
 * there is nothing to say (an auto-answered or answered question, or one that only waits its turn). */
export function waitReason(g: QuestionGroup): string | null {
  const byApproval: Record<string, string> = {
    health: "Health or safety",
    claim: "Claim about results",
    test_results: "About test results",
    certification: "Certificate or ethics",
    personal: "Depends on the viewer",
    outside: "Order, delivery or shop",
    host_line: "Follow-up on the host",
    unclear: "Unclear or beyond the product sheet",
  };
  const byRoute: Record<string, string> = {
    no_verified_answer: "No verified answer in the product sheet",
    previous_product: "About a product no longer on air",
    sensitive: "Sensitive topic",
  };
  if (g.approval_reason && byApproval[g.approval_reason]) return byApproval[g.approval_reason];
  return byRoute[g.route_reason] ?? null;
}

export function questionDesk(state: ClientState, tab: DeskTab = "todo"): QuestionGroup[] {
  const all = Object.values(state.groups);
  const filtered = tab === "all" ? all : all.filter((g) => deskTabOf(g) === tab);
  return filtered.sort((a, b) => deskBucket(a) - deskBucket(b) || b.score - a.score || a.first_at - b.first_at);
}

// ---- chat ------------------------------------------------------------------------------------------

export type ChatItem =
  | { kind: "comment"; at: number; comment: Comment; replies: Message[] }
  | { kind: "message"; at: number; message: Message };

const messageTime = (m: Message) => m.published_at ?? m.created_at;

/** Visible comments and published messages in time order; a reply is attached to the first visible
 * comment it answers (§12.5 "Replies render under the question they answer"). */
export function chatItems(state: ClientState): ChatItem[] {
  const comments = Object.values(state.comments)
    .filter((c) => c.visibility === "visible" && c.kind !== "hide")
    .sort((a, b) => a.received_at - b.received_at);
  const visible = new Set(comments.map((c) => c.comment_id));
  const replies = new Map<string, Message[]>();
  const standalone: ChatItem[] = [];
  for (const m of Object.values(state.messages)
    .filter((m) => m.state === "published")
    .sort((a, b) => messageTime(a) - messageTime(b))) {
    const anchor = m.reply_to_comment_ids.find((id) => visible.has(id));
    if (anchor) replies.set(anchor, [...(replies.get(anchor) ?? []), m]);
    else standalone.push({ kind: "message", at: messageTime(m), message: m });
  }
  const items: ChatItem[] = comments.map((c) => ({
    kind: "comment",
    at: c.received_at,
    comment: c,
    replies: replies.get(c.comment_id) ?? [],
  }));
  return [...items, ...standalone].sort((a, b) => a.at - b.at);
}

/** Correction notices stay pinned in viewer chat for 60 s (§8.13). */
export function hiddenComments(state: ClientState): Comment[] {
  return Object.values(state.comments)
    .filter((c) => c.visibility === "hidden")
    .sort((a, b) => b.received_at - a.received_at);
}

/** Last `n` final transcripts, newest first (operator Live transcript). */
export function recentTranscripts(state: ClientState, n = 20): Transcript[] {
  return Object.values(state.transcripts)
    .filter((t) => t.is_final)
    .sort((a, b) => b.received_at - a.received_at)
    .slice(0, n);
}

/** The active cue strip: active, or done less than 2 s ago (check then fade, §12.3.2). */
export function cueStrip(state: ClientState, clientNow: number) {
  const cue = state.session?.cue;
  if (!cue) return null;
  if (cue.status === "active") return cue;
  if (cue.status === "done" && cue.done_at && clientNow - cue.done_at < 2000) return cue;
  return null;
}

/** The active AI PD card: active, or done less than 1.5 s ago (short done fade). */
export function activePdCard(state: ClientState, clientNow: number): PdCard | null {
  const card = state.session?.pd_card;
  if (!card) return null;
  if (card.status === "active") return card;
  if (card.status === "done" && card.done_at && clientNow - card.done_at < 1500) return card;
  return null;
}
