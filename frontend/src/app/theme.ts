// Per-screen theme state (DEV_SPEC §12.1, §12.2). Choice stored in localStorage `ls.theme.<screen>`;
// storage access is wrapped in try/catch and falls back to the default.
import { useCallback, useEffect, useState } from "react";

export type ThemeName = "light" | "dark";
export type ScreenKey = "hub" | "studio" | "host" | "operator" | "viewer" | "setup" | "summary";

export const THEME_DEFAULTS: Record<ScreenKey, ThemeName | "system"> = {
  hub: "system",
  studio: "light",
  host: "dark",
  operator: "light",
  viewer: "light",
  setup: "system",
  summary: "system",
};

export const storageKey = (screen: ScreenKey) => `ls.theme.${screen}`;

export function readStoredTheme(screen: ScreenKey, storage?: Storage | null): ThemeName | null {
  try {
    const store = storage === undefined ? window.localStorage : storage;
    const v = store?.getItem(storageKey(screen));
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null;
  }
}

export type ThemePref = ThemeName | "system";

/** Stores a theme, or removes it for "system" (the screen then follows the OS again). */
export function writeStoredTheme(screen: ScreenKey, theme: ThemePref, storage?: Storage | null): boolean {
  try {
    const store = storage === undefined ? window.localStorage : storage;
    if (theme === "system") store?.removeItem(storageKey(screen));
    else store?.setItem(storageKey(screen), theme);
    return true;
  } catch {
    return false;
  }
}

export function systemPrefersDark(): boolean {
  try {
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
  } catch {
    return false;
  }
}

export function resolveTheme(screen: ScreenKey, stored: ThemeName | null, prefersDark: boolean): ThemeName {
  if (stored) return stored;
  const d = THEME_DEFAULTS[screen];
  return d === "system" ? (prefersDark ? "dark" : "light") : d;
}

/** [theme, toggle, set, pref]. "System" screens follow prefers-color-scheme until the user picks a
 *  theme; set("system") goes back to that. `pref` is what the Settings menu shows. */
export function useTheme(screen: ScreenKey): [ThemeName, () => void, (t: ThemePref) => void, ThemePref] {
  const [stored, setStored] = useState<ThemeName | null>(() => readStoredTheme(screen));
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

  // Keep panes of the same screen in sync (e.g. the Studio host pane and a /host tab).
  useEffect(() => {
    const on = (e: StorageEvent) => {
      if (e.key === storageKey(screen)) setStored(readStoredTheme(screen));
    };
    window.addEventListener("storage", on);
    return () => window.removeEventListener("storage", on);
  }, [screen]);

  const theme = resolveTheme(screen, stored, prefersDark);
  const set = useCallback(
    (t: ThemePref) => {
      writeStoredTheme(screen, t);
      setStored(t === "system" ? null : t);
    },
    [screen],
  );
  const toggle = useCallback(() => set(theme === "dark" ? "light" : "dark"), [set, theme]);
  return [theme, toggle, set, stored ?? "system"];
}
