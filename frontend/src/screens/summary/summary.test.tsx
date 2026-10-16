import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { exportSummaryJson } from "./exportJson";
import { printSummary } from "./exportPdf";
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
          typed: true, // D-439: a typed demo line
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

describe("SummaryView: back to the hub", () => {
  it("links to the hub with its session and offers the Settings gear", () => {
    renderView(data(), { onSetTheme: vi.fn(), themePref: "system" });
    expect(screen.getByTestId("hub-link").getAttribute("href")).toMatch(/^\/\?session=/);
    expect(screen.getByTestId("settings-button")).toBeInTheDocument();
  });
});

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
    expect(within(log).getByText("1.6 s (typed)")).toBeInTheDocument(); // alert latency; D-439: a typed line is marked
    expect(within(log).getByText("8.0 s")).toBeInTheDocument(); // corrected in
    expect(within(log).getByText("1:10")).toBeInTheDocument(); // time from start
    expect(screen.getByTestId("summary-facts")).toHaveTextContent("S$36.00");
    // D-096: both logs in one box, with the same columns
    const logs = screen.getByTestId("summary-logs");
    expect(within(logs).getByTestId("summary-compliance")).toBeInTheDocument();
    expect(within(logs).getByTestId("summary-facts")).toBeInTheDocument();
    const headers = (id: string) => [...screen.getByTestId(id).querySelectorAll("th")].map((th) => th.textContent);
    expect(headers("summary-facts")).toEqual([...headers("summary-compliance").slice(0, 2), "Field", ...headers("summary-compliance").slice(3)]);
    expect(within(screen.getByTestId("summary-promos")).getByText("Running at end")).toBeInTheDocument();
    expect(within(screen.getByTestId("summary-agents")).getByText("Utterance judge")).toBeInTheDocument();
    expect(screen.getByText("Do you ship to Malaysia?")).toBeInTheDocument();
  });

  it("shows the AI recap first, labelled, with its parts (D-092)", () => {
    renderView(data());
    const recap = screen.getByTestId("summary-recap");
    const sections = screen.getByTestId("summary").querySelectorAll("section");
    expect(sections[0]).toBe(recap); // executive summary before the totals and logs
    expect(within(recap).getByText("AI-written recap based on the numbers below")).toBeInTheDocument();
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
    const onExportPdf = vi.fn();
    const onBack = vi.fn();
    renderView(data(), { onExport, onExportPdf, onBack });
    fireEvent.click(screen.getByRole("button", { name: "Export PDF" }));
    fireEvent.click(screen.getByRole("button", { name: "Export JSON" }));
    fireEvent.click(screen.getByRole("button", { name: "Back to hub" }));
    expect(onExportPdf).toHaveBeenCalledOnce();
    expect(onExport).toHaveBeenCalledOnce();
    expect(onBack).toHaveBeenCalledOnce();
  });

  it("waits for the recap before the PDF report (D-097)", () => {
    renderView(data({ status: "computing", recap: null }), { onExportPdf: vi.fn() });
    expect(screen.getByRole("button", { name: "Export PDF" })).toBeDisabled();
  });

  it("D-493: a loading bar while the recap is written, gone once it is ready", () => {
    const { unmount } = renderView(data({ status: "computing", recap: null }));
    const bar = screen.getByRole("progressbar", { name: "Writing the recap" });
    expect(bar).not.toHaveAttribute("aria-valuenow");  // no made-up percentage
    unmount();
    renderView(data());
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("prints the report with its title as the file name and restores the page title", () => {
    const listeners: Record<string, () => void> = {};
    const win = {
      document: { title: "LIVE / Studio" },
      print: vi.fn(),
      addEventListener: (type: string, fn: () => void) => (listeners[type] = fn),
      removeEventListener: vi.fn(),
    } as unknown as Window;
    const title = printSummary(data(), win);
    expect(win.print).toHaveBeenCalledOnce();
    expect(win.document.title).toBe(title);
    expect(title).toMatch(/broadcast summary/);
    listeners.afterprint();
    expect(win.document.title).toBe("LIVE / Studio");
  });
});

describe("exportSummaryJson", () => {
  it("shows what viewers asked: topics, outcomes, waits, buying questions and gaps in the product information", () => {
    const d = data();
    d.comment_insights = {
      source: "firestore", topic_source: "analysis", comments: 30, viewers: 14, askers: 11, questions: 20, reactions: 8, hidden: 2,
      stream_reports: 1,
      timeline: { bin_sec: 60, bins: [{ start_sec: 0, comments: 4, questions: 2, product: "Hydra Barrier Cream" }, { start_sec: 60, comments: 9, questions: 7, product: "Hydra Barrier Cream" }], peak: { start_sec: 60, comments: 9, questions: 7, product: "Hydra Barrier Cream" } },
      reply_time_sec: { auto: { n: 12, p50: 4.2, p95: 9.8 }, person: { n: 5, p50: 31, p95: 70.5 } },
      buying: { questions: 13, topics: ["Price and offers", "Shipping and delivery"], unanswered: 2 },
      not_in_product_information: { questions: 3, examples: ["Do you ship to Malaysia?"] },
      outcomes: { auto_answered: 12, answered_by_person: 5, unanswered: 3 },
      waited_for_a_person_by_reason: { health: 4, outside: 3 },
      question_languages: { en: 17, ko: 3 },
      topics: [
        { label: "Price and offers", buying: true, questions: 10, askers: 8, auto_answered: 10, answered_by_person: 0, unanswered: 0, examples: ["how much ah"], products: [] },
        { label: "Use during pregnancy", buying: false, questions: 4, askers: 4, auto_answered: 0, answered_by_person: 4, unanswered: 0, examples: ["im pregnant, ok?"], products: [] },
      ],
      notes: ["Viewers asked about use during pregnancy, which the team answered by hand."],
    };
    renderView(d);
    const card = screen.getByTestId("summary-insights");
    expect(within(card).getByTestId("summary-insights-outcomes")).toHaveTextContent(
      "20 questions: 12 answered automatically (60%), 5 answered by the host or the team (25%), 3 left unanswered (15%).");
    const facts = within(card).getByTestId("summary-insights-facts");
    expect(facts).toHaveTextContent("14 wrote, 11 asked a question");
    expect(facts).toHaveTextContent("4.2 s (95%: 9.8 s, 12 replies)");
    expect(facts).toHaveTextContent("13 asked, 2 left unanswered");
    const rows = within(card).getAllByTestId("summary-insights-topic");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("Price and offers · buying");
    expect(rows[1]).not.toHaveTextContent("buying");
    expect(within(card).getByTestId("summary-insights-peak")).toHaveTextContent("Most questions: 1:00 to 2:00 (7 questions), while Hydra Barrier Cream was on air.");
    expect(within(card).getByTestId("summary-insights-timeline").querySelectorAll('[title^="0:00"], [title^="1:00"]')).toHaveLength(2);
    expect(within(card).getByTestId("summary-insights-gaps")).toHaveTextContent("Do you ship to Malaysia?");
    expect(within(card).getByTestId("summary-insights-reasons")).toHaveTextContent("Health or safety 4 · Order, delivery or shop 3");
    expect(within(card).getByTestId("summary-insights-notes")).toHaveTextContent("answered by hand");
    expect(within(card).getByTestId("summary-insights-source")).toHaveTextContent("Topics: sorted by AI after the broadcast.");
  });

  it("shows no such card for a summary without the analysis", () => {
    renderView(data());
    expect(screen.queryByTestId("summary-insights")).not.toBeInTheDocument();
  });

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
