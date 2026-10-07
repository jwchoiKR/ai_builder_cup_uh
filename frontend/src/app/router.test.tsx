import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

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

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("D-315: a show lost to a server restart", () => {
  it("says the show ended, without the raw error, and drops the stale id", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      const gone = url.includes("ses_old");
      const body = gone ? { error: { code: "session_not_found", message: "session ses_old not found" } }
        : url.startsWith("/api/demo/current") ? { session_id: "ses_new" } : {};
      return new Response(JSON.stringify(body), { status: gone ? 404 : 200, headers: { "Content-Type": "application/json" } });
    }));
    window.history.replaceState(null, "", "/host?session=ses_old");
    render(<App />);
    expect(await screen.findByTestId("session-ended")).toHaveTextContent("This show ended (server restarted).");
    expect(screen.queryByText(/ses_old not found/)).toBeNull();
    fireEvent.click(screen.getByTestId("session-ended-new"));
    await waitFor(() => expect(window.location.search).toBe(""));
    expect(window.location.pathname).toBe("/host");
    expect(screen.queryByTestId("session-ended")).toBeNull();
  });
});
