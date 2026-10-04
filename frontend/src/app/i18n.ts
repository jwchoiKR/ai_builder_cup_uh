// UI language (D-109): screen labels only. What the host says on air (say-instead lines, suggested
// answers, product facts, promo text) stays in the broadcast language and is never passed to t().
// One choice for every screen of this browser, stored in localStorage `ls.lang`; storage errors are
// ignored. English strings are the keys; a missing Korean entry falls back to English.
import { useCallback, useSyncExternalStore } from "react";

import { KO } from "./i18n.ko";

export type Lang = "en" | "ko";
export const LANG_KEY = "ls.lang";
export const LANGS: { value: Lang; label: string }[] = [
  { value: "en", label: "English" },
  { value: "ko", label: "한국어" },
];

const listeners = new Set<() => void>();
let current: Lang | null = null;

function read(): Lang {
  try {
    return window.localStorage.getItem(LANG_KEY) === "ko" ? "ko" : "en";
  } catch {
    return "en";
  }
}

export function getLang(): Lang {
  if (current === null) current = read();
  return current;
}

export function setLang(lang: Lang): void {
  current = lang;
  try {
    window.localStorage.setItem(LANG_KEY, lang);
  } catch {
    // not remembered; the screen still switches
  }
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // another tab or pane changed the language
  const onStorage = (e: StorageEvent) => {
    if (e.key === LANG_KEY) {
      current = read();
      listener();
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

export function useLang(): Lang {
  return useSyncExternalStore(subscribe, getLang, () => "en");
}

export type Translate = (en: string, vars?: Record<string, string | number>) => string;

/** t("{n} required points left", { n: 2 }) -> "필수 포인트 2개 남음" in Korean. */
export function translate(lang: Lang, en: string, vars?: Record<string, string | number>): string {
  const text = lang === "ko" ? (KO[en] ?? en) : en;
  return vars ? text.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m)) : text;
}

export function useT(): Translate {
  const lang = useLang();
  return useCallback((en, vars) => translate(lang, en, vars), [lang]);
}
