import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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
  it("transcript chips: rule, answered question, covered points, switch cue", () => {
    const st = {
      ...reduceSnapshot(
        snapshot({ alerts: [alert({ transcript_id: "tr_1" })], groups: [group()] }),
        "operator",
        T0,
      ),
      agentCalls: [
        {
          call_id: "c1", agent: "utterance_judge", model: "m", prompt_version: "v", started_at: T0, latency_ms: 900, status: "ok" as const,
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
      if (path === "/api/catalog") out = catalog;
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
  it("shows the escalated compliance card as Not corrected", async () => {
    snap = snapshot({ alerts: [alert({ escalated_at: T0 + 10_000 })] });
    render(<Operator sessionId="ses_op_escalated" />);
    const card = await screen.findByTestId("op-alert-al_000001");
    expect(card).toHaveAttribute("data-state", "escalated");
    expect(within(card).getByText(/^Not corrected · /)).toBeInTheDocument();
    expect(within(card).getByText("The host is seeing a full-screen correction prompt.")).toBeInTheDocument();
    expect(within(card).getByText("Send correction cue")).toBeInTheDocument();
    expect(within(card).getByText("Dismiss false alert")).toBeInTheDocument();
    expect(screen.getByText("Live control room")).toBeInTheDocument();
    expect(screen.getByText("BROADCAST WORKSPACE")).toBeInTheDocument();
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

  it("disables Approve for an unverified draft in the expanded row", async () => {
    snap = snapshot({
      groups: [group({ group_id: "g_x", status: "needs_review", answer_id: "ans_x", canonical_question: "Can I use it while pregnant?" })],
      answers: { ans_x: answer({ answer_id: "ans_x", verified: false, verify_errors: ["no citation"] }) },
    });
    render(<Operator sessionId="ses_op_unverified" />);
    const desk = await screen.findByTestId("op-question-desk");
    fireEvent.click(await within(desk).findByText("Can I use it while pregnant?", { selector: "span" }));
    expect(within(desk).getByRole("button", { name: "Approve" })).toBeDisabled();
    expect(within(desk).getByText("Unverified draft: no citation")).toBeInTheDocument();
    expect(within(desk).getByRole("button", { name: "Edit reply" })).toBeEnabled();
  });
});
