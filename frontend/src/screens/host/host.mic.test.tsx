import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MicSnapshot } from "../../app/mic";
import { reduceSnapshot } from "../../app/state";
import { catalog, session, snapshot } from "../../test/fixtures";
import { HostView, type HostActions } from "./HostScreen";

let micState: MicSnapshot["state"] = "off";

vi.mock("../../app/mic", async (orig) => ({
  ...(await orig<typeof import("../../app/mic")>()),
  useMic: () => ({ state: micState, level: 0.5, message: null, start: vi.fn(), stop: vi.fn(), toggle: vi.fn() }),
}));

const actions: HostActions = { rendered: vi.fn(), undoSwitch: vi.fn(), dismissPd: vi.fn(), pullQuestion: vi.fn(), extendSegment: vi.fn() };

function show(over = {}) {
  const state = { ...reduceSnapshot(snapshot(over), "host", Date.now()), serverOffsetMs: 0 };
  render(<HostView state={state} catalog={catalog} connection="connected" theme="dark" actions={actions} />);
  return screen.getByTestId("host-mic");
}

afterEach(cleanup);

describe("host mic control", () => {
  it("says what to do when the show is live and the mic is off, with an accent", () => {
    micState = "off";
    const mic = show();
    expect(mic).toHaveTextContent("Mic off · click or press M");
    expect(mic.className).toMatch(/micPrompt/);
    expect(mic).toHaveAttribute("aria-pressed", "false");
  });

  it("stays quiet before the broadcast starts", () => {
    micState = "off";
    const mic = show({ session: session({ status: "ready", started_at: null }), segments: [] });
    expect(mic).toHaveTextContent(/^mic off$/);
    expect(mic.className).not.toMatch(/micPrompt/);
  });

  it("shows the level while listening", () => {
    micState = "listening";
    const mic = show();
    expect(mic).toHaveTextContent(/^mic$/);
    expect(mic.className).not.toMatch(/micPrompt/);
    expect(mic.querySelector("span[aria-hidden]")).not.toBeNull(); // the level bar
    expect(mic).toHaveAttribute("aria-pressed", "true");
  });
});
