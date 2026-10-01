import { describe, expect, it } from "vitest";

import { AMPOULE, CREAM, T0, alert, answer, catalog, comment, group, message, segment, snapshot } from "../test/fixtures";
import {
  activeHighAlert,
  activeMediumAlerts,
  activePromos,
  chatItems,
  cueStrip,
  factNotesForHost,
  formatClock,
  formatMmSs,
  groupStatusLabel,
  hostSlots,
  nextProduct,
  onAirSegment,
  priceView,
  prompterView,
  questionDesk,
  recentlyCorrected,
  relativeTime,
  runOfShow,
} from "./selectors";
import { reduceSnapshot } from "./state";

describe("products and segments", () => {
  it("on air, next and end of run sheet", () => {
    const s = reduceSnapshot(snapshot(), "host");
    expect(onAirSegment(s)?.product_id).toBe(CREAM);
    expect(nextProduct(s, catalog)?.product_id).toBe(AMPOULE);
    const later = reduceSnapshot(
      snapshot({ segments: [segment({ ended_at: T0 + 60_000 }), segment({ segment_id: "seg_2", product_id: AMPOULE, started_at: T0 + 60_000 })] }),
      "host",
    );
    expect(onAirSegment(later)?.product_id).toBe(AMPOULE);
    expect(nextProduct(later, catalog)).toBeNull(); // "End of run sheet"
    const ready = reduceSnapshot(snapshot({ segments: [] }), "host");
    expect(nextProduct(ready, catalog)?.product_id).toBe(CREAM);
  });

  it("run of show statuses and required points", () => {
    const s = reduceSnapshot(snapshot({ segments: [segment({ covered_point_ids: ["cr-p2"] })] }), "operator");
    const rows = runOfShow(s, catalog, T0 + 120_000);
    expect(rows.map((r) => r.status)).toEqual(["on_air", "next"]);
    expect(rows[0].elapsedMs).toBe(120_000);
    expect(rows[0].coveredRequired).toBe(1);
  });
});

describe("prompter", () => {
  it("marks covered points; there is no next point (D-091)", () => {
    const s = reduceSnapshot(snapshot({ segments: [segment({ covered_point_ids: ["cr-p1"] })] }), "host");
    const v = prompterView(s, catalog);
    expect(v.points.map((p) => [p.point_id, p.covered, p.required])).toEqual([
      ["cr-p1", true, false],
      ["cr-p2", false, true],
      ["cr-p3", false, true],
    ]);
    expect(v.points[0]).not.toHaveProperty("focus");
    expect([v.requiredCovered, v.requiredTotal]).toEqual([0, 2]);
  });
});

describe("prices", () => {
  it("switches to promo prices during a price promo", () => {
    const live = reduceSnapshot(snapshot(), "viewer");
    const product = catalog.products[0];
    expect(priceView(live, catalog, product)).toEqual({ label: "LIVE PRICE", current: "S$36.00", struck: "S$48.00", set: "S$62.00" });
    const sale = reduceSnapshot(snapshot({ session: { ...snapshot().session, active_promo_id: "promo_time_sale_10", active_promos: [{ promo_id: "promo_time_sale_10", started_at: T0, ends_at: T0 + 600_000 }] } }), "viewer");
    expect(priceView(sale, catalog, product)).toEqual({ label: "TIME SALE", current: "S$32.40", struck: "S$36.00", set: "S$55.80" });
    expect(activePromos(sale, catalog, T0 + 60_000)[0].remainingMs).toBe(540_000);
  });
});

describe("alerts", () => {
  it("host shows the newest HIGH alert with '1 of N'", () => {
    const s = reduceSnapshot(
      snapshot({
        alerts: [
          alert({ alert_id: "al_1", shown_at: T0 + 1000 }),
          alert({ alert_id: "al_2", shown_at: T0 + 2000 }),
          alert({ alert_id: "al_3", severity: "MEDIUM", rule_id: "BRAND-SUPERLATIVE" }),
          alert({ alert_id: "al_4", status: "corrected" }),
          alert({ alert_id: "al_5", status: "provisional" }),
        ],
      }),
      "host",
    );
    const high = activeHighAlert(s);
    expect(high?.alert.alert_id).toBe("al_2");
    expect([high?.position, high?.total]).toEqual([1, 2]);
    expect(activeMediumAlerts(s).map((a) => a.alert_id)).toEqual(["al_3"]);
  });

  it("fact notes leave the host after host_hidden_at; corrected toast lasts 1.5 s", () => {
    const s = reduceSnapshot(
      snapshot({
        alerts: [
          alert({ alert_id: "fx_1", kind: "fact", field: "price", severity: null, rule_id: null }),
          alert({ alert_id: "fx_2", kind: "fact", field: "volume", severity: null, rule_id: null, host_hidden_at: T0 + 50_000 }),
          alert({ alert_id: "al_c", status: "corrected", resolved_at: T0 + 10_000 }),
        ],
      }),
      "host",
    );
    expect(factNotesForHost(s).map((a) => a.alert_id)).toEqual(["fx_1"]);
    expect(recentlyCorrected(s, T0 + 11_000)?.alert_id).toBe("al_c");
    expect(recentlyCorrected(s, T0 + 11_600)).toBeNull();
  });
});

describe("host slots", () => {
  it("keeps slot order and resolves groups, verified answers, tags and pending posts", () => {
    const s = reduceSnapshot(
      snapshot({
        groups: [
          group({ group_id: "g_a", answer_id: "ans_a", score: 1 }),
          group({ group_id: "g_b", status: "auto_answered", route: "AUTO", score: 9 }),
          group({ group_id: "g_c", answer_id: "ans_c", score: 5 }),
        ],
        answers: { ans_a: answer({ answer_id: "ans_a" }), ans_c: answer({ answer_id: "ans_c", verified: false }) },
        host_slots: [
          { group_id: "g_c", pinned: true, on_host_since: T0 },
          { group_id: "g_a", pinned: false, on_host_since: T0 },
          { group_id: "g_b", pinned: false, on_host_since: T0 },
          { group_id: "missing", pinned: false, on_host_since: T0 },
        ],
        messages: [message({ message_id: "m_p", group_id: "g_a", state: "pending", kind: "host_answer" })],
      }),
      "host",
    );
    const slots = hostSlots(s);
    expect(slots.map((x) => [x.index, x.group.group_id, x.tag])).toEqual([
      [1, "g_c", "From your PD"],
      [2, "g_a", "For you"],
      [3, "g_b", "AI answered"],
    ]);
    expect(slots[0].answer).toBeNull(); // unverified drafts are never suggested to the host
    expect(slots[1].answer?.answer_id).toBe("ans_a");
    expect(slots[1].pending?.message_id).toBe("m_p");
  });
});

describe("question desk", () => {
  it("sorts by status bucket then score, and filters by tab", () => {
    const s = reduceSnapshot(
      snapshot({
        groups: [
          group({ group_id: "answered", status: "answered", score: 99 }),
          group({ group_id: "ready_low", status: "ready", score: 1 }),
          group({ group_id: "ready_high", status: "ready", score: 8 }),
          group({ group_id: "review", status: "needs_review", route: "OPERATOR", score: 0 }),
          group({ group_id: "onhost", status: "ready", host_slot: "on_host", score: 2 }),
          group({ group_id: "comp", status: "composing", score: 50 }),
          group({ group_id: "ai", status: "auto_answered", score: 7 }),
          group({ group_id: "closed", status: "closed", score: 100 }),
        ],
      }),
      "operator",
    );
    expect(questionDesk(s).map((g) => g.group_id)).toEqual(["review", "onhost", "ready_high", "ready_low", "comp", "ai", "answered", "closed"]);
    expect(questionDesk(s, "answered").map((g) => g.group_id)).toEqual(["ai", "answered"]);
    expect(questionDesk(s, "on_host").map((g) => g.group_id)).toEqual(["onhost"]);
  });

  it("status labels", () => {
    expect(groupStatusLabel(group({ status: "needs_review", route_reason: "unresolved_product" }))).toBe("Assign a product");
    expect(groupStatusLabel(group({ host_verbal_answer_transcript_id: "tr_1" }))).toBe("Host answered on air · not posted");
    expect(groupStatusLabel(group({ status: "composing" }))).toBe("Composing…");
    expect(groupStatusLabel(group({ status: "auto_answered" }))).toBe("AI answered");
    expect(groupStatusLabel(group({ host_slot: "on_host" }))).toBe("On host");
  });
});

describe("chat", () => {
  it("orders by time and attaches replies to the first visible comment they answer", () => {
    const s = reduceSnapshot(
      snapshot({
        comments: [
          comment({ comment_id: "c1", author_name: "Raj", received_at: T0 + 1000 }),
          comment({ comment_id: "c2", author_name: "Mei", received_at: T0 + 2000 }),
          comment({ comment_id: "c3", kind: "reaction", received_at: T0 + 2500, group_id: null }),
        ],
        messages: [
          message({ message_id: "m1", reply_to_comment_ids: ["c1", "c2"], published_at: T0 + 4000 }),
          message({ message_id: "m_notice", kind: "correction_notice", reply_to_comment_ids: [], published_at: T0 + 3000 }),
          message({ message_id: "m_pending", state: "pending", published_at: null }),
        ],
      }),
      "viewer",
    );
    const items = chatItems(s);
    expect(items.map((i) => (i.kind === "comment" ? i.comment.comment_id : i.message.message_id))).toEqual(["c1", "c2", "c3", "m_notice"]);
    const first = items[0];
    expect(first.kind === "comment" && first.replies.map((m) => m.message_id)).toEqual(["m1"]);
  });
});

describe("time helpers", () => {
  it("formats clocks and relative times", () => {
    expect(formatClock(23 * 60_000 + 41_000 + 3_600_000)).toBe("01:23:41");
    expect(formatMmSs(5_000)).toBe("00:05");
    expect(formatMmSs(4_001)).toBe("00:05");
    expect(relativeTime(T0, T0 + 2_000)).toBe("now");
    expect(relativeTime(T0, T0 + 12_000)).toBe("12s");
    expect(relativeTime(T0, T0 + 180_000)).toBe("3m");
  });

  it("cue strip shows done cues for 2 s", () => {
    const s = reduceSnapshot(snapshot({ session: { ...snapshot().session, cue: { cue_id: "c", text: "x", preset_id: null, created_at: T0, status: "done", done_by_transcript_id: "tr", done_at: T0 + 1000 } } }), "host");
    expect(cueStrip(s, T0 + 2500)).not.toBeNull();
    expect(cueStrip(s, T0 + 3100)).toBeNull();
  });
});

describe("desk status: one tab per group, chip and tab agree", () => {
  it("maps every status to exactly one tab and counts add up to All", async () => {
    const { deskStatus, deskTabCounts } = await import("./selectors");
    const gs = [
      group({ group_id: "a", status: "needs_review" }),
      group({ group_id: "b", status: "ready", host_slot: "on_host" }),
      group({ group_id: "c", status: "ready" }),
      group({ group_id: "d", status: "composing" }),
      group({ group_id: "e", status: "auto_answered" }),
      group({ group_id: "f", status: "answered", host_slot: "on_host" }),
      group({ group_id: "g", status: "rejected" }),
      group({ group_id: "h", status: "ready", host_verbal_answer_transcript_id: "tr_1" }),
    ];
    expect(gs.map((g) => [deskStatus(g).label, deskStatus(g).tab])).toEqual([
      ["Needs review", "needs_review"],
      ["On host", "on_host"],
      ["Ready", "ready"],
      ["Composing…", "composing"],
      ["AI answered", "answered"],
      ["Answered", "answered"],
      ["Rejected", "closed"],
      ["Host answered on air · not posted", "needs_review"],
    ]);
    const c = deskTabCounts(gs);
    expect(c.all).toBe(8);
    expect(c.needs_review + c.on_host + c.ready + c.composing + c.answered + c.closed).toBe(c.all);
  });
});