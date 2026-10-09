import { cleanup, fireEvent, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setLang, translate } from "../../app/i18n";
import { emptyState, reduceSnapshot } from "../../app/state";
import type { QuestionGroup, StateSnapshot } from "../../app/types";
import { alert, answer, catalog, comment, group, message, snapshot, T0 } from "../../test/fixtures";
import { Operator } from "../Operator";
import { useArrivalDot } from "./attention";
import { CommentStream } from "./CommentStream";
import { OperatorProvider } from "./context";
import { QuestionDesk } from "./QuestionDesk";
import { metricChips } from "./Header";
import {
  alertCardState,
  complianceTitle,
  correctedLine,
  groupActions,
  isStale,
  setLabel,
  sourceLabel,
  stackAlerts,
  systemCards,
  transcriptChips,
} from "./model";

// ---- pure rules ------------------------------------------------------------------------------------------

const keys = (g: QuestionGroup, a = answer(), pending = null) =>
  groupActions(g, a, pending).map((x) => `${x.key}${x.enabled ? "" : "(off)"}`);

describe("groupActions: enabled by status (§12.10)", () => {
  it("ready group with a verified draft", () => {
    expect(keys(group({ status: "ready" }))).toEqual(["push", "approve", "edit", "write", "assign", "reject"]);
  });
  it("on host shows Recall instead of Push to host", () => {
    expect(keys(group({ status: "ready", host_slot: "on_host" }))[0]).toBe("recall");
  });
  it("unverified draft cannot be approved", () => {
    const a = answer({ verified: false, verify_errors: ["number 30 not in a cited quote"] });
    expect(keys(group({ status: "needs_review" }), a)).toContain("approve(off)");
  });
  it("no draft: no Edit reply, Write reply available", () => {
    const k = groupActions(group({ status: "needs_review", answer_id: null }), null).map((x) => x.key);
    expect(k).not.toContain("edit");
    expect(k).toContain("write");
  });
  it("host answered on air but not posted offers Post suggested answer", () => {
    const k = keys(group({ status: "ready", host_verbal_answer_transcript_id: "tr_9" }));
    expect(k).toContain("post_suggested");
  });
  it("AI-answered groups can be pushed or rejected, not re-answered", () => {
    expect(keys(group({ status: "auto_answered", route: "AUTO" }))).toEqual(["push", "reject"]);
  });
  it("answered, rejected and closed groups have no actions", () => {
    for (const status of ["answered", "rejected", "closed"] as const) {
      expect(groupActions(group({ status }), answer())).toEqual([]);
    }
  });
  it("a pending host answer blocks approve and reply", () => {
    const pending = message({ kind: "host_answer", state: "pending" });
    const k = groupActions(group({ status: "ready" }), answer(), pending).map((x) => `${x.key}${x.enabled ? "" : "(off)"}`);
    expect(k).toEqual(expect.arrayContaining(["approve(off)", "write(off)", "reject(off)"]));
  });
});

describe("alert cards", () => {
  it("compliance title and states", () => {
    const a = alert();
    expect(complianceTitle(a, T0 + 6000)).toBe("Host correction required");
    const esc = alert({ escalated_at: T0 + 10_000 });
    expect(alertCardState(esc)).toBe("escalated");
    expect(complianceTitle(esc, T0 + 5000 + 65_000)).toBe("Not corrected · 01:05");
    const done = alert({ status: "corrected", resolved_at: T0 + 8200, corrected_text: "Let me correct that." });
    expect(correctedLine(done)).toBe("Host fixed in 3.2 s · 'Let me correct that.'");
  });
  it("corrected alerts stay in the stack for 10 s", () => {
    const st = reduceSnapshot(
      snapshot({ alerts: [alert({ status: "corrected", resolved_at: T0 + 9000 }), alert({ alert_id: "fx_1", kind: "fact", field: "price" })] }),
      "operator",
      T0 + 10_000,
    );
    expect(stackAlerts(st, T0 + 12_000).map((a) => a.alert_id)).toEqual(["al_000001", "fx_1"]);
    expect(stackAlerts(st, T0 + 19_500).map((a) => a.alert_id)).toEqual(["fx_1"]);
  });
  it("source label from passage or promo", () => {
    const cat = { ...catalog, passages: { "DL-CR-01#key-facts#live-broadcast-price": { doc: "x.pdf", section: "Key facts", product_id: "cream_hydra_barrier", text: "Live broadcast price: S$36.00" } } };
    expect(sourceLabel(cat, "DL-CR-01#key-facts#live-broadcast-price")).toBe("Hydra Barrier Cream product sheet · Key facts");
    expect(sourceLabel(cat, null)).toBe("Active promotion");
  });
  it("system cards from missing points, judge failures and overtime", () => {
    let st = reduceSnapshot(snapshot(), "operator", T0 + 10_000);
    st = {
      ...st,
      missingPoints: [{ seq: 1, segment_id: "seg_000001", product_id: "cream_hydra_barrier", missing_point_ids: ["cr-p3"],
        missing_texts: ["Helps keep skin hydrated for up to 24 hours (in-house test)."] }],  // D-432: as the server sends
      unchecked: [{ seq: 2, transcript_id: "tr_1", agent: "compliance_judge", cause: "busy", at: T0 }],
      overtime: { seg_000001: { segment_id: "seg_000001", product_id: "cream_hydra_barrier", overtime_sec: 5 } },
    };
    const cards = systemCards(st, catalog, T0 + 905_000);
    expect(cards.map((c) => c.text)).toEqual([
      "Switched with missing required points: Helps keep skin hydrated for up to 24 hours (in-house test).",
      "AI check unavailable for the last sentence · Compliance check: AI busy (429)",
      "Overtime +0:05 on Hydra Barrier Cream",
    ]);
  });
  it("D-412: a failed line says its cause with the code; the last 5 minutes are counted by cause", () => {
    let st = reduceSnapshot(snapshot(), "operator", T0);
    const failures = [
      { seq: 1, transcript_id: "tr_old", agent: "compliance_judge", cause: "busy", at: T0 - 400_000 },
      { seq: 2, transcript_id: "tr_1", agent: "compliance_judge", cause: "busy", at: T0 - 60_000 },
      { seq: 3, transcript_id: "tr_2", agent: "compliance_judge", cause: "busy", at: T0 - 30_000 },
      { seq: 4, transcript_id: "tr_2", agent: "fact_checker", cause: "timeout", at: T0 - 1000 },
    ];
    st = { ...st, judgeFailures: failures.slice(1), unchecked: failures };  // the snapshot's two lists (D-420)
    const texts = systemCards(st, catalog, T0).map((c) => c.text);
    // D-420: one card per unchecked line, whatever its age, listing each failed judge with its cause
    expect(texts).toContain("AI check unavailable for the last sentence · Compliance check: AI busy (429)");
    expect(texts).toContain(
      "AI check unavailable for the last sentence · Compliance check: AI busy (429) · Fact check: AI timed out");
    expect(texts.filter((x) => x.startsWith("AI check unavailable"))).toHaveLength(3);  // tr_old, tr_1, tr_2
    expect(texts).toContain("Last 5 min: AI busy (429) 2 · AI timed out 1");  // tr_old is older than 5 minutes
    // D-422: a later failure on a line gets a new card key, so a dismissed card shows again
    const key = (u: typeof failures) => systemCards({ ...st, unchecked: u }, catalog, T0)
      .find((x) => x.text.startsWith("AI check unavailable"))?.key;
    expect(key(failures.slice(2, 3))).not.toBe(key(failures.slice(2, 4)));
  });
  it("stale questions turn amber after STALE_COMMENT_SEC", () => {
    expect(isStale(group({ status: "needs_review", first_at: T0 }), T0 + 300_000, 300)).toBe(true);
    expect(isStale(group({ status: "answered", first_at: T0 }), T0 + 900_000, 300)).toBe(false);
  });
  it("metric chips", () => {
    expect(metricChips({ header: { alert_in_s: 2.43, judge_p50_s: 1.8, instant_answers: 12, answers_total: 15 } })).toEqual({
      alert: "Alert in 2.4s",
      judge: "Judge p50 1.8s",
      instant: "Instant answers 12/15",
    });
    expect(metricChips({}).alert).toBe("Alert in –");
  });
  it("metric chips show – when nothing is measured, never 0.0s (item 7)", () => {
    expect(metricChips({})).toEqual({ alert: "Alert in –", judge: "Judge p50 –", instant: "Instant answers –" });
    expect(metricChips({ header: { alert_in_s: null, judge_p50_s: Number.NaN, instant_answers: 0, answers_total: 0 } })).toEqual({
      alert: "Alert in –",
      judge: "Judge p50 –",
      instant: "Instant answers –",
    });
    expect(metricChips({ header: { alert_in_s: 0.04, judge_p50_s: 1.37, instant_answers: 0, answers_total: 3 } })).toEqual({
      alert: "Alert in 0.0s",
      judge: "Judge p50 1.4s",
      instant: "Instant answers 0/3",
    });
  });
  it("transcript chips: rule, answered question, covered points, switch cue", () => {
    const st = {
      ...reduceSnapshot(
        snapshot({ alerts: [alert({ transcript_id: "tr_1" })], groups: [group()] }),
        "operator",
        T0,
      ),
      agentCalls: [
        {
          call_id: "c0", agent: "compliance_judge", model: "m", prompt_version: "v", started_at: T0, latency_ms: 600, status: "ok" as const,
          input_hash: "h", input_preview: "Yes it is.", error: null,
          output: { compliance: { violations: [] }, correction: { corrects_alert_ids: [] } },
        },
        {
          call_id: "c1", agent: "context_judge", model: "m", prompt_version: "v", started_at: T0, latency_ms: 900, status: "ok" as const,
          input_hash: "h", input_preview: "Yes it is.", error: null,
          output: { answer: { is_answer: true, matched_group_id: "grp_000001" }, prompter: { covered_point_ids: ["cr-p1"] } },
        },
      ],
    };
    const t = { transcript_id: "tr_1", text: "Yes it is.", is_final: true, speech_start_at: null, speech_end_at: T0, received_at: T0, source: "injected" as const, segment_id: "seg_000001" };
    expect(transcriptChips(st, catalog, t).map((c) => c.text)).toEqual([
      "ASEAN-3-SKIN-AGEING",
      "answered: Is it suitable for oily skin?",
      "cr-p1",
    ]);
  });
  it("D-440: a cited alert's chip names the document and section, not the citation slug", () => {
    const cited = alert({ transcript_id: "tr_1", rule_id: "asean-cosmetic-claims-guideline-appendix-iii-2007#2-d",
      citation: "asean_cosmetic_claims_guideline_appendix_iii_2007.pdf#2.d", cited_title: "ASEAN Appendix III 2.d" });
    const st = reduceSnapshot(snapshot({ alerts: [cited] }), "operator", T0);
    const t = { transcript_id: "tr_1", text: "x", is_final: true, speech_start_at: null, speech_end_at: T0, received_at: T0,
      source: "mic" as const, segment_id: "seg_000001" };
    expect(transcriptChips(st, catalog, t).map((c) => c.text)).toEqual(["ASEAN Appendix III 2.d"]);
    expect(transcriptChips(reduceSnapshot(snapshot({ alerts: [{ ...cited, cited_title: null }] }), "operator", T0), catalog, t)
      .map((c) => c.text)).toEqual(["asean_cosmetic_claims_guideline_appendix_iii_2007 2.d"]);  // the host's own fallback
  });
  it("empty state renders nothing heavy", () => {
    expect(stackAlerts(emptyState("operator"), T0)).toEqual([]);
  });
});

// ---- rendering --------------------------------------------------------------------------------------------

class FakeEventSource {
  static CLOSED = 2;
  readyState = 1;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public url: string) {
    setTimeout(() => this.onopen?.(), 0);
  }
  addEventListener() {}
  close() {}
}

type Call = { method: string; path: string; body: unknown };
let calls: Call[] = [];
let snap: StateSnapshot;
let answerReplies: { status: number; body: unknown }[] = [];

beforeEach(() => {
  calls = [];
  answerReplies = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = url.split("?")[0];
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ method, path, body });
      let status = 200;
      let out: unknown = { ok: true };
      if (path.split("?")[0] === "/api/catalog") out = catalog;
      else if (path === "/api/health") out = { status: "ok", demo_tools_enabled: true };
      else if (path.endsWith("/state")) out = snap;
      else if (path.endsWith("/answer") && answerReplies.length) ({ status, body: out } = answerReplies.shift()!);
      return new Response(JSON.stringify(out), { status, headers: { "Content-Type": "application/json" } });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Operator screen", () => {
  it("links back to the hub with the session and asks first while live", async () => {
    snap = snapshot({ session: { ...snapshot().session!, status: "live" } });
    render(<Operator sessionId="ses_op_hub" />);
    const link = await screen.findByTestId("hub-link");
    expect(link).toHaveAttribute("href", "/?session=ses_op_hub");
    fireEvent.click(link);
    expect(screen.getByTestId("hub-link-confirm")).toBeInTheDocument();
  });

  it("shows the escalated compliance card as Not corrected", async () => {
    snap = snapshot({ alerts: [alert({ escalated_at: T0 + 10_000 })] });
    render(<Operator sessionId="ses_op_escalated" />);
    const card = await screen.findByTestId("op-alert-al_000001");
    expect(card).toHaveAttribute("data-state", "escalated");
    expect(within(card).getByText(/^Not corrected · /)).toBeInTheDocument();
    expect(within(card).getByTestId("op-alert-host")).toHaveTextContent("The host sees this alert now.");
    expect(within(card).getByText("Send correction cue")).toBeInTheDocument();
    expect(within(card).getByText("Dismiss false alert")).toBeInTheDocument();
    expect(screen.getByText("Live control room")).toBeInTheDocument();
    expect(screen.getByText(/BROADCAST WORKSPACE/)).toBeInTheDocument();
  });

  it("D-404: says where each alert is on the host screen: shown, held behind a red, or in +N", async () => {
    const red = alert({ alert_id: "al_red", transcript_id: "tr_red", span: "erases wrinkles" });
    const held = alert({ alert_id: "al_held", transcript_id: "tr_red", rule_id: "BRAND-SUPERLATIVE", severity: "MEDIUM",
      span: "the best" });
    const fact = alert({ alert_id: "fx_1", kind: "fact", transcript_id: "tr_f1", rule_id: null, severity: null,
      field: "price", passage_id: "P#1" });
    const beyond = alert({ alert_id: "fx_2", kind: "fact", transcript_id: "tr_f2", rule_id: null, severity: null,
      field: "volume", passage_id: "P#2", created_at: T0 - 5000, shown_at: T0 - 5000 });
    snap = snapshot({ alerts: [red, held, fact, beyond] });
    render(<Operator sessionId="ses_op_seen" />);
    const seen = async (id: string) =>
      within(await screen.findByTestId(`op-alert-${id}`)).getByTestId("op-alert-host").getAttribute("data-seen");
    expect(await seen("al_red")).toBe("shown");
    expect(await seen("al_held")).toBe("held");
    expect(await seen("fx_1")).toBe("shown");
    expect(await seen("fx_2")).toBe("more");
  });

  it("D-407: with two reds both are shown and the fact note is in +N", async () => {
    const red1 = alert({ alert_id: "al_r1", transcript_id: "tr_r1", span: "erases wrinkles" });
    const red2 = alert({ alert_id: "al_r2", transcript_id: "tr_r2", span: "cures acne", created_at: T0 - 5000,
      shown_at: T0 - 5000 });
    const fact = alert({ alert_id: "fx_1", kind: "fact", transcript_id: "tr_f1", rule_id: null, severity: null,
      field: "price", passage_id: "P#1" });
    snap = snapshot({ alerts: [red1, red2, fact] });
    render(<Operator sessionId="ses_op_two_reds" />);
    const host = async (id: string) =>
      within(await screen.findByTestId(`op-alert-${id}`)).getByTestId("op-alert-host");
    expect(await host("al_r1")).toHaveTextContent("The host sees this alert now.");
    expect(await host("al_r2")).toHaveTextContent("The host sees this alert now.");
    expect(await host("fx_1")).toHaveTextContent('Not on the host screen yet: counted in "+N".');
  });

  it("D-374: shows the model's citation and summary, labelled as the AI's", async () => {
    snap = snapshot({ alerts: [alert({ citation: "guideline.pdf#3", quote: "Removes wrinkles or reverses skin ageing." })] });
    render(<Operator sessionId="ses_op_citation" />);
    const card = await screen.findByTestId("op-alert-al_000001");
    expect(within(card).getByTestId("op-alert-citation")).toHaveTextContent("AI citation: guideline.pdf#3");
    expect(within(card).getByTestId("op-alert-summary")).toHaveTextContent(
      "AI summary: Removes wrinkles or reverses skin ageing.");
  });

  it("D-120: a collapsed row shows the proposed reply and the next action without opening", async () => {
    snap = snapshot({
      groups: [
        group({ group_id: "g_rev", canonical_question: "Is it suitable for oily skin?", status: "needs_review", answer_id: "ans_000001" }),
        group({ group_id: "g_none", canonical_question: "Do you ship to Malaysia?", status: "needs_review", answer_id: null, intent: "shipping" }),
      ],
      answers: { ans_000001: answer() },
    });
    render(<Operator sessionId="ses_op_preview" />);
    const desk = await screen.findByTestId("op-question-desk");
    // the first row is open by default; the operator closes it, and every row is then a collapsed one
    fireEvent.click(await within(desk).findByRole("button", { name: /Is it suitable for oily skin\?/ }));
    const row = await within(desk).findByTestId("op-preview-g_rev");
    expect(row).toHaveTextContent(answer().text);
    expect(within(row).getByRole("button", { name: "Post" })).toBeEnabled();
    // the whole reply wraps before it can be posted (no ellipsis)
    expect(row.querySelector("span")?.className).toMatch(/previewFull/);
    expect(within(desk).getByTestId("op-preview-g_none")).toHaveTextContent("No AI draft for this question.");
  });

  it("has three tabs, To do first and selected, with a count on each", async () => {
    snap = snapshot({
      groups: [
        group({ group_id: "g_ready", canonical_question: "Is it suitable for oily skin?", status: "ready", route: "OPERATOR", answer_id: "ans_000001" }),
        group({ group_id: "g_review", canonical_question: "Can I use it while pregnant?", status: "needs_review", intent: "pregnancy_breastfeeding" }),
        group({ group_id: "g_ai", canonical_question: "How much is it?", status: "auto_answered", route: "AUTO", intent: "price" }),
        group({ group_id: "g_closed", canonical_question: "Do you ship?", status: "closed", intent: "shipping" }),
      ],
      answers: { ans_000001: answer() },
    });
    render(<Operator sessionId="ses_op_tabs" />);
    const desk = await screen.findByTestId("op-question-desk");
    await within(desk).findByTestId("op-group-g_ready");
    const tabs = within(desk).getAllByRole("tab");
    expect(tabs.map((x) => x.getAttribute("data-testid"))).toEqual(["op-desk-tab-todo", "op-desk-tab-answered", "op-desk-tab-all"]);
    expect(tabs.map((x) => x.textContent!.replace(/\s+/g, " ").trim())).toEqual(["To do 2", "Answered 1", "All 4"]);
    expect(tabs.map((x) => x.getAttribute("aria-selected"))).toEqual(["true", "false", "false"]);
    // To do: what waits for a person
    expect(within(desk).getAllByTestId(/^op-group-/).map((e) => e.getAttribute("data-testid")).sort()).toEqual(["op-group-g_ready", "op-group-g_review"]);
    fireEvent.click(within(desk).getByRole("tab", { name: /Answered/ }));
    expect(within(desk).getAllByTestId(/^op-group-/).map((e) => e.getAttribute("data-testid"))).toEqual(["op-group-g_ai"]);
    // closed groups are listed only under All
    expect(within(desk).queryByTestId("op-group-g_closed")).not.toBeInTheDocument();
    fireEvent.click(within(desk).getByRole("tab", { name: /All/ }));
    expect(within(desk).getAllByTestId(/^op-group-/)).toHaveLength(4);
    expect(within(desk).getByTestId("op-group-g_closed")).toHaveAttribute("data-tab", "closed");
  });

  it("every group is in exactly one of To do / Answered / closed, and the tab counts add up", async () => {
    const groups = [
      group({ group_id: "g_review", status: "needs_review", intent: "pregnancy_breastfeeding", canonical_question: "Q review" }),
      group({ group_id: "g_assign", status: "needs_review", route_reason: "unresolved_product", product_id: null, canonical_question: "Q assign" }),
      group({ group_id: "g_verbal", status: "ready", host_verbal_answer_transcript_id: "tr_9", canonical_question: "Q verbal" }),
      group({ group_id: "g_onhost", status: "ready", host_slot: "on_host", canonical_question: "Q on host" }),
      group({ group_id: "g_ready", status: "ready", canonical_question: "Q ready" }),
      group({ group_id: "g_comp", status: "composing", canonical_question: "Q composing" }),
      group({ group_id: "g_ai", status: "auto_answered", route: "AUTO", intent: "price", canonical_question: "Q ai" }),
      group({ group_id: "g_ans", status: "answered", canonical_question: "Q answered" }),
      group({ group_id: "g_rej", status: "rejected", canonical_question: "Q rejected" }),
      group({ group_id: "g_closed", status: "closed", intent: "price", canonical_question: "Q closed" }),
    ];
    snap = snapshot({ groups });
    render(<Operator sessionId="ses_op_counts" />);
    const desk = await screen.findByTestId("op-question-desk");
    await within(desk).findByTestId("op-group-g_review");
    const tabCount = (key: string) => Number(within(within(desk).getByTestId(`op-desk-tab-${key}`)).getByText(/^\d+$/).textContent);
    expect(tabCount("all")).toBe(groups.length);
    expect(Number(within(desk).getByTestId("op-desk-count").textContent)).toBe(groups.length);
    expect(tabCount("todo")).toBe(6);
    expect(tabCount("answered")).toBe(2);
    const seen = new Map<string, string>();
    for (const key of ["todo", "answered"]) {
      fireEvent.click(within(desk).getByTestId(`op-desk-tab-${key}`));
      const rows = within(desk).queryAllByTestId(/^op-group-/);
      expect(rows.length).toBe(tabCount(key));
      for (const row of rows) {
        expect(row).toHaveAttribute("data-tab", key);
        expect(seen.has(row.getAttribute("data-testid")!)).toBe(false);
        seen.set(row.getAttribute("data-testid")!, key);
      }
    }
    // the rest is closed or rejected: visible only under All
    expect(seen.size).toBe(tabCount("todo") + tabCount("answered"));
    fireEvent.click(within(desk).getByTestId("op-desk-tab-all"));
    const rest = within(desk).getAllByTestId(/^op-group-/).filter((r) => !seen.has(r.getAttribute("data-testid")!));
    expect(rest.map((r) => r.getAttribute("data-tab"))).toEqual(["closed", "closed"]);
    expect(seen.size + rest.length).toBe(groups.length);
  });

  it("explains an empty To do list, and what to do with the desk", async () => {
    snap = snapshot({ groups: [group({ group_id: "g_ai", status: "auto_answered", route: "AUTO", intent: "price" })] });
    render(<Operator sessionId="ses_op_todo_empty" />);
    const desk = await screen.findByTestId("op-question-desk");
    expect(await within(desk).findByTestId("op-desk-empty")).toHaveTextContent("Nothing is waiting for you. Questions that need a person appear here.");
    expect(within(desk).getByText("Viewer questions that need a person. Check the suggested reply, edit it if you want, and post.")).toBeInTheDocument();
    expect(within(desk).queryByText("Grouped by topic.")).not.toBeInTheDocument();
  });

  it("each row has one plain status chip and the reason it waits as quiet text", async () => {
    snap = snapshot({
      groups: [
        group({ group_id: "g_op", status: "needs_review", route: "OPERATOR", route_reason: "no_verified_answer", canonical_question: "Q op" }),
        group({ group_id: "g_host", status: "ready", route: "HOST", route_reason: "approval", approval_reason: "claim", canonical_question: "Q host" }),
        group({ group_id: "g_health", status: "ready", route: "HOST", route_reason: "approval", approval_reason: "health", host_slot: "on_host", intent: "pregnancy_breastfeeding", canonical_question: "Q health" }),
        group({ group_id: "g_draft", status: "composing", canonical_question: "Q draft" }),
        group({ group_id: "g_assign", status: "needs_review", route_reason: "unresolved_product", product_id: null, canonical_question: "Q assign" }),
        group({ group_id: "g_verbal", status: "ready", host_verbal_answer_transcript_id: "tr_9", canonical_question: "Q verbal" }),
        group({ group_id: "g_ai", status: "auto_answered", route: "AUTO", canonical_question: "Q ai" }),
        group({ group_id: "g_ans", status: "answered", published_message_id: "m_h", canonical_question: "Q host answered" }),
        group({ group_id: "g_ans2", status: "answered", canonical_question: "Q answered" }),
        group({ group_id: "g_closed", status: "closed", canonical_question: "Q closed" }),
        group({ group_id: "g_rej", status: "rejected", canonical_question: "Q rejected" }),
      ],
      messages: [message({ message_id: "m_h", kind: "host_answer", group_id: "g_ans" })],
    });
    render(<Operator sessionId="ses_op_chips" />);
    const desk = await screen.findByTestId("op-question-desk");
    await within(desk).findByTestId("op-group-g_op");
    fireEvent.click(within(desk).getByTestId("op-desk-tab-all"));
    const chip = (id: string) => {
      const chips = within(screen.getByTestId(`op-group-${id}`)).getAllByTestId("op-status-chip");
      expect(chips).toHaveLength(1); // one chip, never a stack
      return chips[0].textContent;
    };
    expect(chip("g_op")).toBe("Needs your reply");
    expect(chip("g_host")).toBe("Needs a reply · host can answer on air");
    expect(chip("g_health")).toBe("Needs a reply · host can answer on air");
    expect(chip("g_draft")).toBe("Drafting…");
    expect(chip("g_assign")).toBe("Assign a product");
    expect(chip("g_verbal")).toBe("Host answered on air · not posted");
    expect(chip("g_ai")).toBe("Answered by AI");
    expect(chip("g_ans")).toBe("Answered by the host");
    expect(chip("g_ans2")).toBe("Answered");
    expect(chip("g_closed")).toBe("Closed");
    expect(chip("g_rej")).toBe("Closed");
    // the reason a question waits, in quiet words next to the product
    const reason = (id: string) => within(screen.getByTestId(`op-group-${id}`)).getByTestId("op-reason").textContent;
    expect(reason("g_op")).toBe("No verified answer in the product sheet");
    expect(reason("g_host")).toBe("Claim about results");
    expect(reason("g_health")).toBe("Health or safety");
    // a health row has one accent (not an extra chip); the others have none
    expect(screen.getByTestId("op-group-g_health")).toHaveAttribute("data-sensitive", "true");
    expect(screen.getByTestId("op-group-g_host")).not.toHaveAttribute("data-sensitive");
    // the old stack is gone
    expect(within(desk).queryByText("On the host's card")).toBeNull();
    expect(within(desk).queryByText("Sensitive", { selector: "span:not(.visually-hidden)" })).toBeNull();
  });

  it("opens the first To do row by default, and the operator's own choice wins", async () => {
    snap = snapshot({
      groups: [
        group({ group_id: "g_a", canonical_question: "First question?", status: "needs_review", route: "OPERATOR", score: 5 }),
        group({ group_id: "g_b", canonical_question: "Second question?", status: "needs_review", route: "OPERATOR", score: 1 }),
      ],
    });
    render(<Operator sessionId="ses_op_autoexpand" />);
    const desk = await screen.findByTestId("op-question-desk");
    const head = (id: string) => within(screen.getByTestId(`op-group-${id}`)).getAllByRole("button")[0];
    await within(desk).findByTestId("op-reply-g_a");
    expect(head("g_a")).toHaveAttribute("aria-expanded", "true");
    expect(head("g_b")).toHaveAttribute("aria-expanded", "false");
    expect(within(desk).queryByTestId("op-reply-g_b")).toBeNull();
    // collapse it: it stays collapsed, nothing else opens by itself
    fireEvent.click(head("g_a"));
    expect(within(desk).queryByTestId("op-reply-g_a")).toBeNull();
    expect(within(desk).queryByTestId("op-reply-g_b")).toBeNull();
    // open the second: that is the operator's choice now
    fireEvent.click(head("g_b"));
    expect(within(desk).getByTestId("op-reply-g_b")).toBeInTheDocument();
    expect(within(desk).queryByTestId("op-reply-g_a")).toBeNull();
    // no default on the Answered tab
    fireEvent.click(within(desk).getByTestId("op-desk-tab-answered"));
    expect(within(desk).queryByTestId(/^op-reply-/)).toBeNull();
  });

  it("when the open row is posted and leaves To do, the next one opens", async () => {
    const g = (id: string, score: number) => group({ group_id: id, canonical_question: `Question ${id}?`, status: "needs_review", route: "OPERATOR", score });
    const first = reduceSnapshot(snapshot({ groups: [g("g_a", 5), g("g_b", 1)] }), "operator", T0);
    const second = reduceSnapshot(snapshot({ groups: [{ ...g("g_a", 5), status: "answered" }, g("g_b", 1)] }), "operator", T0);
    const ui = (state: typeof first) => (
      <OperatorProvider value={{ sid: "s", state, catalog, now: T0 + 5000 }}>
        <QuestionDesk />
      </OperatorProvider>
    );
    const { rerender } = render(ui(first));
    expect(screen.getByTestId("op-reply-g_a")).toBeInTheDocument();
    rerender(ui(second));
    expect(screen.queryByTestId("op-reply-g_a")).toBeNull();
    expect(screen.getByTestId("op-reply-g_b")).toBeInTheDocument();
  });

  it("the collapsed row's buttons use the same words as the reply box", async () => {
    snap = snapshot({
      groups: [
        group({ group_id: "g_first", canonical_question: "Open one?", status: "needs_review", route: "OPERATOR", score: 9 }),
        group({ group_id: "g_ver", canonical_question: "Verified one?", status: "needs_review", route: "OPERATOR", answer_id: "ans_000001", score: 3 }),
        group({ group_id: "g_none", canonical_question: "No draft one?", status: "needs_review", route: "OPERATOR", answer_id: null, score: 2 }),
        group({ group_id: "g_card", canonical_question: "On the card?", status: "ready", route: "HOST", host_slot: "on_host", answer_id: null, score: 1 }),
      ],
      answers: { ans_000001: answer() },
    });
    render(<Operator sessionId="ses_op_labels" />);
    const desk = await screen.findByTestId("op-question-desk");
    await within(desk).findByTestId("op-preview-g_ver");
    expect(within(within(desk).getByTestId("op-preview-g_ver")).getByRole("button", { name: "Post" })).toBeEnabled();
    expect(within(within(desk).getByTestId("op-preview-g_none")).getByRole("button", { name: "Send to host" })).toBeEnabled();
    expect(within(desk).queryByRole("button", { name: /Post to chat|Push to host/ })).toBeNull();
    // on the host's card: the way back is "Take back"
    fireEvent.click(within(screen.getByTestId("op-group-g_card")).getAllByRole("button")[0]);
    expect(within(screen.getByTestId("op-group-g_card")).getByRole("button", { name: "Take back" })).toBeInTheDocument();
    expect(within(desk).queryByRole("button", { name: "Recall" })).toBeNull();
  });

  it("the Post button is the primary control of the open row", async () => {
    snap = snapshot({ groups: [group({ group_id: "g_p", status: "needs_review", route: "OPERATOR", answer_id: "ans_000001" })], answers: { ans_000001: answer() } });
    render(<Operator sessionId="ses_op_post_primary" />);
    const row = await screen.findByTestId("op-group-g_p");
    const post = await within(row).findByRole("button", { name: "Post" });
    const others = within(row).getAllByRole("button").filter((b) => b !== post && b.getAttribute("aria-expanded") === null);
    expect(post.className).toMatch(/primary/);
    expect(post.className).not.toMatch(/\bsm\b|_sm_/); // the larger size
    expect(others.length).toBeGreaterThan(0);
    for (const b of others) expect(b.className).not.toMatch(/primary/);
  });

  it("set-price groups show the set short_name from products.json as product label (item 4, D-085)", async () => {
    snap = snapshot({
      groups: [group({ group_id: "g_set", intent: "set_price", status: "auto_answered", route: "AUTO", canonical_question: "How much is the set?", member_comment_ids: ["cm_s"] })],
      comments: [comment({ comment_id: "cm_s", group_id: "g_set", kind: "question", text: "how much is the set?" })],
    });
    render(<Operator sessionId="ses_op_set" />);
    fireEvent.click(await screen.findByTestId("op-desk-tab-all"));
    const row = await screen.findByTestId("op-group-g_set");
    expect(within(row).getByText("Cream + Ampoule set")).toBeInTheDocument();
    expect(within(row).queryByText("Hydra Barrier Cream")).toBeNull();
    expect(within(row).queryByText(catalog.set_offers[0].name)).toBeNull();
    const stream = screen.getByTestId("op-comment-cm_s");
    expect(within(stream).getByText("Cream + Ampoule set")).toBeInTheDocument();
  });

  it("a comment in another language shows its language tag and English reading in the stream and the desk row", async () => {
    snap = snapshot({
      groups: [group({ group_id: "g_ko", canonical_question: "Can pregnant women use it?", member_comment_ids: ["cm_ko", "cm_en"] })],
      comments: [
        comment({ comment_id: "cm_ko", group_id: "g_ko", text: "임산부도 써도 되나요?", language: "ko", translation_en: "Can pregnant women use it too?" }),
        comment({ comment_id: "cm_en", group_id: "g_ko", text: "ok while pregnant?", language: "en", translation_en: null }),
      ],
    });
    render(<Operator sessionId="ses_op_translation" />);
    const row = await screen.findByTestId("op-comment-cm_ko");
    expect(within(row).getByText("임산부도 써도 되나요?")).toBeInTheDocument();
    const translation = within(row).getByTestId("op-comment-translation-cm_ko");
    expect(translation).toHaveTextContent("KO");
    expect(translation).toHaveTextContent("Can pregnant women use it too?");
    expect(within(screen.getByTestId("op-comment-cm_en")).queryByTestId("op-comment-translation-cm_en")).toBeNull();

    const desk = screen.getByTestId("op-group-g_ko"); // the first To do row is open
    expect(within(desk).getByTestId("op-comment-translation-cm_ko")).toHaveTextContent("Can pregnant women use it too?");
    expect(within(desk).queryByTestId("op-comment-translation-cm_en")).toBeNull();
  });

  it("a set without short_name falls back to its full name", () => {
    const { short_name: _, ...set } = catalog.set_offers[0];
    expect(setLabel(set)).toBe("Hydra Barrier Cream + Deep Hydration Ampoule set");
    expect(setLabel(catalog.set_offers[0])).toBe("Cream + Ampoule set");
  });

  it("no source: the standard reply is the starting text, with a note only the team sees, and it stays editable", async () => {
    snap = snapshot({
      groups: [group({ group_id: "g_ns", status: "needs_review", route: "OPERATOR", route_reason: "no_verified_answer", answer_id: null, intent: "shipping", canonical_question: "Do you ship to Malaysia?" })],
    });
    render(<Operator sessionId="ses_op_nosource" />);
    const desk = await screen.findByTestId("op-question-desk");
    await within(desk).findByTestId("op-reply-g_ns");
    expect(within(desk).getByTestId("op-no-source-g_ns")).toHaveTextContent("No source: the product information does not answer this");
    const box = within(desk).getByLabelText("Reply") as HTMLTextAreaElement;
    expect(box.value).toBe("That isn't covered in our product information. Our team will check and get back to you.");
    expect(within(desk).getByText("Posts the standard reply: it states no product fact")).toBeInTheDocument();
    fireEvent.change(box, { target: { value: "We ship to Malaysia from next month." } });
    expect(within(desk).getByText("Your own reply: posts as it is, not checked")).toBeInTheDocument();
    fireEvent.click(within(desk).getByRole("button", { name: "Back to the standard reply" }));
    expect(box.value).toBe("That isn't covered in our product information. Our team will check and get back to you.");
  });

  it("an unverified draft sits in the reply box and is posted as the operator's text, never approved as it is", async () => {
    snap = snapshot({
      groups: [group({ group_id: "g_x", status: "needs_review", answer_id: "ans_x", canonical_question: "Can I use it while pregnant?" })],
      answers: { ans_x: answer({ answer_id: "ans_x", verified: false, verify_errors: ["no citation"] }) },
    });
    render(<Operator sessionId="ses_op_unverified" />);
    const desk = await screen.findByTestId("op-question-desk");
    await within(desk).findByTestId("op-reply-g_x");
    expect(within(desk).getByText("Not confirmed by the product sheet. Check it before you post.")).toBeInTheDocument();
    const box = within(desk).getByLabelText("Reply") as HTMLTextAreaElement;
    expect(box.value).toBe(answer({ answer_id: "ans_x" }).text);
    expect(within(desk).getByText("Not verified: posts as it is, not checked")).toBeInTheDocument();
    fireEvent.click(within(desk).getByRole("button", { name: "Post" }));
    await waitFor(() => expect(calls.some((c) => c.path.endsWith("/groups/g_x/answer"))).toBe(true));
    expect(calls.some((c) => c.path.endsWith("/groups/g_x/approve"))).toBe(false);
    expect((calls.find((c) => c.path.endsWith("/groups/g_x/answer"))!.body as { origin: string }).origin).toBe("operator_edit");
  });

  it("a verified suggestion is posted as it is with one click, or edited in place", async () => {
    snap = snapshot({
      groups: [group({ group_id: "g_v", status: "needs_review", answer_id: "ans_v", canonical_question: "Is it ok for dry skin?" })],
      answers: { ans_v: answer({ answer_id: "ans_v", verified: true, verify_errors: [] }) },
    });
    render(<Operator sessionId="ses_op_reply_box" />);
    const desk = await screen.findByTestId("op-question-desk");
    await within(desk).findByTestId("op-reply-g_v");
    const box = within(desk).getByLabelText("Reply") as HTMLTextAreaElement;
    const suggestion = answer({ answer_id: "ans_v" }).text;
    expect(box.value).toBe(suggestion);
    expect(within(desk).getByText("Posts the suggested reply as it is")).toBeInTheDocument();
    // edited: it becomes the operator's text, and the suggestion can be brought back
    fireEvent.change(box, { target: { value: `${suggestion} Thank you for asking.` } });
    expect(within(desk).getByText("Edited: posts as it is, not checked")).toBeInTheDocument();
    fireEvent.click(within(desk).getByRole("button", { name: "Back to the suggestion" }));
    expect(box.value).toBe(suggestion);
    // unchanged: one click approves the suggestion
    fireEvent.click(within(desk).getByRole("button", { name: "Post" }));
    await waitFor(() => expect(calls.some((c) => c.path.endsWith("/groups/g_v/approve"))).toBe(true));
    expect(calls.some((c) => c.path.endsWith("/groups/g_v/answer"))).toBe(false);
  });

  it("shows header labels in Korean when the screen language is Korean (D-109)", async () => {
    snap = snapshot();
    setLang("ko");
    try {
      render(<Operator sessionId="ses_op_ko" />);
      const header = await screen.findByTestId("op-header");
      expect(within(header).getByText("라이브 컨트롤룸")).toBeInTheDocument();
    } finally {
      setLang("en");
    }
  });
});

describe("operator desk rows and header (D-120)", () => {
  it("hides latency chips until a real latency is measured", async () => {
    const { latencyShown } = await import("./Header");
    expect(latencyShown({ header: { alert_in_s: 0, judge_p50_s: null } })).toEqual({ alert: false, judge: false });
    expect(latencyShown({ header: { alert_in_s: 2.4, judge_p50_s: 1.2 } })).toEqual({ alert: true, judge: true });
  });
});

describe("stream problem reports", () => {
  it("counts viewers who reported a stream problem in the last two minutes", async () => {
    const { streamIssues, STREAM_ISSUE_WINDOW_MS } = await import("./model");
    const c = (id: string, author: string, at: number, signal: "stream_issue" | "injection" | null) =>
      ({ comment_id: id, author_id: author, author_name: author, text: id, received_at: at, source: "viewer",
         visibility: "visible", hide_category: null, kind: "reaction", analysis_id: null, group_id: null, signal }) as const;
    const now = 1_000_000;
    const comments = {
      a: c("a", "u1", now - 10_000, "stream_issue"),
      b: c("b", "u1", now - 5_000, "stream_issue"), // the same viewer again: one report
      d: c("d", "u2", now - 60_000, "stream_issue"),
      e: c("e", "u3", now - STREAM_ISSUE_WINDOW_MS - 1, "stream_issue"), // too old
      f: c("f", "u4", now - 1_000, "injection"),
      g: c("g", "u5", now - 1_000, null),
    };
    const r = streamIssues(comments, now);
    expect(r.viewers).toBe(2);
    expect(r.latest?.comment_id).toBe("b");
    expect(streamIssues({}, now)).toEqual({ viewers: 0, latest: null });
  });
});

// ---- simplified screen: attention dots, hidden comments, header, rail ---------------------------------------------


const opState = (over: Parameters<typeof snapshot>[0] = {}) => reduceSnapshot(snapshot(over), "operator", T0);
const withState = (state: ReturnType<typeof opState>, ui: React.ReactNode) => (
  <OperatorProvider value={{ sid: "s", state, catalog, now: T0 + 5000 }}>{ui}</OperatorProvider>
);

describe("attention dots (no sound, no toast)", () => {
  const todo = (id: string) => group({ group_id: id, canonical_question: `Question ${id}?`, status: "needs_review", route: "OPERATOR" });

  it("useArrivalDot: nothing already there raises it; a newcomer does while not viewing, and viewing clears it", () => {
    const { result, rerender } = renderHook(({ ids, viewing }) => useArrivalDot(ids, true, viewing), {
      initialProps: { ids: ["a", "b"], viewing: false },
    });
    expect(result.current).toBe(false);
    rerender({ ids: ["a", "b", "c"], viewing: false });
    expect(result.current).toBe(true);
    rerender({ ids: ["a", "b", "c"], viewing: true });
    expect(result.current).toBe(false);
    rerender({ ids: ["a", "b", "c", "d"], viewing: true }); // looking at it: no dot
    expect(result.current).toBe(false);
    rerender({ ids: ["a", "b", "c", "d"], viewing: false });
    expect(result.current).toBe(false);
  });

  it("does not fire before the state is loaded (the first snapshot is not news)", () => {
    const { result, rerender } = renderHook(({ ids, loaded }) => useArrivalDot(ids, loaded, false), { initialProps: { ids: [] as string[], loaded: false } });
    rerender({ ids: ["a", "b"], loaded: true });
    expect(result.current).toBe(false);
  });

  it("a new To do question while on another tab puts a dot on the To do tab, which clears when it is opened", () => {
    const ui = (...ids: string[]) => withState(opState({ groups: ids.map(todo) }), <QuestionDesk />);
    const { rerender } = render(ui("g_a"));
    expect(screen.queryByTestId("op-todo-dot")).toBeNull();
    // on the To do tab itself the new row is right there: no dot
    rerender(ui("g_a", "g_b"));
    expect(screen.queryByTestId("op-todo-dot")).toBeNull();
    fireEvent.click(screen.getByTestId("op-desk-tab-all"));
    rerender(ui("g_a", "g_b", "g_c"));
    const dot = screen.getByTestId("op-todo-dot");
    expect(screen.getByTestId("op-desk-tab-todo")).toContainElement(dot);
    expect(dot).toHaveAccessibleName("New question");
    expect(screen.getByTestId("op-desk-tab-all")).not.toContainElement(dot);
    fireEvent.click(screen.getByTestId("op-desk-tab-todo"));
    expect(screen.queryByTestId("op-todo-dot")).toBeNull();
  });

  it("a comment hidden while the stream shows the visible list puts a dot on 'Hidden comments', which clears when opened", () => {
    const hid = comment({ comment_id: "cm_bad", text: "you are all idiots", author_name: "T", visibility: "hidden", hide_category: "abuse", kind: "hide", group_id: null });
    const ok = comment({ comment_id: "cm_ok", text: "how much?", group_id: null, kind: "reaction" });
    const analyses = { cm_bad: { analysis_id: "an_1", comment_id: "cm_bad", output: { reason: "Insults aimed at the host." }, product_id: null, product_basis: "unknown" as const, context_product_id: null, route: null, route_reason: null, source: "llm" as const, latency_ms: 300 } };
    const { rerender } = render(withState(opState({ comments: [ok] }), <CommentStream />));
    const toggle = () => screen.getByRole("button", { name: /Hidden comments/ });
    expect(toggle()).toHaveTextContent("Hidden comments (0)");
    expect(screen.queryByText(/Show filtered/)).toBeNull();
    expect(screen.queryByTestId("op-hidden-dot")).toBeNull();
    rerender(withState(opState({ comments: [ok, hid], analyses }), <CommentStream />));
    expect(toggle()).toHaveTextContent("Hidden comments (1)");
    expect(within(toggle()).getByTestId("op-hidden-dot")).toBeInTheDocument();
    expect(toggle()).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(toggle());
    expect(screen.queryByTestId("op-hidden-dot")).toBeNull();
    // the hide category, the reason triage gave, and Unhide, next to each other
    const row = screen.getByTestId("op-comment-cm_bad");
    expect(within(row).getByText("Abuse")).toBeInTheDocument();
    expect(within(row).getByTestId("op-hide-reason-cm_bad")).toHaveTextContent("Insults aimed at the host.");
    expect(within(row).getByRole("button", { name: "Unhide" })).toBeInTheDocument();
  });

  it("a hidden comment without a triage reason shows no reason line; an empty list says so", () => {
    const hid = comment({ comment_id: "cm_x", visibility: "hidden", hide_category: "spam", kind: "hide", group_id: null });
    render(withState(opState({ comments: [hid] }), <CommentStream />));
    fireEvent.click(screen.getByRole("button", { name: /Hidden comments \(1\)/ }));
    expect(screen.queryByTestId("op-hide-reason-cm_x")).toBeNull();
    cleanup();
    render(withState(opState({ comments: [] }), <CommentStream />));
    fireEvent.click(screen.getByRole("button", { name: /Hidden comments \(0\)/ }));
    expect(screen.getByText("No hidden comments.")).toBeInTheDocument();
  });
});

describe("operator header and right rail", () => {
  const cat = { ...catalog, notices: { ...catalog.notices!, host_cue_presets: [{ cue_id: "c1", label: "Time sale", text: "Mention the time sale." }], operator_quick_replies: [{ reply_id: "q1", text: "Delivery details are shown at checkout." }] } };
  const metrics = { header: { instant_answers: 3, answers_total: 5 }, impact: { risky_lines: { alerted: 1, of_lines: 4 }, questions: { ai: 2, host: 1, operator: 1, of_askers: 4 }, operator_actions: 2, llm: { calls: 9, tokens: 1000, tokens_per_hour: 396_000 } } };

  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState({}, "", "/");
  });
  afterEach(() => {
    window.history.replaceState({}, "", "/");
  });

  let railId = 0; // the store keeps one state per session id
  const rail = async (over: Parameters<typeof snapshot>[0] = {}) => {
    snap = snapshot({ metrics: metrics as never, ...over });
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      const path = url.split("?")[0];
      const out = path === "/api/catalog" ? cat : path === "/api/health" ? { status: "ok", demo_tools_enabled: true } : path.endsWith("/state") ? snap : { ok: true };
      return new Response(JSON.stringify(out), { status: 200, headers: { "Content-Type": "application/json" } });
    }));
    render(<Operator sessionId={`ses_op_rail_${++railId}`} />);
    return screen.findByTestId("op-transcript");
  };

  it("keeps the metric chips out of the header, in a Show stats disclosure that starts closed", async () => {
    await rail();
    const header = screen.getByTestId("op-header");
    expect(within(header).queryByTestId("op-metrics")).toBeNull();
    expect(within(header).queryByTestId("op-impact")).toBeNull();
    expect(header).not.toHaveTextContent(/Instant answers|tokens\/h|Operator actions/);
    expect(within(header).getByText("Live control room")).toBeInTheDocument();
    const stats = screen.getByTestId("op-stats");
    const toggle = within(stats).getByRole("button", { name: "Show stats" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(within(stats).queryByTestId("op-metrics")).toBeNull();
    fireEvent.click(toggle);
    expect(within(stats).getByRole("button", { name: "Hide stats" })).toHaveAttribute("aria-expanded", "true");
    expect(within(stats).getByTestId("op-metrics")).toHaveTextContent("Instant answers 3/5");
    expect(within(stats).getByTestId("op-impact")).toHaveTextContent("Lines with alerts 1 / 4 lines");  // D-348 wording
    expect(within(stats).getByTestId("op-impact")).toHaveTextContent("LLM 396k tokens/h");
  });

  it("keeps the live alerts (stream problem, collecting context) next to LIVE in the header", async () => {
    const now = Date.now();
    await rail({
      comments: [comment({ comment_id: "cm_s", kind: "reaction", signal: "stream_issue", received_at: now - 5000, group_id: null, author_id: "u1" })],
      server_time: now,
    });
    const header = screen.getByTestId("op-header");
    expect(await within(header).findByTestId("op-stream-issue")).toHaveTextContent("1 viewer reports a stream problem");
  });

  it("orders the rail: transcript and alert log first, then banners; host cue and quick replies are closed", async () => {
    await rail();
    const ids = ["op-transcript", "op-alert-log", "op-promos", "op-cue", "op-quick", "op-stats"].map((id) => screen.getByTestId(id));
    for (let i = 1; i < ids.length; i++) {
      expect(ids[i - 1].compareDocumentPosition(ids[i]) & Node.DOCUMENT_POSITION_FOLLOWING, `section ${i}`).toBeTruthy();
    }
    // banners & notices stay open
    expect(within(screen.getByTestId("op-promos")).queryByRole("button", { name: /Banners/ })).toBeNull();
    expect(within(screen.getByTestId("op-promos")).getByPlaceholderText("Pinned notice for viewers")).toBeInTheDocument();
    // host cue and quick replies: a closed disclosure each
    for (const [id, name] of [["op-cue", "Host cue"], ["op-quick", "Quick replies"]] as const) {
      const toggle = within(screen.getByTestId(id)).getByRole("button", { name });
      expect(toggle).toHaveAttribute("aria-expanded", "false");
    }
    expect(screen.queryByPlaceholderText("Cue for the host")).toBeNull();
    expect(screen.queryByText("Delivery details are shown at checkout.")).toBeNull();
  });

  it("opens host cue and quick replies with one click and remembers the choice", async () => {
    await rail();
    fireEvent.click(within(screen.getByTestId("op-cue")).getByRole("button", { name: "Host cue" }));
    expect(screen.getByPlaceholderText("Cue for the host")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Time sale" })).toBeInTheDocument();
    expect(window.localStorage.getItem("ls.op.cue.open")).toBe("1");
    expect(window.localStorage.getItem("ls.op.quick.open")).toBeNull();
    fireEvent.click(within(screen.getByTestId("op-quick")).getByRole("button", { name: "Quick replies" }));
    expect(screen.getByText("Delivery details are shown at checkout.")).toBeInTheDocument();
    cleanup();
    // a new visit: cue stays open, closing it is remembered too
    await rail();
    expect(within(screen.getByTestId("op-cue")).getByRole("button", { name: "Host cue" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByPlaceholderText("Cue for the host")).toBeInTheDocument();
    fireEvent.click(within(screen.getByTestId("op-cue")).getByRole("button", { name: "Host cue" }));
    expect(window.localStorage.getItem("ls.op.cue.open")).toBe("0");
  });

  it("works when storage throws", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    try {
      await rail();
      fireEvent.click(within(screen.getByTestId("op-quick")).getByRole("button", { name: "Quick replies" }));
      expect(screen.getByText("Delivery details are shown at checkout.")).toBeInTheDocument();
    } finally {
      vi.restoreAllMocks();
    }
  });

  it("shows Agent calls only with ?debug=1", async () => {
    await rail();
    expect(screen.queryByRole("region", { name: "Agent calls" })).toBeNull();
    expect(screen.queryByText("Agent calls")).toBeNull();
    cleanup();
    window.history.replaceState({}, "", "/?debug=1");
    await rail();
    expect(screen.getByText("Agent calls")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Agent calls/ })).toHaveAttribute("aria-expanded", "false");
  });

  it("new operator strings have Korean entries", () => {
    for (const k of ["To do", "Needs your reply", "Needs a reply · host can answer on air", "Answered by AI", "Answered by the host", "Hidden comments ({n})",
      "Show stats", "Take back", "Send to host", "Health or safety", "Nothing is waiting for you. Questions that need a person appear here."]) {
      expect(translate("ko", k, { n: 1 }), k).not.toBe(translate("en", k, { n: 1 }));
    }
  });
});
