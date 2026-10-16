// UI text (D-109). D-494 (user: "remove the Korean features everywhere"): the UI is English only. Call sites keep t() so a
// template like "{n} required points left" fills in its values; what the host says on air is never passed to it.

export type Translate = (en: string, vars?: Record<string, string | number>) => string;

/** translate("{n} required points left", { n: 2 }) -> "2 required points left". */
export function translate(en: string, vars?: Record<string, string | number>): string {
  return vars ? en.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m)) : en;
}

export function useT(): Translate {
  return translate;
}
