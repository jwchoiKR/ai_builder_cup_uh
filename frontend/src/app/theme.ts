// Theme (DEV_SPEC §12.1, §12.2). D-180: one choice for every screen of this browser, like the UI language
// (D-109): localStorage `ls.theme` holds "light" or "dark", and no value means "follow the system". A change on
// one screen applies to every screen and Studio pane at once, and to other tabs through the storage event. The
// old per-screen keys `ls.theme.<screen>` are ignored. Storage errors are ignored (the choice lasts in memory).
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";

export type ThemeName = "light" | "dark";
export type ThemePref = ThemeName | "system";
export type ScreenKey = "hub" | "studio" | "host" | "operator" | "viewer" | "setup" | "summary";
export const THEME_KEY = "ls.theme";

const listeners = new Set<() => void>();
let current: ThemeName | null | undefined; // undefined: not read yet

export function readStoredTheme(storage?: Storage | null): ThemeName | null {
  try {
    const store = storage === undefined ? window.localStorage : storage;
    const v = store?.getItem(THEME_KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null;
  }
}

/** Stores a theme, or removes it for "system" (every screen then follows the OS again). */
export function writeStoredTheme(theme: ThemePref, storage?: Storage | null): boolean {
  try {
    const store = storage === undefined ? window.localStorage : storage;
    if (theme === "system") store?.removeItem(THEME_KEY);
    else store?.setItem(THEME_KEY, theme);
    return true;
  } catch {
    return false;
  }
}

function getStored(): ThemeName | null {
  if (current === undefined) current = readStoredTheme();
  return current;
}

export function setTheme(theme: ThemePref): void {
  writeStoredTheme(theme);
  current = theme === "system" ? null : theme;
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // another tab changed the theme
  const onStorage = (e: StorageEvent) => {
    if (e.key === THEME_KEY) {
      current = readStoredTheme();
      listener();
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

export function systemPrefersDark(): boolean {
  try {
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
  } catch {
    return false;
  }
}

export function resolveTheme(stored: ThemeName | null, prefersDark: boolean): ThemeName {
  return stored ?? (prefersDark ? "dark" : "light");
}

/** [theme, toggle, set, pref]. Every screen follows prefers-color-scheme until the user picks a theme anywhere;
 *  set("system") goes back to that. `pref` is what the Settings menu shows. */
export function useTheme(): [ThemeName, () => void, (t: ThemePref) => void, ThemePref] {
  const stored = useSyncExternalStore(subscribe, getStored, () => null);
  const [prefersDark, setPrefersDark] = useState(systemPrefersDark);

  useEffect(() => {
    let mq: MediaQueryList | null = null;
    try {
      mq = window.matchMedia?.("(prefers-color-scheme: dark)") ?? null;
    } catch {
      mq = null;
    }
    if (!mq) return;
    const on = (e: MediaQueryListEvent) => setPrefersDark(e.matches);
    mq.addEventListener?.("change", on);
    return () => mq?.removeEventListener?.("change", on);
  }, []);

  const theme = resolveTheme(stored, prefersDark);
  const toggle = useCallback(() => setTheme(theme === "dark" ? "light" : "dark"), [theme]);
  return [theme, toggle, setTheme, stored ?? "system"];
}
