// Pathname routes (DEV_SPEC §12.1). Session from ?session=<sid>, else GET /api/demo/current.
import { useCallback, useEffect, useRef, useState, type ComponentType } from "react";

import { Host } from "../screens/Host";
import { Hub } from "../screens/Hub";
import { Onboarding } from "../screens/Onboarding";
import { TestDrive } from "../screens/TestDrive";
import { Operator } from "../screens/Operator";
import { Setup } from "../screens/Setup";
import { Studio } from "../screens/Studio";
import { Summary } from "../screens/Summary";
import { Viewer } from "../screens/Viewer";
import { Button, PanelBoundary } from "../components";
import styles from "../screens/screens.module.css";
import { api, onStaleSession, userMessage } from "./api";
import { useLang, useT } from "./i18n";
import { navigate, useLocation, withSession, type ScreenProps } from "./nav";
import { useTheme } from "./theme";

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
  refresh: () => void;
} {
  const { pathname, search } = useLocation();
  const fromUrl = new URLSearchParams(search).get("session");
  const [current, setCurrent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [epoch, setEpoch] = useState(0);  // D-315: a bump fetches /demo/current again

  useEffect(() => {
    if (fromUrl) return;
    let cancelled = false;
    api.demoCurrent().then(
      (s) => !cancelled && setCurrent(s.session_id),
      (e) => !cancelled && setError(userMessage(e)),
    );
    return () => {
      cancelled = true;
    };
  }, [fromUrl, epoch]);

  const setSessionId = useCallback((sid: string) => navigate(withSession(pathname, sid)), [pathname]);
  const refresh = useCallback(() => {
    setCurrent(null);
    setError(null);
    setEpoch((e) => e + 1);
  }, []);
  const sessionId = fromUrl ?? current;
  return { sessionId, loading: !sessionId && !error, error, setSessionId, refresh };
}

/** D-315: the show in the URL is gone (the server restarted). No raw error: say so, and start the current demo. */
function SessionEnded({ onNew }: { onNew: () => void }) {
  const t = useT();
  const lang = useLang();
  const [theme] = useTheme();
  return (
    <div className={styles.root} data-theme={theme} lang={lang}>
      <main className={styles.sessionEnded} role="alert" data-testid="session-ended">
        <h1 className={styles.hubReleasesTitle}>{t("This show is no longer available.")}</h1>
        <p className={styles.hubStudioNote}>{t("Start a new one to keep going.")}</p>
        <Button variant="primary" onClick={onNew} data-testid="session-ended-new">{t("Start a new show")}</Button>
      </main>
    </div>
  );
}

export function App() {
  const { pathname } = useLocation();
  const { sessionId, setSessionId, refresh } = useSessionId();
  const [ended, setEnded] = useState(false);
  const current = useRef(sessionId);
  current.current = sessionId;
  useEffect(() => {
    // a late 404 from a session this page has left is ignored
    onStaleSession((sid) => sid === current.current && setEnded(true));
    return () => onStaleSession(null);
  }, []);
  const Screen = ROUTES[pathname.replace(/\/+$/, "") || "/"] ?? Hub;
  if (ended) {
    // drop the stale id: without ?session the app takes /api/demo/current (the demo show, made if none is left)
    const onNew = () => {
      setEnded(false);
      navigate(pathname, true);
      refresh();
    };
    return <SessionEnded onNew={onNew} />;
  }
  return (
    <PanelBoundary name={pathname}>
      <Screen sessionId={sessionId} onSessionChange={setSessionId} />
    </PanelBoundary>
  );
}
