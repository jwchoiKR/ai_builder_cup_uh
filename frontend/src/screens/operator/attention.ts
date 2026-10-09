// Quiet attention for the operator: a small dot, no sound, no toast. A control that leads to a list gets a dot when
// something new joined that list while the operator was looking elsewhere; the dot clears when the list is viewed.
import { useEffect, useRef, useState } from "react";

/** True from the moment an id appears that was not there when the list was first seen (state loaded), while the list
 * is not `viewing`, until it is viewed. What is already there when the page loads never raises the dot. */
export function useArrivalDot(ids: string[], loaded: boolean, viewing: boolean): boolean {
  const seen = useRef<Set<string> | null>(null);
  const [dot, setDot] = useState(false);
  const key = ids.join("|");
  useEffect(() => {
    if (!loaded) return;
    if (seen.current === null) {
      seen.current = new Set(ids);
      return;
    }
    let fresh = false;
    for (const id of ids) {
      if (!seen.current.has(id)) {
        seen.current.add(id);
        fresh = true;
      }
    }
    if (fresh && !viewing) setDot(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, loaded, viewing]);
  useEffect(() => {
    if (viewing) setDot(false);
  }, [viewing]);
  return dot && !viewing;
}

/** A disclosure's open state, remembered in localStorage (closed by default). A storage error is ignored. */
export function useStoredOpen(key: string, initial = false): [boolean, () => void] {
  const [open, setOpen] = useState<boolean>(() => {
    try {
      const v = window.localStorage.getItem(key);
      return v === null ? initial : v === "1";
    } catch {
      return initial;
    }
  });
  const toggle = () =>
    setOpen((cur) => {
      const next = !cur;
      try {
        window.localStorage.setItem(key, next ? "1" : "0");
      } catch {
        // not remembered
      }
      return next;
    });
  return [open, toggle];
}

/** The URL switch for developer-only panels: `?debug=1`. */
export function debugOn(): boolean {
  try {
    return new URLSearchParams(window.location.search).get("debug") === "1";
  } catch {
    return false;
  }
}
