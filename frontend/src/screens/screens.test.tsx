import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { catalog, snapshot } from "../test/fixtures";
import type { FeedState } from "../app/types";
import { setLang } from "../app/i18n";
import { Hub } from "./Hub";
import { Studio } from "./Studio";

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

const responses: Record<string, unknown> = {
  "/api/health": { status: "ok", demo_tools_enabled: true, viewer_input_enabled: false },
  "/api/catalog": catalog,
  "/api/demo/script": {
    steps: [{ index: 3, scene: "S02", who: "Host", action: "host_line", text: "Hi everyone, welcome to DAON LAB live!", arg: null, expected: "" }],
  },
};

// the demo show's feed: chatter and bursts B1-B5 (D-337: a release show has none, and its buttons are hidden)
const burst = (burst_id: string) => ({ burst_id, scene: "S01", description: "", anchor: "trigger", count: 3 });
let demoFeed: FeedState = { pool_running: false, pool_available: true, armed: [], fired: [],
  bursts: ["B1_price", "B2_oily", "B3_sensitive", "B4_timesale", "B5_switch"].map(burst) };

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const path = url.split("?")[0];
      const body = path.endsWith("/state") ? snapshot({ feed: demoFeed }) : responses[path] ?? (path.endsWith("/releases") ? [] : {});
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("screens", () => {
  it("D-230: the Studio's panes load the session's own catalog (an onboarded product's show)", async () => {
    render(<Studio sessionId="ses_rel" />);
    await screen.findByRole("button", { name: "Host" });
    await waitFor(() =>
      expect((fetch as unknown as { mock: { calls: string[][] } }).mock.calls.map((c) => c[0])).toContain(
        "/api/catalog?session=ses_rel",
      ),
    );
  });

  it("Studio renders the default preset, the demo console, and toggles recording mode", async () => {
    render(<Studio sessionId="ses_000001" />);
    expect(await screen.findByRole("button", { name: "Host", pressed: true })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Operator", pressed: true })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Viewer", pressed: false })).toBeInTheDocument();
    expect(screen.queryByText("Host screen")).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Demo console/ })).toBeInTheDocument();
    act(() => {
      fireEvent.keyDown(window, { key: "r" });
    });
    expect(screen.queryByRole("button", { name: "Viewer" })).not.toBeInTheDocument(); // recording mode hides the chrome
    act(() => {
      fireEvent.keyDown(window, { key: "R" });
    });
    fireEvent.click(screen.getByRole("button", { name: "Viewer" }));
    expect(screen.getByRole("region", { name: "Viewer" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Operator" }));
    expect(screen.queryByRole("region", { name: "Operator" })).not.toBeInTheDocument();
  });

  it("Studio: the splitter between two screens moves their edge (arrow keys, 5%)", async () => {
    render(<Studio sessionId="ses_000001" />);
    const split = await screen.findByTestId("studio-split-0");
    const host = () => screen.getByRole("region", { name: "Host" }).style.flexGrow;
    const before = Number(host());
    fireEvent.keyDown(split, { key: "ArrowRight" });
    expect(Number(host())).toBeGreaterThan(before);
    fireEvent.doubleClick(split);
    expect(Number(host())).toBe(50);
  });

  it("Studio has one link back to the hub, in its header; the panes have none", async () => {
    render(<Studio sessionId="ses_000001" />);
    const links = await screen.findAllByTestId("hub-link");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "/?session=ses_000001");
    expect(screen.getAllByTestId("settings-button")).toHaveLength(1);
  });

  it("Demo console (D): a host line, a viewer comment and a pasted batch take the show's normal path", async () => {
    for (const k of ["transcripts", "demo/comments"]) responses[`/api/sessions/ses_000001/${k}`] = { ok: true };
    try {
      render(<Studio sessionId="ses_000001" />);
      fireEvent.click(await screen.findByRole("button", { name: /Demo console/ }));
      fireEvent.change(screen.getByTestId("console-line"), { target: { value: "It cures acne." } });
      fireEvent.click(screen.getByTestId("console-inject"));
      fireEvent.change(screen.getByTestId("console-comment"), { target: { value: "How much is it?" } });
      fireEvent.click(await screen.findByTestId("console-post"));
      fireEvent.change(screen.getByTestId("console-comments"), { target: { value: "Mina: Is it vegan?\nDoes it sting?" } });
      fireEvent.click(await screen.findByTestId("console-burst"));
      const calls = (fetch as unknown as { mock: { calls: [string, RequestInit?][] } }).mock.calls;
      const body = (url: string) => calls.filter(([u]) => u === url).map(([, init]) => JSON.parse(String(init?.body)));
      await waitFor(() => expect(body("/api/sessions/ses_000001/demo/comments")).toHaveLength(3));
      expect(body("/api/sessions/ses_000001/transcripts")).toEqual([{ text: "It cures acne." }]);
      expect(body("/api/sessions/ses_000001/demo/comments")).toEqual([{ author: "Viewer", text: "How much is it?" },
        { author: "Mina", text: "Is it vegan?" }, { author: "Viewer", text: "Does it sting?" }]);
    } finally {
      for (const k of ["transcripts", "demo/comments"]) delete responses[`/api/sessions/ses_000001/${k}`];
    }
  });

  it("Demo console: Write with AI fills the host script; nothing is injected until a line's Inject", async () => {
    responses["/api/sessions/ses_000001/demo/generate"] = { lines: ["Welcome back, everyone.", "This cream is S$36 today."] };
    try {
      render(<Studio sessionId="ses_000001" />);
      fireEvent.click(await screen.findByRole("button", { name: /Demo console/ }));
      fireEvent.change(screen.getByTestId("console-ai-instruction-host"), { target: { value: "one price line" } });
      fireEvent.click(screen.getByTestId("console-ai-host"));
      expect(await screen.findByTestId("console-line-2")).toBeInTheDocument();
      expect(screen.getByTestId("console-script")).toHaveValue("Welcome back, everyone.\nThis cream is S$36 today.");
      const calls = (fetch as unknown as { mock: { calls: [string, RequestInit?][] } }).mock.calls;
      const sent = calls.filter(([u]) => u === "/api/sessions/ses_000001/demo/generate").map(([, i]) => JSON.parse(String(i?.body)));
      expect(sent).toEqual([{ kind: "host", count: 10, instruction: "one price line" }]);
      expect(calls.some(([u]) => u === "/api/sessions/ses_000001/transcripts")).toBe(false);
    } finally {
      delete responses["/api/sessions/ses_000001/demo/generate"];
    }
  });

  it("Hub links every screen", async () => {
    render(<Hub sessionId="ses_000001" />);
    for (const name of ["Onboard", "Pick products", "Host screen", "Operator", "Viewer", "Summary"]) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
    expect(screen.queryByText("New demo session")).toBeNull();
    expect(screen.getByText(/ses_000001/)).toBeInTheDocument();
  });

  it("D-264/D-315: Hub starts a show from a product card approved earlier", async () => {
    responses["/api/products/releases"] = [{ release_id: "rel_lumen_v2", product_name: "Night Serum", brand: "Lumen",
      category: "skincare", markets: ["SG"], approved_at: 1790000000000, version: 2, brief: "done" }];
    responses["/api/sessions"] = { session_id: "ses_rel" };
    try {
      render(<Hub sessionId="ses_000001" />);
      const open = await screen.findByTestId("hub-releases-open");
      expect(open).toHaveTextContent("Approved products1");  // the count badge
      expect(open).toHaveAttribute("aria-expanded", "false");
      expect(screen.queryByTestId("hub-releases")).toBeNull();  // D-319: the rows are in a popover
      fireEvent.click(open);
      expect(open).toHaveAttribute("aria-expanded", "true");
      const card = await screen.findByTestId("hub-release-rel_lumen_v2");
      expect(document.activeElement).toBe(card);  // focus moves into the panel
      expect(card).toHaveTextContent("Lumen");
      expect(card).toHaveTextContent("Night Serum");
      expect(card).toHaveTextContent("SG");
      expect(card).toHaveAttribute("aria-pressed", "false");
      expect(screen.queryByTestId("hub-release-start")).toBeNull();  // picking only; no start button
      fireEvent.click(card);
      expect(card).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByTestId("hub-lineup")).toHaveTextContent("1. Night Serum");
      fireEvent.click(screen.getByTestId("hub-card-host"));  // a During-the-show card starts the show
      await waitFor(() => expect(window.location.search).toContain("session=ses_rel"));
      expect(window.location.pathname).toBe("/host");
    } finally {
      delete responses["/api/products/releases"];
      delete responses["/api/sessions"];
    }
  });

  it("D-279/D-315: Hub builds the line-up in the order picked, at most 3, and can remove or clear", async () => {
    const row = (id: string, name: string) => ({ release_id: id, product_name: name, brand: "Lumen", category: "skincare",
      markets: ["SG"], approved_at: 1790000000000, version: 1, brief: "done" });
    responses["/api/products/releases"] = [row("rel_a", "Serum"), row("rel_b", "Ampoule"), row("rel_c", "Cream"),
      row("rel_d", "Toner")];
    responses["/api/sessions"] = { session_id: "ses_show" };
    try {
      render(<Hub sessionId="ses_000001" />);
      fireEvent.click(await screen.findByTestId("hub-releases-open"));
      for (const id of ["rel_c", "rel_a", "rel_b"]) fireEvent.click(await screen.findByTestId(`hub-release-${id}`));
      expect(screen.getByTestId("hub-lineup")).toHaveTextContent("1. Cream→ 2. Serum→ 3. Ampoule");
      expect(screen.getByTestId("hub-release-rel_d")).toBeDisabled();  // max 3
      fireEvent.click(screen.getByRole("button", { name: "Remove Serum" }));
      expect(screen.getByTestId("hub-lineup")).toHaveTextContent("1. Cream→ 2. Ampoule");
      fireEvent.click(screen.getByTestId("hub-card-operator"));  // a During-the-show card starts the show
      await waitFor(() => expect(window.location.search).toContain("session=ses_show"));
      const calls = (fetch as unknown as { mock: { calls: [string, RequestInit?][] } }).mock.calls;
      const body = calls.filter(([u]) => u === "/api/sessions").map(([, init]) => JSON.parse(String(init?.body)));
      expect(body.at(-1)).toEqual({ release_ids: ["rel_c", "rel_b"] });
      fireEvent.click(screen.getByTestId("hub-lineup-clear"));
      expect(screen.getByTestId("hub-lineup")).toHaveTextContent("No product picked yet.");
    } finally {
      delete responses["/api/products/releases"];
      delete responses["/api/sessions"];
    }
  });

  it("D-319: the approved-products popover closes on Escape and on an outside click, focus back on its button", async () => {
    responses["/api/products/releases"] = [{ release_id: "rel_a", product_name: "Serum", brand: "Lumen",
      category: "skincare", markets: ["SG"], approved_at: 1790000000000, version: 1, brief: "done" }];
    try {
      render(<Hub sessionId="ses_000001" />);
      const open = await screen.findByTestId("hub-releases-open");
      expect(open).toHaveAttribute("aria-controls", "hub-releases");
      fireEvent.click(open);
      expect(screen.getByRole("dialog")).toHaveAttribute("id", "hub-releases");
      fireEvent.keyDown(document, { key: "Escape" });
      expect(screen.queryByRole("dialog")).toBeNull();
      expect(document.activeElement).toBe(open);
      fireEvent.click(open);
      fireEvent.pointerDown(screen.getByTestId("hub-release-rel_a"));  // inside: stays open
      expect(screen.getByRole("dialog")).toBeInTheDocument();
      fireEvent.pointerDown(document.body);
      expect(screen.queryByRole("dialog")).toBeNull();
    } finally {
      delete responses["/api/products/releases"];
    }
  });

  it("Hub points at Pick products when a During-the-show card is pressed with no show and no product", () => {
    window.history.pushState({}, "", "/");
    render(<Hub sessionId={null} />);
    expect(screen.queryByTestId("hub-pick-nudge")).toBeNull();
    fireEvent.click(screen.getByTestId("hub-card-host"));
    expect(window.location.pathname).toBe("/");
    expect(screen.getByTestId("hub-pick-nudge")).toHaveTextContent("Pick the show's products here first.");
  });

  it("Hub shows the screens in the order of a show, under their phase, each card one link", () => {
    render(<Hub sessionId="ses_000001" />);
    const phases = screen.getAllByRole("region");
    expect(phases.map((r) => r.getAttribute("aria-label"))).toEqual(["Before the show", "During the show", "After the show"]);
    expect(within(phases[1]).getAllByRole("link").map((a) => a.dataset.testid))
      .toEqual(["hub-card-host", "hub-card-operator", "hub-card-viewer", "hub-card-studio"]);
    const host = screen.getByTestId("hub-card-host");
    expect(host).toHaveAttribute("href", expect.stringContaining("/host"));
    expect(host).toHaveTextContent("For the host");
    expect(host).toHaveTextContent("Prompter, instant correction alerts and viewer questions to read out.");
    expect(document.querySelector("[role=tooltip]")).toBeNull();
  });

  it("Hub follows the UI language chosen in the Settings gear", () => {
    setLang("ko");
    try {
      render(<Hub sessionId="ses_000001" />);
      expect(screen.getByText("방송 허브")).toBeInTheDocument();
      expect(screen.getByTestId("hub-card-studio")).toHaveTextContent("통합 화면");
      expect(screen.getByTestId("hub-card-operator")).toHaveTextContent("운영자 화면");
      expect(screen.getByText("세션 ses_000001")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "설정" })).toBeInTheDocument();
    } finally {
      setLang("en");
    }
  });
});
