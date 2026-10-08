// Pure selectors over ClientState (+ catalog, + server now). Screens read these, never raw events.
import type { ClientState, LineCheck } from "./state";
import type {
  Alert,
  Answer,
  Catalog,
  Comment,
  HostSlot,
  Message,
  PdCard,
  Product,
  Promo,
  QuestionGroup,
  Segment,
  Transcript,
} from "./types";

// ---- time ------------------------------------------------------------------------------------------

export function serverNow(state: ClientState, clientNow: number = Date.now()): number {
  return clientNow + state.serverOffsetMs;
}

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
}

export function priceView(state: ClientState, catalog: Catalog | null, product: Product | null): PriceView | null {
  if (!product || !catalog) return null;
  const promo = activePricePromo(state, catalog);
  const set = catalog.set_offers.find((s) => s.product_ids.includes(product.product_id));
  const promoPrice = promo?.promo_prices_display[product.product_id];
  if (promo && promoPrice) {
    return {
      label: "TIME SALE",
      current: promoPrice,
      struck: product.live_price_display,
      set: (set && promo.promo_prices_display[set.set_id]) || set?.live_price_display || "",
      symbol: catalog.currency_symbol,
    };
  }
  return { label: "LIVE PRICE", current: product.live_price_display, struck: product.list_price_display,
    set: set?.live_price_display ?? "", symbol: catalog.currency_symbol };
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
  requiredTotal: number;
  requiredCovered: number;
}

export function prompterView(state: ClientState, catalog: Catalog | null): PrompterViewModel {
  const seg = onAirSegment(state);
  const product = productById(catalog, seg?.product_id ?? state.prompter?.product_id);
  if (!product) return { product: null, points: [], requiredTotal: 0, requiredCovered: 0 };
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
  return {
    product,
    points,
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

/** D-161, D-177: a red alert created less than RED_BLOCK_MS ago (server time): it is highlighted and blocks cards.
 *  The same claim said again is a new alert, so it highlights and blocks again. */
export function redBlocking(state: ClientState, now: number): boolean {
  return activeComplianceAlerts(state).some((a) => a.severity === "HIGH" && now - a.created_at < RED_BLOCK_MS);
}

export function activeMediumAlerts(state: ClientState): Alert[] {
  return activeComplianceAlerts(state).filter((a) => a.severity === "MEDIUM");
}

export function provisionalAlerts(state: ClientState): Alert[] {
  return Object.values(state.alerts).filter((a) => a.kind === "compliance" && a.status === "provisional");
}

export function factNotesForHost(state: ClientState): Alert[] {
  return Object.values(state.alerts)
    .filter((a) => a.kind === "fact" && a.status === "active" && a.host_hidden_at === null)
    .sort((a, b) => alertTime(b) - alertTime(a));
}

/** D-105: a test number said without "in our in-house test". */
export const TEST_QUALIFIER_RULE = "TEST-QUALIFIER";

/** Host banners. D-105: a test-qualifier banner and a fact note on the same sentence show as one
 *  card (the note joins the banner when the fact checker finishes); alerts and logs keep both. D-342 (review H20):
 *  a sentence with an active HIGH alert shows only that alert: its MEDIUM banners and fact notes wait in the log. */
export function hostBanners(state: ClientState): { mediums: { alert: Alert; fact: Alert | null }[]; facts: Alert[] } {
  const high = new Set(activeComplianceAlerts(state).filter((a) => a.severity === "HIGH").map((a) => a.transcript_id));
  const facts = factNotesForHost(state).filter((f) => !high.has(f.transcript_id));
  const merged = new Set<string>();
  const mediums = activeMediumAlerts(state).filter((a) => !high.has(a.transcript_id)).map((alert) => {
    const fact =
      alert.rule_id === TEST_QUALIFIER_RULE
        ? (facts.find((f) => f.transcript_id === alert.transcript_id && !merged.has(f.alert_id)) ?? null)
        : null;
    if (fact) merged.add(fact.alert_id);
    return { alert, fact };
  });
  return { mediums, facts: facts.filter((f) => !merged.has(f.alert_id)) };
}

export function activeFactAlerts(state: ClientState): Alert[] {
  return Object.values(state.alerts)
    .filter((a) => a.kind === "fact" && a.status === "active")
    .sort((a, b) => alertTime(b) - alertTime(a));
}

export function alertLog(state: ClientState): Alert[] {
  return Object.values(state.alerts)
    .filter((a) => a.status !== "provisional" && a.status !== "cleared")
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
  waiting: "On your card" | "Drafting…" | "Which product?" | "Read out" | "Ready" | "No answer yet";
}

export function hostSlots(state: ClientState): HostSlotView[] {
  const pending = pendingMessages(state);
  const card = state.session?.pd_card;
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
      waiting: waitingState(group, verifiedAnswer(state, group), card),
    }));
}

function waitingState(group: QuestionGroup, answer: Answer | null, card: PdCard | null | undefined): HostSlotView["waiting"] {
  if (card?.status === "active" && card.ref_id === group.group_id) return "On your card";
  if (group.status === "composing") return "Drafting…";
  if (group.status === "needs_review" && group.route_reason === "unresolved_product") return "Which product?";
  if (group.status === "auto_answered") return "Read out";
  return answer ? "Ready" : "No answer yet";
}

/** D-178: questions the product info does not answer, shop policy and the previous product's questions wait for the
 *  operator. In a solo show nobody watches that list, so the host sees only how many there are. */
export function unansweredCount(state: ClientState): number {
  if (state.session?.show_mode !== "solo") return 0;
  return Object.values(state.groups).filter((g) => g.route === "OPERATOR"
    && ["new", "composing", "ready", "needs_review"].includes(g.status) && !g.host_verbal_answer_transcript_id).length;
}

export type DeskTab = "all" | "needs_review" | "on_host" | "ready" | "composing" | "answered" | "closed";
export type DeskStatusTab = Exclude<DeskTab, "all">;

export interface DeskStatus {
  label: string; // the row chip
  tab: DeskStatusTab; // the one tab the group is counted and listed under
}

const DONE_STATUSES = ["answered", "rejected", "closed"];

/** The single source of a group's desk status: its row chip and its tab always agree, every group
 * is in exactly one tab, and the tab counts add up to All. */
export function deskStatus(g: QuestionGroup): DeskStatus {
  const done = DONE_STATUSES.includes(g.status);
  if (g.host_verbal_answer_transcript_id && !done) return { label: "Host answered on air · not posted", tab: "needs_review" };
  if (g.status === "needs_review" && g.route_reason === "unresolved_product") return { label: "Assign a product", tab: "needs_review" };
  if (g.host_slot === "on_host" && !done) return { label: "On host", tab: "on_host" };
  switch (g.status) {
    case "needs_review":
      return { label: "Needs review", tab: "needs_review" };
    case "ready":
      return { label: "Ready", tab: "ready" };
    case "new":
    case "composing":
      return { label: "Composing…", tab: "composing" };
    case "auto_answered":
      return { label: "AI answered", tab: "answered" };
    case "answered":
      return { label: "Answered", tab: "answered" };
    case "rejected":
      return { label: "Rejected", tab: "closed" };
    default:
      return { label: "Closed", tab: "closed" };
  }
}

export function deskTabOf(g: QuestionGroup): DeskStatusTab {
  return deskStatus(g).tab;
}

/** Counts per tab; `all` equals the sum of the other tabs. */
export function deskTabCounts(groups: QuestionGroup[]): Record<DeskTab, number> {
  const counts: Record<DeskTab, number> = { all: groups.length, needs_review: 0, on_host: 0, ready: 0, composing: 0, answered: 0, closed: 0 };
  for (const g of groups) counts[deskTabOf(g)] += 1;
  return counts;
}

/** Status bucket (§12.4.7): Needs review, On host, Ready, Composing, AI answered, Answered, Rejected/Closed. */
export function deskBucket(g: QuestionGroup): number {
  const s = deskStatus(g);
  switch (s.tab) {
    case "needs_review":
      return 0;
    case "on_host":
      return 1;
    case "ready":
      return 2;
    case "composing":
      return 3;
    case "answered":
      return s.label === "AI answered" ? 4 : 5;
    default:
      return 6;
  }
}

export function groupStatusLabel(g: QuestionGroup): string {
  return deskStatus(g).label;
}

export function questionDesk(state: ClientState, tab: DeskTab = "all"): QuestionGroup[] {
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
export function pinnedCorrectionNotices(state: ClientState, now: number, windowMs = 60_000): Message[] {
  return Object.values(state.messages).filter(
    (m) => m.kind === "correction_notice" && m.state === "published" && now - messageTime(m) < windowMs,
  );
}

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
export const LINE_CHECK_MS = 15_000;

/** D-288: the newest line to check, for 15 s after it arrived */
export function activeLineCheck(state: ClientState, clientNow: number): LineCheck | null {
  const c = state.lineChecks[state.lineChecks.length - 1];
  return c && clientNow - c.at < LINE_CHECK_MS ? c : null;
}

export function activePdCard(state: ClientState, clientNow: number): PdCard | null {
  const card = state.session?.pd_card;
  if (!card) return null;
  if (card.status === "active") return card;
  if (card.status === "done" && card.done_at && clientNow - card.done_at < 1500) return card;
  return null;
}
