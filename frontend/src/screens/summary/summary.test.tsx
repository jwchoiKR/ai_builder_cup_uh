import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { exportSummaryJson } from "./exportJson";
import { formatDuration, formatMsAsSeconds } from "./format";
import { SummaryView } from "./SummaryView";
import type { SummaryData } from "./types";

const START = 1_790_000_000_000;

function data(over: Partial<SummaryData> = {}): SummaryData {
  return {
    status: "ready",
    error: null,
    recap: {
      headline: "The 203-second session handled 41 comments.",
      highlights: ["All 3 required points were covered for Hydra Barrier Cream."],
      watch_outs: ["One HIGH alert."],
      follow_ups: ["Reply to the 3 unanswered question groups."],
    },
    stats: {
      title: "DAON LAB · Skincare session",
      session_id: "ses_000001",
      started_at: START,
      ended_at: START + 203_000,
      duration_sec: 203,
      products: [
        {
          product_id: "cream_hydra_barrier",
          name: "Hydra Barrier Cream",
          duration_sec: 166,
          planned_duration_sec: 900,
          required_points_covered: 3,
          required_points_total: 3,
          missing_points: [],
          comments: 30,
          questions: 24,
          groups: 9,
          answered_groups: { ai_answer: 4, host_answer: 1, brand_answer: 1 },
          unanswered_groups: [{ group_id: "g1", canonical_question: "Can I use it under makeup?", unique_askers: 4 }],
        },
        {
          product_id: "ampoule_deep_hydration",
          name: "Deep Hydration Ampoule",
          duration_sec: 37,
          planned_duration_sec: 600,
          required_points_covered: 1,
          required_points_total: 3,
          missing_points: [{ point_id: "am-p3", text: "Instant hydration: +45% right after one use (in-house test)." }],
          comments: 11,
          questions: 10,
          groups: 6,
          answered_groups: { ai_answer: 2, host_answer: 0, brand_answer: 0 },
          unanswered_groups: [],
        },
      ],
      totals: {
        comments: 41,
        questions: 34,
        hidden_comments: 3,
        groups: 16,
        messages_by_kind: { ai_answer: 9 },
        analysed_comments: 41,
      },
      general_unanswered_groups: [{ group_id: "g9", canonical_question: "Do you ship to Malaysia?", unique_askers: 1 }],
      compliance_alerts: [
        {
          alert_id: "al_1",
          rule_id: "ASEAN-3-SKIN-AGEING",
          rule_title: "Prevents, reduces or reverses physiological changes of ageing",
          severity: "HIGH",
          span: "your wrinkles will disappear overnight",
          shown_at: START + 70_000,
          speech_end_to_shown_ms: 1640,
          shown_to_corrected_ms: 8000,
          corrected_text: "Let me correct that.",
          unverified: false,
        },
      ],
      fact_alerts: [
        { alert_id: "fx_1", field: "price", stated_value: "S$32", correct_value: "S$36.00", corrected: true, time_to_correction_ms: 8000 },
      ],
      promos: [{ promo_id: "promo_time_sale_10", title: "Time sale: extra 10% off", started_at: START + 120_000, ended_at: null, duration_sec: 83 }],
      agent_latency: { utterance_judge: { p50_ms: 1380, p95_ms: 1650, calls: 15 } },
      cache: { instant_answers: 7, composed_answers: 9, triage_hits: 2, triage_misses: 30 },
    },
    ...over,
  };
}

function renderView(d: SummaryData, extra: Partial<Parameters<typeof SummaryView>[0]> = {}) {
  return render(<SummaryView data={d} theme="light" onExport={() => {}} onBack={() => {}} {...extra} />);
}

afterEach(() => vi.restoreAllMocks());

describe("SummaryView", () => {
  it("renders the computed numbers", () => {
    renderView(data());
    expect(screen.getByText("DAON LAB · Skincare session")).toBeInTheDocument();
    expect(screen.getByText("41")).toBeInTheDocument(); // total comments
    const cream = screen.getByTestId("summary-product-cream_hydra_barrier");
    expect(within(cream).getByText("3 / 3 covered")).toBeInTheDocument();
    expect(within(cream).getByText("Can I use it under makeup?")).toBeInTheDocument();
    const ampoule = screen.getByTestId("summary-product-ampoule_deep_hydration");
    expect(within(ampoule).getByText(/Instant hydration/)).toBeInTheDocument();
    const log = screen.getByTestId("summary-compliance");
    expect(within(log).getByText("1.6 s")).toBeInTheDocument(); // alert latency
    expect(within(log).getByText("8.0 s")).toBeInTheDocument(); // corrected in
    expect(within(log).getByText("1:10")).toBeInTheDocument(); // time from start
    expect(within(screen.getByTestId("summary-facts")).getByText("S$36.00")).toBeInTheDocument();
    expect(within(screen.getByTestId("summary-promos")).getByText("Running at end")).toBeInTheDocument();
    expect(within(screen.getByTestId("summary-agents")).getByText("Utterance judge")).toBeInTheDocument();
    expect(screen.getByText("Do you ship to Malaysia?")).toBeInTheDocument();
  });

  it("labels the AI recap and shows its parts", () => {
    renderView(data());
    const recap = screen.getByTestId("summary-recap");
    expect(within(recap).getByText("AI-written recap based on the numbers above")).toBeInTheDocument();
    expect(within(recap).getByText("The 203-second session handled 41 comments.")).toBeInTheDocument();
    expect(within(recap).getByText("Watch-outs")).toBeInTheDocument();
  });

  it("shows the statistics without a recap when the recap failed", () => {
    renderView(data({ status: "failed", recap: null, error: "recap unavailable (timeout)" }));
    const recap = screen.getByTestId("summary-recap");
    expect(within(recap).getByText(/Recap unavailable/)).toBeInTheDocument();
    expect(screen.getByText("41")).toBeInTheDocument();
  });

  it("calls export and back", () => {
    const onExport = vi.fn();
    const onBack = vi.fn();
    renderView(data(), { onExport, onBack });
    fireEvent.click(screen.getByRole("button", { name: "Export JSON" }));
    fireEvent.click(screen.getByRole("button", { name: "Back to hub" }));
    expect(onExport).toHaveBeenCalledOnce();
    expect(onBack).toHaveBeenCalledOnce();
  });
});

describe("exportSummaryJson", () => {
  it("downloads the stats and recap as JSON", async () => {
    let blob: Blob | null = null;
    vi.spyOn(URL, "createObjectURL").mockImplementation((b) => {
      blob = b as Blob;
      return "blob:summary";
    });
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const name = exportSummaryJson(data());
    expect(name).toBe("summary-ses_000001.json");
    expect(click).toHaveBeenCalledOnce();
    const parsed = JSON.parse(await (blob as unknown as Blob).text());
    expect(parsed.stats.totals.comments).toBe(41);
    expect(parsed.recap.headline).toContain("41 comments");
  });
});

describe("format", () => {
  it("formats durations and seconds", () => {
    expect(formatDuration(203)).toBe("3:23");
    expect(formatDuration(3725)).toBe("1:02:05");
    expect(formatMsAsSeconds(1640)).toBe("1.6 s");
    expect(formatMsAsSeconds(null)).toBe("–");
  });
});
