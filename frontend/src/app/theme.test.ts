import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { THEME_KEY, readStoredTheme, resolveTheme, setTheme, useTheme, writeStoredTheme } from "./theme";

const throwing = {
  getItem: () => {
    throw new Error("blocked");
  },
  setItem: () => {
    throw new Error("blocked");
  },
} as unknown as Storage;

afterEach(() => {
  act(() => setTheme("system"));
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("theme storage", () => {
  it("falls back to the system preference when localStorage throws", () => {
    expect(readStoredTheme(throwing)).toBeNull();
    expect(writeStoredTheme("light", throwing)).toBe(false);
    expect(resolveTheme(readStoredTheme(throwing), true)).toBe("dark");
  });

  it("D-180: every screen defaults to the system preference", () => {
    expect(resolveTheme(null, true)).toBe("dark");
    expect(resolveTheme(null, false)).toBe("light");
    expect(resolveTheme("light", true)).toBe("light");
  });

  it("D-180: one key for the whole browser; the old per-screen keys are ignored", () => {
    window.localStorage.setItem("ls.theme.host", "dark");
    expect(readStoredTheme()).toBeNull();
    writeStoredTheme("dark");
    expect(window.localStorage.getItem(THEME_KEY)).toBe("dark");
    writeStoredTheme("system");
    expect(window.localStorage.getItem(THEME_KEY)).toBeNull();
  });

  it("D-180: a choice on one screen applies to every screen at once", () => {
    const host = renderHook(() => useTheme());
    const viewer = renderHook(() => useTheme());
    act(() => host.result.current[2]("dark"));
    expect(viewer.result.current[0]).toBe("dark");
    expect(viewer.result.current[3]).toBe("dark");
    act(() => viewer.result.current[2]("system"));
    expect(host.result.current[3]).toBe("system");
  });

  it("follows another tab through the storage event", () => {
    const { result } = renderHook(() => useTheme());
    act(() => {
      window.localStorage.setItem(THEME_KEY, "dark");
      window.dispatchEvent(new StorageEvent("storage", { key: THEME_KEY }));
    });
    expect(result.current[0]).toBe("dark");
  });

  it("useTheme toggles and survives a throwing localStorage", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const { result } = renderHook(() => useTheme());
    const first = result.current[0];
    act(() => result.current[1]());
    expect(result.current[0]).toBe(first === "dark" ? "light" : "dark");
  });
});
