import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { catalog, snapshot } from "../test/fixtures";
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

  it("Hub links every screen", async () => {
    render(<Hub sessionId="ses_000001" />);
    for (const name of ["Host screen", "Operator", "Viewer", "Setup", "Summary"]) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
    expect(screen.getByTestId("hub-open-studio")).toHaveAttribute("href", expect.stringContaining("/studio"));
    expect(screen.getByText("New demo session")).toBeInTheDocument();
    expect(screen.getByText(/ses_000001/)).toBeInTheDocument();
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
});
