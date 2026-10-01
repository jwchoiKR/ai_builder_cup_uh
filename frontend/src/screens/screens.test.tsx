import { act, fireEvent, render, screen } from "@testing-library/react";
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

  it("Hub links every screen", async () => {
    render(<Hub sessionId="ses_000001" />);
    for (const name of ["Studio", "Host screen", "Operator", "Viewer", "Setup", "Summary"]) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
    expect(screen.getByText("New demo session")).toBeInTheDocument();
    expect(screen.getByText(/ses_000001/)).toBeInTheDocument();
  });
});
