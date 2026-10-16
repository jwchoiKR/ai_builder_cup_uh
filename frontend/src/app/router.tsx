// Pathname routes (DEV_SPEC §12.1). The session is ?session=<sid>; the hub's Pick products starts one.
import { useCallback, useEffect, useRef, useState, type ComponentType } from "react";

import { Host } from "../screens/Host";
import { Hub } from "../screens/Hub";
import { Onboarding } from "../screens/Onboarding";
import { Operator } from "../screens/Operator";
import { Studio } from "../screens/Studio";
import { Summary } from "../screens/Summary";
import { Viewer } from "../screens/Viewer";
import { Button, PanelBoundary } from "../components";
import styles from "../screens/screens.module.css";
import { onStaleSession } from "./api";
import { useT } from "./i18n";
import { navigate, useLocation, withSession, type ScreenProps } from "./nav";
import { useTheme } from "./theme";

export { navigate, useLocation, withSession, type ScreenProps };

export const ROUTES: Record<string, ComponentType<ScreenProps>> = {
  "/": Hub,
  "/studio": Studio,
  "/host": Host,
  "/operator": Operator,
  "/viewer": Viewer,
  "/summary": Summary,
  "/onboarding": Onboarding,
};

export function useSessionId(): { sessionId: string | null; setSessionId: (sid: string) => void } {
  const { pathname, search } = useLocation();
  const sessionId = new URLSearchParams(search).get("session");
  const setSessionId = useCallback((sid: string) => navigate(withSession(pathname, sid)), [pathname]);
  return { sessionId, setSessionId };
}

/** D-315: the show in the URL is gone (the server restarted). No raw error: say so, and send the user to the hub. */
function SessionEnded({ onNew }: { onNew: () => void }) {
  const t = useT();
  const [theme] = useTheme();
  return (
    <div className={styles.root} data-theme={theme} lang="en">
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
  const { sessionId, setSessionId } = useSessionId();
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
    // drop the stale id: the hub's Pick products starts a new show
    const onNew = () => {
      setEnded(false);
      navigate("/", true);
    };
    return <SessionEnded onNew={onNew} />;
  }
  return (
    <PanelBoundary name={pathname}>
      <Screen sessionId={sessionId} onSessionChange={setSessionId} />
    </PanelBoundary>
  );
}
