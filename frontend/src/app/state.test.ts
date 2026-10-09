import { describe, expect, it } from "vitest";

import { AMPOULE, CREAM, T0, alert, answer, comment, group, message, pdCard, segment, snapshot } from "../test/fixtures";
import { activePdCard } from "./selectors";
import { EVENT_TYPES } from "./sse";
import { reduceEvent, reduceSnapshot, type ClientState } from "./state";
import type { SessionEvent } from "./types";

const ev = (seq: number, type: string, payload: unknown): SessionEvent => ({ seq, type, payload });

function apply(state: ClientState, events: SessionEvent[], now = T0 + 20_000): ClientState {
  return events.reduce((s, e) => reduceEvent(s, e, now), state);
}

describe("reduceSnapshot", () => {
  it("builds maps by id, the server offset and missing P2 keys as empty", () => {
    const s = reduceSnapshot(
      snapshot({ groups: [group()], comments: [comment()], answers: { ans_000001: answer() }, prompter: undefined }),
      "operator",
      T0 + 9_000,
    );
    expect(s.loaded).toBe(true);
    expect(s.lastSeq).toBe(10);
    expect(s.serverOffsetMs).toBe(1000);
    expect(Object.keys(s.groups)).toEqual(["grp_000001"]);
    expect(s.alerts).toEqual({});
    expect(s.prompter).toBeNull();
  });

  it("drops hidden comments for host and viewer", () => {
    const snap = snapshot({ comments: [comment(), comment({ comment_id: "cm_2", visibility: "hidden" })] });
    expect(Object.keys(reduceSnapshot(snap, "viewer").comments)).toEqual(["cm_000001"]);
    expect(Object.keys(reduceSnapshot(snap, "operator").comments)).toHaveLength(2);
  });
});

describe("reduceEvent idempotency", () => {
  it("skips events at or below lastSeq and is an upsert above it", () => {
    const base = reduceSnapshot(snapshot({ groups: [group({ score: 5 })] }), "operator");
    const stale = reduceEvent(base, ev(10, "group.updated", group({ score: 99 })));
    expect(stale).toBe(base);
    const once = reduceEvent(base, ev(11, "group.updated", group({ score: 7 })));
    expect(once.groups.grp_000001.score).toBe(7);
    expect(once.lastSeq).toBe(11);
    expect(reduceEvent(once, ev(11, "group.updated", group({ score: 99 })))).toBe(once);
  });

  it("applies the same object twice without duplicates", () => {
    const base = reduceSnapshot(snapshot(), "operator");
    const s = apply(base, [ev(11, "comment.created", comment()), ev(12, "comment.created", comment())]);
    expect(Object.keys(s.comments)).toEqual(["cm_000001"]);
  });
});

describe("every event type", () => {
  it("has a reducer branch for each type the SSE client listens to", () => {
    const base = reduceSnapshot(snapshot(), "operator");
    const samples: Record<string, unknown> = {
      "session.started": { ...base.session, status: "live" },
      "session.ended": { ...base.session, status: "ended" },
      "segment.started": segment({ segment_id: "seg_2", product_id: AMPOULE, started_at: T0 + 60_000, start_reason: "auto_speech" }),
      "segment.overtime": { segment_id: "seg_000001", product_id: CREAM, overtime_sec: 1 },
      "segment.switch_decided": { transcript_id: "tr_1", switch: true, target_product_id: AMPOULE, confidence: "high" },
      "segment.undone": { segment_id: "seg_x" },
      "segment.missing_points": { segment_id: "seg_000001", product_id: CREAM, missing_point_ids: ["cr-p4"] },
      "prompter.updated": { product_id: CREAM, segment_id: "seg_000001", covered_point_ids: ["cr-p1"], required_total: 2, required_covered: 0 },
      "transcript.interim": { transcript_id: "tr_i", text: "hel", is_final: false, speech_start_at: null, speech_end_at: T0, received_at: T0, source: "mic", segment_id: "seg_000001" },
      "transcript.final": { transcript_id: "tr_1", text: "hello", is_final: true, speech_start_at: null, speech_end_at: T0, received_at: T0, source: "injected", segment_id: "seg_000001" },
      "alert.created": alert(),
      "alert.updated": alert(),
      "alert.escalated": alert({ escalated_at: T0 + 10_000 }),
      "cue.updated": { cue_id: "cue_1", text: "Mention the patch test results.", preset_id: null, created_at: T0, status: "active", done_by_transcript_id: null },
      "pd.card": pdCard(),
      "comment.created": comment(),
      "comment.hidden": comment({ comment_id: "cm_h", visibility: "hidden" }),
      "comment.unhidden": comment({ comment_id: "cm_h" }),
      "comment.analyzed": { comment: comment(), analysis: { analysis_id: "an_1", comment_id: "cm_000001", output: {}, product_id: CREAM, product_basis: "context", context_product_id: CREAM, route: "HOST", route_reason: "intent", source: "llm", latency_ms: 900 } },
      "comment.status": comment({ reply_status: "host" }),
      "group.updated": group(),
      "hostqueue.updated": { slots: [{ group_id: "grp_000001", pinned: false, on_host_since: T0 }] },
      "message.pending": message({ message_id: "msg_p", state: "pending", kind: "host_answer" }),
      "message.published": message(),
      "message.updated": message({ reply_to_author_names: ["Raj", "Mei"] }),
      "message.cancelled": message({ message_id: "msg_p", state: "cancelled", kind: "host_answer" }),
      "promo.started": { promo_id: "promo_time_sale_10", started_at: T0, ends_at: T0 + 600_000, changes_prices: true },
      "promo.ended": { promo_id: "promo_time_sale_10", ended_at: T0 + 1000, reason: "operator" },
      "notice.updated": { pinned_notice: "Free shipping today" },
      "metrics.updated": { header: { alert_in_s: 2.4, judge_p50_s: 1.4, instant_answers: 3, answers_total: 4 } },
      "operator.action": { actor: "operator", action: "push", group_id: "grp_000001" },
      "agent.call": { call_id: "call_1", agent: "comment_triage", model: "m", prompt_version: "v", started_at: T0, latency_ms: 900, status: "ok", input_hash: "h", input_preview: "p", output: {}, error: null },
      "judge.failed": { transcript_id: "tr_1", cause: "timeout" },
      "judge.health": { degraded: ["compliance_judge"], at: 1 },
      "segment.extended": { segment: segment(), added_sec: 120 },
      "summary.ready": {},
      "feed.updated": { pool_running: true, armed: [], fired: [], bursts: [] },
      "line.check": { transcript_id: "tr_1", heard: "fifteen", source_value: "fifty" },
      "checks.recovered": { transcript_id: "tr_2", at: 1 },
      "hold.started": { transcript_id: "tr_q", max_ms: 2500 },
      "hold.ended": { transcript_id: "tr_q" },
    };
    expect(Object.keys(samples).sort()).toEqual([...EVENT_TYPES].sort());
    let s = base;
    let seq = 11;
    for (const type of EVENT_TYPES) {
      const next = reduceEvent(s, ev(seq++, type, samples[type]));
      expect(next.lastSeq, type).toBe(seq - 1);
      s = next;
    }
    expect(s.session?.status).toBe("ended");
    expect(s.summaryReady).toBe(true);
    expect(s.metrics.header?.instant_answers).toBe(3);
    expect(s.agentCalls[0].call_id).toBe("call_1");
    expect(s.judgeFailures).toHaveLength(1);
    expect(s.session?.pinned_notice).toBe("Free shipping today");
    expect(s.messages.msg_p.state).toBe("cancelled");
    expect(s.messages.msg_000001.reply_to_author_names).toEqual(["Raj", "Mei"]);
    expect(s.comments.cm_h.visibility).toBe("visible");
    expect(s.comments.cm_000001.reply_status).toBe("host");
    expect(s.analyses.cm_000001.route).toBe("HOST");
    expect(s.transcripts.tr_1.text).toBe("hello");
    expect(s.interim).toBeNull();
  });
});

describe("event semantics", () => {
  const base = () => reduceSnapshot(snapshot(), "viewer");

  it("segment.started closes the open segment, moves current_segment_id and records the commit", () => {
    const s = reduceEvent(base(), ev(11, "segment.started", segment({ segment_id: "seg_2", product_id: AMPOULE, started_at: T0 + 60_000, start_reason: "auto_speech" })));
    expect(s.segments.seg_000001.ended_at).toBe(T0 + 60_000);
    expect(s.session?.current_segment_id).toBe("seg_2");
    expect(s.session?.switch.last_commit).toEqual({ closed_segment_id: "seg_000001", opened_segment_id: "seg_2", at: T0 + 60_000 });
  });

  it("undo removes the new segment and reopens the previous one", () => {
    let s = reduceEvent(base(), ev(11, "segment.started", segment({ segment_id: "seg_2", product_id: AMPOULE, started_at: T0 + 60_000, start_reason: "operator" })));
    s = reduceEvent(s, ev(12, "segment.undone", { segment_id: "seg_2" }));
    s = reduceEvent(s, ev(13, "segment.started", segment()));
    expect(Object.keys(s.segments)).toEqual(["seg_000001"]);
    expect(s.segments.seg_000001.ended_at).toBeNull();
    expect(s.session?.switch.last_commit).toBeNull();
  });

  it("hidden comments are removed for the viewer (redacted payload)", () => {
    let s = reduceEvent(base(), ev(11, "comment.created", comment({ comment_id: "cm_x" })));
    expect(s.comments.cm_x).toBeDefined();
    s = reduceEvent(s, ev(12, "comment.hidden", { comment_id: "cm_x", visibility: "hidden" }));
    expect(s.comments.cm_x).toBeUndefined();
    s = reduceEvent(s, ev(13, "comment.analyzed", { comment: { comment_id: "cm_y", visibility: "hidden" } }));
    expect(s.comments.cm_y).toBeUndefined();
  });

  it("the viewer's snapshot has no groups, answers or metrics; a status event updates the comment", () => {
    const { groups: _g, answers: _a, host_slots: _h, metrics: _m, ...publicOnly } = snapshot({ comments: [comment({ reply_status: "checking" })] });
    let s = reduceSnapshot(publicOnly, "viewer");
    expect([s.groups, s.answers, s.hostSlots, s.metrics]).toEqual([{}, {}, [], {}]);
    expect(s.comments.cm_000001.reply_status).toBe("checking");
    s = reduceEvent(s, ev(11, "comment.status", { comment_id: "cm_000001", visibility: "visible", reply_status: "team" }));
    expect(s.comments.cm_000001).toMatchObject({ reply_status: "team", text: "Is it OK for oily skin?" });
    s = reduceEvent(s, ev(12, "message.updated", message({ translations: { ko: "S$36.00입니다." } })));
    expect(s.messages.msg_000001.translations).toEqual({ ko: "S$36.00입니다." });
  });

  it("group.updated with an unknown answer asks for a resync; a bundled answer is stored", () => {
    const s = reduceEvent(base(), ev(11, "group.updated", group({ answer_id: "ans_9" })));
    expect(s.needsResync).toBe(true);
    const t = reduceEvent(base(), ev(11, "group.updated", { ...group({ answer_id: "ans_9" }), answer: answer({ answer_id: "ans_9" }) }));
    expect(t.needsResync).toBe(false);
    expect(t.answers.ans_9.text).toContain("gel-cream");
  });

  it("promos set and clear the active price promo", () => {
    let s = reduceEvent(base(), ev(11, "promo.started", { promo_id: "promo_time_sale_10", started_at: T0, ends_at: T0 + 600_000, changes_prices: true }));
    expect(s.session?.active_promo_id).toBe("promo_time_sale_10");
    expect(s.session?.active_promos).toHaveLength(1);
    s = reduceEvent(s, ev(12, "promo.started", { promo_id: "promo_gift_pouch", started_at: T0, ends_at: T0 + 900_000, changes_prices: false }));
    expect(s.session?.active_promo_id).toBe("promo_time_sale_10");
    s = reduceEvent(s, ev(13, "promo.ended", { promo_id: "promo_time_sale_10", ended_at: T0 + 1, reason: "timer" }));
    expect(s.session?.active_promo_id).toBeNull();
    expect(s.session?.active_promos.map((p) => p.promo_id)).toEqual(["promo_gift_pouch"]);
  });

  it("a done cue keeps its first done time; an older cue never replaces the current one", () => {
    const cue = { cue_id: "cue_2", text: "Wrap up", preset_id: null, created_at: T0 + 100, status: "active", done_by_transcript_id: null };
    let s = reduceEvent(base(), ev(11, "cue.updated", cue), T0);
    s = reduceEvent(s, ev(12, "cue.updated", { ...cue, status: "done" }), T0 + 50);
    s = reduceEvent(s, ev(13, "cue.updated", { ...cue, status: "done" }), T0 + 900);
    expect(s.session?.cue?.done_at).toBe(T0 + 50);
    s = reduceEvent(s, ev(14, "cue.updated", { ...cue, cue_id: "cue_1", created_at: T0, status: "cleared" }));
    expect(s.session?.cue?.cue_id).toBe("cue_2");
  });

  it("a new pd.card replaces older, an older update is ignored, done/dismissed ends it", () => {
    const card = pdCard({ card_id: "card_2", created_at: T0 + 100, status: "active" });
    let s = reduceEvent(base(), ev(11, "pd.card", card), T0);
    expect(s.session?.pd_card?.card_id).toBe("card_2");
    expect(activePdCard(s, T0 + 100)?.card_id).toBe("card_2");

    // An update for an older card never replaces the current active one
    const older = pdCard({ card_id: "card_1", created_at: T0, status: "active" });
    s = reduceEvent(s, ev(12, "pd.card", older), T0 + 120);
    expect(s.session?.pd_card?.card_id).toBe("card_2");

    // Done sets done_at and keeps first done time
    s = reduceEvent(s, ev(13, "pd.card", { ...card, status: "done" }), T0 + 150);
    expect(s.session?.pd_card?.status).toBe("done");
    expect(s.session?.pd_card?.done_at).toBe(T0 + 150);
    s = reduceEvent(s, ev(14, "pd.card", { ...card, status: "done" }), T0 + 900);
    expect(s.session?.pd_card?.done_at).toBe(T0 + 150);
    expect(activePdCard(s, T0 + 200)?.status).toBe("done");
    expect(activePdCard(s, T0 + 2000)).toBeNull();

    // Dismissed ends the card
    s = reduceEvent(s, ev(15, "pd.card", { ...card, status: "dismissed" }), T0 + 2100);
    expect(s.session?.pd_card?.status).toBe("dismissed");
    expect(activePdCard(s, T0 + 2100)).toBeNull();

    // Null clears the card
    s = reduceEvent(s, ev(16, "pd.card", null), T0 + 2200);
    expect(s.session?.pd_card).toBeNull();
    expect(activePdCard(s, T0 + 2200)).toBeNull();
  });

  it("prompter.updated mirrors covered points into the segment", () => {
    const s = reduceEvent(base(), ev(11, "prompter.updated", { product_id: CREAM, segment_id: "seg_000001", covered_point_ids: ["cr-p1", "cr-p2"], required_total: 2, required_covered: 1 }));
    expect(s.segments.seg_000001.covered_point_ids).toEqual(["cr-p1", "cr-p2"]);
    expect(s.prompter?.required_covered).toBe(1);
  });
});

describe("segment.extended (D-138)", () => {
  it("takes the new plan and drops the overtime badge of that segment", () => {
    const seg = segment();
    let s = reduceSnapshot(snapshot({ segments: [seg] }), "operator");
    s = reduceEvent(s, ev(50, "segment.overtime", { segment_id: seg.segment_id, product_id: seg.product_id, overtime_sec: 5 }));
    s = reduceEvent(s, ev(51, "segment.extended", { segment: { ...seg, planned_duration_sec: seg.planned_duration_sec + 120 }, added_sec: 120 }));
    expect(s.segments[seg.segment_id].planned_duration_sec).toBe(seg.planned_duration_sec + 120);
    expect(s.overtime[seg.segment_id]).toBeUndefined();
  });
});

