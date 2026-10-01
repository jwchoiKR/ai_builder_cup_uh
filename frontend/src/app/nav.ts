// Minimal pathname navigation (no router dependency).
import { useSyncExternalStore } from "react";

import type { ThemeName } from "./theme";

/** Props every screen accepts. In Studio a pane passes its own theme and `embedded`. */
export interface ScreenProps {
  sessionId: string | null;
  theme?: ThemeName;
  embedded?: boolean;
  onSessionChange?: (sessionId: string) => void;
}

const subscribeLocation = (fn: () => void) => {
  window.addEventListener("popstate", fn);
  return () => window.removeEventListener("popstate", fn);
};

export function useLocation(): { pathname: string; search: string } {
  const pathname = useSyncExternalStore(subscribeLocation, () => window.location.pathname);
  const search = useSyncExternalStore(subscribeLocation, () => window.location.search);
  return { pathname, search };
}

export function navigate(path: string, replace = false): void {
  if (replace) window.history.replaceState(null, "", path);
  else window.history.pushState(null, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function withSession(path: string, sessionId: string | null): string {
  return sessionId ? `${path}?session=${encodeURIComponent(sessionId)}` : path;
}
