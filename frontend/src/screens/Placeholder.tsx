// Temporary screen body used until the real Host / Operator / Viewer / Setup / Summary screens land.
// It shows live values from the session store so Studio works end to end.
import { useEffect, type ReactNode } from "react";

import type { ScreenProps } from "../app/nav";
import { nextProduct, onAirProduct } from "../app/selectors";
import { useCatalog, useSession } from "../app/store";
import { useTheme, type ScreenKey } from "../app/theme";
import type { Role } from "../app/types";
import { Card, ConnectionLabel, Eyebrow, ThemeToggle } from "../components";
import styles from "./screens.module.css";

export function ScreenPlaceholder({
  screen,
  role,
  title,
  props,
  children,
}: {
  screen: ScreenKey;
  role: Role;
  title: string;
  props: ScreenProps;
  children?: ReactNode;
}) {
  const [ownTheme, toggle] = useTheme();
  const theme = props.theme ?? ownTheme;
  const { state, connection, error } = useSession(props.sessionId, role);
  const catalog = useCatalog(props.sessionId);

  // Host: key T toggles the theme (§12.3.10); other screens use the header toggle.
  useEffect(() => {
    if (screen !== "host" || props.embedded) return;
    const on = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      if (e.key === "t" || e.key === "T") toggle();
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [screen, props.embedded, toggle]);

  const onAir = onAirProduct(state, catalog);
  const next = nextProduct(state, catalog);
  const stats: [string, number][] = [
    ["Comments", Object.keys(state.comments).length],
    ["Question groups", Object.keys(state.groups).length],
    ["Messages", Object.values(state.messages).filter((m) => m.state === "published").length],
    ["Alerts", Object.keys(state.alerts).length],
  ];

  return (
    <div className={styles.root} data-theme={theme}>
      <header className={styles.header}>
        <div className={styles.headerTitle}>
          <Eyebrow>LIVE / Studio</Eyebrow>
          <span className={styles.title}>{title}</span>
          <span className={styles.subtitle}>{state.session?.title ?? props.sessionId ?? "No session"}</span>
        </div>
        <div className={styles.headerActions}>
          <ConnectionLabel status={connection} />
          {!props.embedded && screen !== "host" && <ThemeToggle theme={theme} onToggle={toggle} />}
        </div>
      </header>
      <main className={styles.body}>
        {error && <p className={styles.error}>{error}</p>}
        <div className={styles.grid}>
          <Card>
            <div className={styles.stat}>
              <Eyebrow>Status</Eyebrow>
              <span className={styles.statValue}>{state.session?.status === "live" ? "LIVE" : state.session?.status === "ended" ? "Ended" : "READY"}</span>
            </div>
          </Card>
          <Card>
            <div className={styles.stat}>
              <Eyebrow>NOW</Eyebrow>
              <span>{onAir?.name ?? "—"}</span>
              <Eyebrow>NEXT</Eyebrow>
              <span>{next?.name ?? "End of run sheet"}</span>
            </div>
          </Card>
          {stats.map(([label, value]) => (
            <Card key={label}>
              <div className={styles.stat}>
                <Eyebrow>{label}</Eyebrow>
                <span className={styles.statValue}>{value}</span>
              </div>
            </Card>
          ))}
        </div>
        {children}
      </main>
    </div>
  );
}
