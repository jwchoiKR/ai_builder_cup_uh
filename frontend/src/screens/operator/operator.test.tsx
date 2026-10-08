import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setLang } from "../../app/i18n";
import { emptyState, reduceSnapshot } from "../../app/state";
import type { QuestionGroup, StateSnapshot } from "../../app/types";
import { alert, answer, catalog, comment, group, message, snapshot, T0 } from "../../test/fixtures";
import { Operator } from "../Operator";
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
    expect(correctedLine(done)).toBe("Corrected in 3.2 s · 'Let me correct that.'");
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
      missingPoints: [{ seq: 1, segment_id: "seg_000001", product_id: "cream_hydra_barrier", missing_point_ids: ["cr-p3"] }],
      judgeFailures: [{ seq: 2, transcript_id: "tr_1" }],
      overtime: { seg_000001: { segment_id: "seg_000001", product_id: "cream_hydra_barrier", overtime_sec: 5 } },
    };
    const cards = systemCards(st, catalog, T0 + 905_000);
    expect(cards.map((c) => c.text)).toEqual([
      "Switched with missing required points: Helps keep skin hydrated for up to 24 hours (in-house test).",
      "AI check unavailable for the last sentence",
      "Overtime +0:05 on Hydra Barrier Cream",
    ]);
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
      switchChips: { tr_1: 1 },
    };
    const t = { transcript_id: "tr_1", text: "Yes it is.", is_final: true, speech_start_at: null, speech_end_at: T0, received_at: T0, source: "injected" as const, segment_id: "seg_000001" };
    expect(transcriptChips(st, catalog, t).map((c) => c.text)).toEqual([
      "ASEAN-3-SKIN-AGEING",
      "answered: Is it suitable for oily skin?",
      "cr-p1",
      "switch cue 1/2",
    ]);
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

  it("requires Post anyway for a restricted phrase", async () => {
    const g = group({ group_id: "grp_ship", intent: "shipping", product_id: null, status: "needs_review", route: "OPERATOR", canonical_question: "Do you ship to Malaysia?", member_comment_ids: ["cm_9"] });
    snap = snapshot({ groups: [g], comments: [comment({ comment_id: "cm_9", group_id: "grp_ship", text: "Do you ship to Malaysia?", author_name: "Kumar" })] });
    answerReplies = [
      { status: 409, body: { error: { code: "restricted_phrase", message: "This reply contains a restricted phrase: 'cures' (Presented as treating or preventing disease)." } } },
      { status: 200, body: { ok: true } },
    ];
    render(<Operator sessionId="ses_op_restricted" />);
    const desk = await screen.findByTestId("op-question-desk");
    fireEvent.click(await within(desk).findByText("Do you ship to Malaysia?", { selector: "span" }));
    fireEvent.click(within(desk).getByRole("button", { name: "Write reply" }));
    fireEvent.change(within(desk).getByLabelText("Write reply"), { target: { value: "Yes, and it cures eczema." } });
    fireEvent.click(within(desk).getByRole("button", { name: "Post" }));
    expect(await within(desk).findByText(/This reply contains a restricted phrase: 'cures'/)).toBeInTheDocument();
    fireEvent.click(within(desk).getByRole("button", { name: "Post anyway" }));
    await waitFor(() => expect(within(desk).queryByLabelText("Write reply")).not.toBeInTheDocument());
    const posts = calls.filter((c) => c.path.endsWith("/groups/grp_ship/answer"));
    expect(posts.map((c) => (c.body as { confirm: boolean }).confirm)).toEqual([false, true]);
    expect((posts[1].body as { origin: string }).origin).toBe("operator_written");
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
    const row = await within(desk).findByTestId("op-preview-g_rev");
    expect(row).toHaveTextContent(answer().text);
    expect(within(row).getByRole("button", { name: "Post to chat" })).toBeEnabled();
    // the whole reply wraps before it can be posted (no ellipsis)
    expect(row.querySelector("span")?.className).toMatch(/previewFull/);
    expect(within(desk).getByTestId("op-preview-g_none")).toHaveTextContent("No AI draft for this question.");
  });

  it("filters the question desk by tab", async () => {
    snap = snapshot({
      groups: [
        group({ group_id: "g_ready", canonical_question: "Is it suitable for oily skin?", status: "ready", answer_id: "ans_000001" }),
        group({ group_id: "g_review", canonical_question: "Can I use it while pregnant?", status: "needs_review", intent: "pregnancy_breastfeeding" }),
        group({ group_id: "g_closed", canonical_question: "How much is it?", status: "closed", intent: "price" }),
      ],
      answers: { ans_000001: answer() },
    });
    render(<Operator sessionId="ses_op_tabs" />);
    const desk = await screen.findByTestId("op-question-desk");
    await within(desk).findByTestId("op-group-g_ready");
    expect(within(desk).getByTestId("op-group-g_closed")).toBeInTheDocument();
    fireEvent.click(within(desk).getByRole("tab", { name: /Needs review/ }));
    expect(within(desk).getByTestId("op-group-g_review")).toBeInTheDocument();
    expect(within(desk).queryByTestId("op-group-g_ready")).not.toBeInTheDocument();
    fireEvent.click(within(desk).getByRole("tab", { name: /Ready/ }));
    expect(within(desk).getByTestId("op-group-g_ready")).toHaveAttribute("data-status", "ready");
    expect(within(desk).queryByTestId("op-group-g_review")).not.toBeInTheDocument();
    fireEvent.click(within(desk).getByRole("tab", { name: /Closed/ }));
    expect(within(desk).getByTestId("op-group-g_closed")).toBeInTheDocument();
  });

  it("header count equals the All tab; every group is in exactly one tab, matching its chip; tabs sum to All (items 2, 3)", async () => {
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
    const all = tabCount("all");
    expect(all).toBe(groups.length);
    expect(Number(within(desk).getByTestId("op-desk-count").textContent)).toBe(all);
    const statusTabs = ["needs_review", "on_host", "ready", "composing", "answered", "closed"];
    expect(statusTabs.reduce((n, k) => n + tabCount(k), 0)).toBe(all);
    // Chip -> tab: each row is listed under exactly the tab its chip belongs to.
    const chipTab: Record<string, string> = {
      "Needs review": "needs_review", "Assign a product": "needs_review", "Host answered on air · not posted": "needs_review",
      "On host": "on_host", Ready: "ready", "Composing…": "composing", "AI answered": "answered", Answered: "answered",
      Rejected: "closed", Closed: "closed",
    };
    const seen = new Map<string, number>();
    for (const key of statusTabs) {
      fireEvent.click(within(desk).getByTestId(`op-desk-tab-${key}`));
      const rows = within(desk).queryAllByTestId(/^op-group-/);
      expect(rows.length).toBe(tabCount(key));
      for (const row of rows) {
        const chip = Object.keys(chipTab).find((label) => within(row).queryByText(label, { exact: true }));
        expect(chip, row.getAttribute("data-testid") ?? "").toBeDefined();
        expect(chipTab[chip!]).toBe(key);
        expect(row).toHaveAttribute("data-tab", key);
        seen.set(row.getAttribute("data-testid")!, (seen.get(row.getAttribute("data-testid")!) ?? 0) + 1);
      }
    }
    expect([...seen.values()].every((n) => n === 1)).toBe(true);
    expect(seen.size).toBe(groups.length);
  });

  it("set-price groups show the set short_name from products.json as product label (item 4, D-085)", async () => {
    snap = snapshot({
      groups: [group({ group_id: "g_set", intent: "set_price", status: "auto_answered", route: "AUTO", canonical_question: "How much is the set?", member_comment_ids: ["cm_s"] })],
      comments: [comment({ comment_id: "cm_s", group_id: "g_set", kind: "question", text: "how much is the set?" })],
    });
    render(<Operator sessionId="ses_op_set" />);
    const row = await screen.findByTestId("op-group-g_set");
    expect(within(row).getByText("Cream + Ampoule set")).toBeInTheDocument();
    expect(within(row).queryByText("Hydra Barrier Cream")).toBeNull();
    expect(within(row).queryByText(catalog.set_offers[0].name)).toBeNull();
    const stream = screen.getByTestId("op-comment-cm_s");
    expect(within(stream).getByText("Cream + Ampoule set")).toBeInTheDocument();
  });

  it("a set without short_name falls back to its full name", () => {
    const { short_name: _, ...set } = catalog.set_offers[0];
    expect(setLabel(set)).toBe("Hydra Barrier Cream + Deep Hydration Ampoule set");
    expect(setLabel(catalog.set_offers[0])).toBe("Cream + Ampoule set");
  });

  it("disables Post to chat for an unverified draft in the expanded row", async () => {
    snap = snapshot({
      groups: [group({ group_id: "g_x", status: "needs_review", answer_id: "ans_x", canonical_question: "Can I use it while pregnant?" })],
      answers: { ans_x: answer({ answer_id: "ans_x", verified: false, verify_errors: ["no citation"] }) },
    });
    render(<Operator sessionId="ses_op_unverified" />);
    const desk = await screen.findByTestId("op-question-desk");
    fireEvent.click(await within(desk).findByText("Can I use it while pregnant?", { selector: "span" }));
    expect(within(desk).getByRole("button", { name: "Post to chat" })).toBeDisabled();
    expect(within(desk).getByText("Unverified draft: no citation")).toBeInTheDocument();
    expect(within(desk).getByRole("button", { name: "Edit reply" })).toBeEnabled();
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

describe("verifier no-answers (D-306)", () => {
  it("shows the count and the most common cause, off the host's screen", () => {
    const st = { ...reduceSnapshot(snapshot(), "operator", T0), verifyHealth: { no_answer: 3, by: { http_504: 2, client_timeout: 1 } } };
    const card = systemCards(st, catalog, T0).find((c) => c.kind === "ai_delay");
    expect(card?.text).toBe("No AI answer: 3 · AI service busy");
    expect(card?.key).toBe("verify:3"); // a new failure shows the card again after a dismiss
    const none = { ...st, verifyHealth: { no_answer: 0, by: {} } };
    expect(systemCards(none, catalog, T0).some((c) => c.kind === "ai_delay")).toBe(false);
  });
});
