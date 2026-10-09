import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { catalog, snapshot } from "../test/fixtures";
import { api } from "./api";
import { App } from "./router";

class FakeEventSource {
  static CLOSED = 2;
  readyState = 1;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public url: string) {}
  addEventListener() {}
  close() {}
}

/** The server after a restart: `dead` sessions answer 404; /demo/current gives the next id of `current`. */
function server(dead: string[], current: string[]) {
  const calls: string[] = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    calls.push(url);
    const gone = dead.some((sid) => url.includes(sid));
    const body = gone ? { error: { code: "session_not_found", message: "session gone not found" } }
      : url.startsWith("/api/demo/current") ? { session_id: current.shift() }
      : url.includes("/state") ? snapshot() : url.startsWith("/api/catalog") ? catalog
      : url.startsWith("/api/health") ? { status: "ok", demo_tools_enabled: true, viewer_input_enabled: false } : {};
    return new Response(JSON.stringify(body), { status: gone ? 404 : 200, headers: { "Content-Type": "application/json" } });
  }));
  return calls;
}

// each test uses its own ids: the app's store keeps a session it has loaded
afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("D-315: a show lost to a server restart", () => {
  it("a session from the URL: says the show ended, without the raw error, and the button goes to the hub", async () => {
    server(["ses_old"], ["ses_new"]);
    window.history.replaceState(null, "", "/host?session=ses_old");
    render(<App />);
    expect(await screen.findByTestId("session-ended")).toHaveTextContent("This show is no longer available.");
    expect(screen.queryByText(/not found/)).toBeNull();
    fireEvent.click(screen.getByTestId("session-ended-new"));
    expect(window.location.search).toBe("");
    expect(window.location.pathname).toBe("/");
    expect(screen.queryByTestId("session-ended")).toBeNull();
  });

  it("a late 404 from a session the page has left changes nothing", async () => {
    const calls = server(["ses_old3"], []);
    window.history.replaceState(null, "", "/host?session=ses_new3");
    render(<App />);
    await waitFor(() => expect(calls.some((u) => u.includes("/sessions/ses_new3/"))).toBe(true));
    await expect(api.state("ses_old3", "host")).rejects.toThrow();
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByTestId("session-ended")).toBeNull();
  });

});
