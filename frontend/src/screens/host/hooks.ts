// Small host-screen hooks: layout scale, FLIP moves, exit fades, corrected toast.
import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";

import type { Alert } from "../../app/types";

/** The host screen is designed for 1920x1080; inside a Studio pane or on a 1280x720 monitor every
 * size scales with the root box (CSS variable --hs). */
export function useHostScale(ref: RefObject<HTMLElement | null>, min = 0.42): number {
  const [scale, setScale] = useState(1);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const w = el.clientWidth;
      const h = el.clientHeight;
      if (!w || !h) return;
      setScale(Math.max(min, Math.min(1, w / 1920, h / 1080)));
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref, min]);
  return scale;
}

/** FLIP: rows keyed by data-flip-key slide from their old position in 200 ms (§12.3.4). */
export function useFlip(container: RefObject<HTMLElement | null>, deps: unknown[]): void {
  const last = useRef(new Map<string, number>());
  useLayoutEffect(() => {
    const root = container.current;
    if (!root) return;
    const next = new Map<string, number>();
    const rows = Array.from(root.querySelectorAll<HTMLElement>("[data-flip-key]"));
    for (const row of rows) {
      const key = row.dataset.flipKey!;
      const top = row.getBoundingClientRect().top;
      next.set(key, top);
      const before = last.current.get(key);
      if (before !== undefined && before !== top && typeof row.animate === "function") {
        row.animate([{ transform: `translateY(${before - top}px)` }, { transform: "translateY(0)" }], {
          duration: 200,
          easing: "ease-out",
        });
      }
    }
    last.current = next;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

/** Keeps removed items for `ms` with leaving=true so they can fade out. */
export function usePresence<T>(items: T[], keyOf: (item: T) => string, ms = 200): { item: T; leaving: boolean }[] {
  const [leaving, setLeaving] = useState<Map<string, T>>(new Map());
  const prev = useRef<Map<string, T>>(new Map());
  const keys = items.map(keyOf).join("|");

  useEffect(() => {
    const now = new Map(items.map((i) => [keyOf(i), i] as const));
    const gone = [...prev.current.entries()].filter(([k]) => !now.has(k));
    prev.current = now;
    if (!gone.length) return;
    setLeaving((m) => {
      const out = new Map(m);
      for (const [k, v] of gone) out.set(k, v);
      return out;
    });
    const t = setTimeout(() => {
      setLeaving((m) => {
        const out = new Map(m);
        for (const [k] of gone) out.delete(k);
        return out;
      });
    }, ms);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [keys, ms]);

  const present = items.map((item) => ({ item, leaving: false }));
  const current = new Set(items.map(keyOf));
  const exiting = [...leaving.entries()].filter(([k]) => !current.has(k)).map(([, item]) => ({ item, leaving: true }));
  return [...present, ...exiting];
}

/** The green "Corrected" bar: shown for `toastMs` when this client saw a compliance alert go from
 * active to corrected. A dismiss closes the overlay without it (§12.3.7). */
export function useCorrectedToast(alerts: Record<string, Alert>, toastMs: number): Alert | null {
  const seen = useRef<Map<string, Alert["status"]>>(new Map());
  const [toast, setToast] = useState<{ alert: Alert; until: number } | null>(null);

  useEffect(() => {
    let fresh: Alert | null = null;
    for (const a of Object.values(alerts)) {
      if (a.kind !== "compliance") continue;
      const before = seen.current.get(a.alert_id);
      if (before === "active" && a.status === "corrected") fresh = a;
      seen.current.set(a.alert_id, a.status);
    }
    if (fresh) setToast({ alert: fresh, until: Date.now() + toastMs });
  }, [alerts, toastMs]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), Math.max(0, toast.until - Date.now()));
    return () => clearTimeout(t);
  }, [toast]);

  return toast?.alert ?? null;
}
