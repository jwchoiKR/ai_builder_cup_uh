import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { THEME_DEFAULTS, readStoredTheme, resolveTheme, storageKey, useTheme, writeStoredTheme } from "./theme";

const throwing = {
  getItem: () => {
    throw new Error("blocked");
  },
  setItem: () => {
    throw new Error("blocked");
  },
} as unknown as Storage;

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("theme storage", () => {
  it("falls back to the default when localStorage throws", () => {
    expect(readStoredTheme("host", throwing)).toBeNull();
    expect(writeStoredTheme("host", "light", throwing)).toBe(false);
    expect(resolveTheme("host", readStoredTheme("host", throwing), false)).toBe("dark");
  });

  it("uses per-screen defaults and the system preference for hub/setup/summary", () => {
    expect(THEME_DEFAULTS.host).toBe("dark");
    expect(resolveTheme("operator", null, true)).toBe("light");
    expect(resolveTheme("hub", null, true)).toBe("dark");
    expect(resolveTheme("summary", null, false)).toBe("light");
    expect(resolveTheme("hub", "light", true)).toBe("light");
  });

  it("stores the choice under ls.theme.<screen>", () => {
    writeStoredTheme("viewer", "dark");
    expect(window.localStorage.getItem(storageKey("viewer"))).toBe("dark");
    expect(readStoredTheme("viewer")).toBe("dark");
  });

  it("useTheme toggles and survives a throwing localStorage", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const { result } = renderHook(() => useTheme("host"));
    expect(result.current[0]).toBe("dark");
    act(() => result.current[1]());
    expect(result.current[0]).toBe("light");
  });
});
