import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { catalog, snapshot } from "../test/fixtures";
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

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const path = url.split("?")[0];
      const body = path.endsWith("/state") ? snapshot({ feed: { pool_running: false, armed: [], fired: [], bursts: [] } }) : responses[path] ?? {};
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
    await screen.findByText("Host + Operator");
    await waitFor(() =>
      expect((fetch as unknown as { mock: { calls: string[][] } }).mock.calls.map((c) => c[0])).toContain(
        "/api/catalog?session=ses_rel",
      ),
    );
  });

  it("Studio renders the default preset, toggles recording mode and the demo console", async () => {
    render(<Studio sessionId="ses_000001" />);
    expect(await screen.findByText("Host + Operator")).toBeInTheDocument();
    expect(screen.getAllByText("Host screen").length).toBeGreaterThan(0);
    const handle = await screen.findByRole("button", { name: /Demo console/ });
    fireEvent.click(handle);
    expect(await screen.findByText("B1 Price questions")).toBeInTheDocument();
    expect(await screen.findByText("Hi everyone, welcome to DAON LAB live!")).toBeInTheDocument();
    expect(screen.getByText("Arm B5 Switch boundary")).toBeInTheDocument();
    act(() => {
      fireEvent.keyDown(window, { key: "r" });
    });
    expect(screen.queryByText("Host + Operator")).not.toBeInTheDocument(); // recording mode hides the chrome
    expect(screen.queryByRole("button", { name: /Demo console/ })).not.toBeInTheDocument();
    act(() => {
      fireEvent.keyDown(window, { key: "R" });
    });
    fireEvent.click(screen.getByText("All three"));
    expect(screen.getAllByText("Viewer").length).toBeGreaterThan(0);
  });

  it("the open demo console resizes by keyboard, remembers its height, and survives a throwing storage", async () => {
    window.localStorage.removeItem("ls.console.height");
    const { unmount } = render(<Studio sessionId="ses_000001" />);
    fireEvent.click(await screen.findByRole("button", { name: /Demo console/ }));
    const grip = await screen.findByTestId("console-grip");
    fireEvent.keyDown(grip, { key: "ArrowUp" });
    const saved = Number(window.localStorage.getItem("ls.console.height"));
    expect(saved).toBeGreaterThanOrEqual(120);
    expect(grip.parentElement).toHaveStyle({ height: `${saved}px` });
    // collapsing leaves only the thin bar
    fireEvent.click(screen.getByRole("button", { name: /Demo console/ }));
    expect(screen.queryByTestId("console-grip")).toBeNull();
    unmount();

    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    render(<Studio sessionId="ses_000001" />);
    fireEvent.click(await screen.findByRole("button", { name: /Demo console/ }));
    fireEvent.keyDown(await screen.findByTestId("console-grip"), { key: "ArrowDown" });
    expect(screen.getByTestId("console-grip")).toBeInTheDocument();
    vi.restoreAllMocks();
  });

  it("Studio has one link back to the hub, in its header; the panes have none", async () => {
    render(<Studio sessionId="ses_000001" />);
    const links = await screen.findAllByTestId("hub-link");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "/?session=ses_000001");
    expect(screen.getAllByTestId("settings-button")).toHaveLength(1);
  });

  it("Hub links every screen", async () => {
    render(<Hub sessionId="ses_000001" />);
    for (const name of ["Host screen", "Operator", "Viewer", "Setup", "Summary"]) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
    expect(screen.getByTestId("hub-open-studio")).toHaveAttribute("href", expect.stringContaining("/studio"));
    expect(screen.getByText("New demo session")).toBeInTheDocument();
    expect(screen.getByText(/ses_000001/)).toBeInTheDocument();
  });

  it("D-264: Hub starts a show from a product approved earlier", async () => {
    responses["/api/onboarding/releases"] = [{ release_id: "rel_lumen_v2", product_name: "Night Serum", brand: "Lumen",
      category: "skincare", markets: ["SG"], approved_at: 1790000000000, version: 2 }];
    responses["/api/sessions"] = { session_id: "ses_rel" };
    try {
      render(<Hub sessionId="ses_000001" />);
      const select = await screen.findByTestId("hub-release-select");
      expect(select).toHaveTextContent("Lumen · Night Serum (v2, SG");
      fireEvent.click(screen.getByTestId("hub-release-start"));
      await waitFor(() => expect(window.location.search).toContain("session=ses_rel"));
      expect(window.location.pathname).toBe("/studio");
    } finally {
      delete responses["/api/onboarding/releases"];
      delete responses["/api/sessions"];
    }
  });

  it("D-279: Hub starts a show of two approved products in the order ticked", async () => {
    responses["/api/onboarding/releases"] = [
      { release_id: "rel_a_v1", product_name: "Night Cream", brand: "Lumen", category: "skincare", markets: ["SG"],
        approved_at: 1790000000000, version: 1 },
      { release_id: "rel_b_v1", product_name: "Quick Kettle", brand: "Larkmoor", category: "kitchen", markets: ["SG"],
        approved_at: 1790000000000, version: 1 }];
    responses["/api/sessions"] = { session_id: "ses_show" };
    try {
      render(<Hub sessionId="ses_000001" />);
      fireEvent.click(await screen.findByTestId("hub-release-more-rel_b_v1"));
      expect(screen.getByTestId("hub-release-more")).toHaveTextContent("2. Quick Kettle");
      fireEvent.click(screen.getByTestId("hub-release-start"));
      await waitFor(() => expect(window.location.search).toContain("session=ses_show"));
    } finally {
      delete responses["/api/onboarding/releases"];
      delete responses["/api/sessions"];
    }
  });

  it("Hub shows the screens in the order of a show, under their phase, each card one link", () => {
    render(<Hub sessionId="ses_000001" />);
    const phases = screen.getAllByRole("region");
    expect(phases.map((r) => r.getAttribute("aria-label"))).toEqual(["Before the show", "During the show", "After the show"]);
    expect(within(phases[1]).getAllByRole("link").map((a) => a.dataset.testid))
      .toEqual(["hub-card-host", "hub-card-operator", "hub-card-viewer"]);
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
      expect(screen.getByTestId("hub-open-studio")).toHaveTextContent("스튜디오 열기 (데모) →");
      expect(screen.getByTestId("hub-card-operator")).toHaveTextContent("운영자 화면");
      expect(screen.getByText("세션 ses_000001")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "설정" })).toBeInTheDocument();
    } finally {
      setLang("en");
    }
  });
});
