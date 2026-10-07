import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let voiceLine: { url: string; text: string; seq: number } | null = null;
vi.mock("../app/store", () => ({
  useSession: () => ({ state: { voiceLine }, connection: "connected", store: null, error: null }),
  useHealth: () => null,
}));

import { TestDriveVoice } from "./Studio";

const plays: string[] = [];
const pauses: string[] = [];
class FakeAudio {
  constructor(public src: string) {}
  play() {
    plays.push(this.src);
    return Promise.resolve();
  }
  pause() {
    pauses.push(this.src);
  }
}

beforeEach(() => {
  plays.length = 0;
  pauses.length = 0;
  window.localStorage.clear();
  vi.stubGlobal("Audio", FakeAudio);
});

afterEach(() => {
  vi.unstubAllGlobals();
  voiceLine = null;
});

const line = (seq: number) => ({ url: `/api/testdrive/audio/${String(seq).padStart(16, "0")}.wav`, text: "Hi", seq });

describe("D-320/D-322: the test drive's voice in the Studio", () => {
  it("plays each line once; a line that comes while muted is skipped, not replayed on unmute", async () => {
    voiceLine = line(1);
    const { rerender } = render(<TestDriveVoice sessionId="ses_1" />);
    await act(async () => {});
    expect(plays).toEqual([line(1).url]);
    expect(screen.getByTestId("testdrive-voice")).toHaveTextContent("AI voice (demo)");
    fireEvent.click(screen.getByTestId("testdrive-voice-mute"));  // mute
    expect(pauses).toContain(line(1).url);
    voiceLine = line(2);
    rerender(<TestDriveVoice sessionId="ses_1" />);
    fireEvent.click(screen.getByTestId("testdrive-voice-mute"));  // unmute
    await act(async () => {});
    expect(plays).toEqual([line(1).url]);  // line 2 came while muted: not played now
    voiceLine = line(3);
    rerender(<TestDriveVoice sessionId="ses_1" />);
    await act(async () => {});
    expect(plays).toEqual([line(1).url, line(3).url]);
  });
});
