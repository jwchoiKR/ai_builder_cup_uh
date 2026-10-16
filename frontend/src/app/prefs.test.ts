import { afterEach, describe, expect, it, vi } from "vitest";

import { clampSplit, COLS_MAX, HOST_LAYOUT_DEFAULT, splitAt, SPLIT_MAX, SPLIT_MIN, stepSplit } from "./prefs";

afterEach(() => {
  window.localStorage.clear();
  vi.resetModules();
});

describe("host panel sizes (D-181)", () => {
  it("the drag math puts the split where the pointer is, in the middle of the gap", () => {
    // a 1000 px container with a 20 px gap: the panels share 980 px
    expect(splitAt(10 + 490 + 10, 10, 1000, 20)).toBe(0.5);
    expect(splitAt(10 + 588 + 10, 10, 1000, 20)).toBe(0.6);
  });

  it("every panel keeps at least 25% of its axis", () => {
    expect(splitAt(0, 0, 1000, 20)).toBe(SPLIT_MIN);
    expect(splitAt(5000, 0, 1000, 20)).toBe(SPLIT_MAX);
    expect(clampSplit(0.1)).toBe(0.25);
    expect(clampSplit(0.9)).toBe(0.75);
  });

  it("arrow keys move 5%, Home and End go to the limits, other keys do nothing", () => {
    expect(stepSplit(0.58, "ArrowRight")).toBe(0.63);
    expect(stepSplit(0.58, "ArrowLeft")).toBe(0.53);
    expect(stepSplit(0.5, "ArrowDown")).toBe(0.55);
    expect(stepSplit(0.27, "ArrowUp")).toBe(0.25);
    expect(stepSplit(0.5, "Home")).toBe(0.25);
    expect(stepSplit(0.5, "End")).toBe(0.75);
    expect(stepSplit(0.5, "Enter")).toBeNull();
  });

  it("the sizes are saved in one key and restored on load; a bad value falls back to the default", async () => {
    let prefs = await import("./prefs");
    prefs.setHostLayout({ cols: 0.7 });
    expect(JSON.parse(window.localStorage.getItem("ls.layout.host")!)).toEqual({ cols: 0.7, rows: 0.5 });
    vi.resetModules();
    prefs = await import("./prefs");
    expect(prefs.getHostLayout()).toEqual({ cols: 0.7, rows: 0.5 });
    prefs.resetHostLayout();
    expect(window.localStorage.getItem("ls.layout.host")).toBeNull();
    window.localStorage.setItem("ls.layout.host", "{not json");
    vi.resetModules();
    prefs = await import("./prefs");
    expect(prefs.getHostLayout()).toEqual(HOST_LAYOUT_DEFAULT);
    window.localStorage.setItem("ls.layout.host", JSON.stringify({ cols: 0.05, rows: 0.99 }));
    vi.resetModules();
    prefs = await import("./prefs");
    expect(prefs.getHostLayout()).toEqual({ cols: 0.25, rows: 0.75 }); // clamped
  });

  it("D-182: the chat keeps at least 30% of the width", async () => {
    expect(stepSplit(0.68, "ArrowRight", SPLIT_MIN, COLS_MAX)).toBe(0.7);
    expect(stepSplit(0.5, "End", SPLIT_MIN, COLS_MAX)).toBe(0.7);
    expect(splitAt(990, 0, 1000, 20, SPLIT_MIN, COLS_MAX)).toBe(0.7);
    window.localStorage.setItem("ls.layout.host", JSON.stringify({ cols: 0.75, rows: 0.75 }));
    vi.resetModules();
    const prefs = await import("./prefs");
    expect(prefs.getHostLayout()).toEqual({ cols: 0.7, rows: 0.75 });
    prefs.setHostLayout({ cols: 0.9 });
    expect(prefs.getHostLayout().cols).toBe(0.7);
  });
});

describe("the mic's speech-recognition language (D-316)", () => {
  it("D-348/D-497: offers English to everyone, with no labs gating; a stored Korean choice falls back to none", async () => {
    window.localStorage.setItem("ls.mic.lang", "ko-KR");
    const prefs = await import("./prefs");
    expect(prefs.STT_LANGUAGES.map((l) => [l.code, l.name])).toEqual([["en-US", "English (en-US)"]]);
    expect(prefs.getMicLang()).toBe("");
  });

  it("defaults to none (the server's language), remembers a listed code and ignores an unlisted one", async () => {
    let prefs = await import("./prefs");
    expect(prefs.getMicLang()).toBe("");
    prefs.setMicLang("en-US");
    expect(window.localStorage.getItem("ls.mic.lang")).toBe("en-US");
    vi.resetModules();
    prefs = await import("./prefs");
    expect(prefs.getMicLang()).toBe("en-US");
    for (const gone of ["xx-YY", "ja-JP", "auto", "ko-KR"]) {  // D-348: the other languages are no longer offered
      window.localStorage.setItem("ls.mic.lang", gone);
      vi.resetModules();
      prefs = await import("./prefs");
      expect(prefs.getMicLang()).toBe("");
    }
  });
});

describe("the mic's WebSocket URL (D-316/D-318)", () => {
  it("sends ?lang= only for a picked language, none by default or for Session default", async () => {
    const url = async () => (await import("./mic")).audioUrl("ses_1");
    expect(await url()).toMatch(/\/api\/sessions\/ses_1\/audio$/);  // default: no choice
    const prefs = await import("./prefs");
    prefs.setMicLang("en-US");
    expect(await url()).toMatch(/\/audio\?lang=en-US$/);
    prefs.setMicLang("");  // Session default
    expect(await url()).toMatch(/\/audio$/);
  });
});
