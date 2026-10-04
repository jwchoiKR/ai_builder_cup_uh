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

/** The green "Corrected" bar: shown for `toastMs` when this client saw a compliance alert or a fact
 * note go from active to corrected. A dismiss closes the alert without it (§12.3.7). */
export function useCorrectedToast(alerts: Record<string, Alert>, toastMs: number): Alert | null {
  const seen = useRef<Map<string, Alert["status"]>>(new Map());
  const [toast, setToast] = useState<{ alert: Alert; until: number } | null>(null);

  useEffect(() => {
    let fresh: Alert | null = null;
    for (const a of Object.values(alerts)) {
      // D-107: a corrected fact note confirms in green too, in the same box
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
