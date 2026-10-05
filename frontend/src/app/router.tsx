// Pathname routes (DEV_SPEC §12.1). Session from ?session=<sid>, else GET /api/demo/current.
import { useCallback, useEffect, useState, type ComponentType } from "react";

import { Host } from "../screens/Host";
import { Hub } from "../screens/Hub";
import { Onboarding } from "../screens/Onboarding";
import { TestDrive } from "../screens/TestDrive";
import { Operator } from "../screens/Operator";
import { Setup } from "../screens/Setup";
import { Studio } from "../screens/Studio";
import { Summary } from "../screens/Summary";
import { Viewer } from "../screens/Viewer";
import { api } from "./api";
import { navigate, useLocation, withSession, type ScreenProps } from "./nav";

export { navigate, useLocation, withSession, type ScreenProps };

export const ROUTES: Record<string, ComponentType<ScreenProps>> = {
  "/": Hub,
  "/studio": Studio,
  "/host": Host,
  "/operator": Operator,
  "/viewer": Viewer,
  "/setup": Setup,
  "/summary": Summary,
  "/onboarding": Onboarding,
  "/testdrive": TestDrive,
};

export function useSessionId(): {
  sessionId: string | null;
  loading: boolean;
  error: string | null;
  setSessionId: (sid: string) => void;
} {
  const { pathname, search } = useLocation();
  const fromUrl = new URLSearchParams(search).get("session");
  const [current, setCurrent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (fromUrl) return;
    let cancelled = false;
    api.demoCurrent().then(
      (s) => !cancelled && setCurrent(s.session_id),
      (e) => !cancelled && setError(e instanceof Error ? e.message : String(e)),
    );
    return () => {
      cancelled = true;
    };
  }, [fromUrl]);

  const setSessionId = useCallback((sid: string) => navigate(withSession(pathname, sid)), [pathname]);
  const sessionId = fromUrl ?? current;
  return { sessionId, loading: !sessionId && !error, error, setSessionId };
}

export function App() {
  const { pathname } = useLocation();
  const { sessionId, setSessionId } = useSessionId();
  const Screen = ROUTES[pathname.replace(/\/+$/, "") || "/"] ?? Hub;
  return <Screen sessionId={sessionId} onSessionChange={setSessionId} />;
}
