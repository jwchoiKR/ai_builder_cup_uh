import { useState } from "react";

import { api } from "../app/api";
import { navigate, withSession, type ScreenProps } from "../app/nav";
import { useHealth } from "../app/store";
import { useTheme } from "../app/theme";
import { Button, Card, Eyebrow, ThemeToggle } from "../components";
import styles from "./screens.module.css";

const SCREENS: { path: string; title: string; text: string }[] = [
  { path: "/studio", title: "Studio", text: "Host, operator and viewer side by side, with the Demo Console. Used for recording." },
  { path: "/host", title: "Host screen", text: "Prompter, audience questions, live chat, cues and full-screen compliance alerts." },
  { path: "/operator", title: "Operator", text: "Live control room: question desk, alerts, run of show, cues, banners and notices." },
  { path: "/viewer", title: "Viewer", text: "Phone layout: video, product strip, chat with AI, host and brand answers." },
  { path: "/setup", title: "Setup", text: "Product documents, Brief Agent and glossary confirmation." },
  { path: "/summary", title: "Summary", text: "Post-broadcast numbers, logs and the AI-written recap." },
];

export function Hub({ sessionId, onSessionChange }: ScreenProps) {
  const [theme, toggle] = useTheme("hub");
  const health = useHealth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const demoTools = health?.demo_tools_enabled ?? false;

  const run = async (fn: () => Promise<{ session_id: string }>) => {
    setBusy(true);
    setError(null);
    try {
      const s = await fn();
      onSessionChange?.(s.session_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={styles.root} data-theme={theme}>
      <header className={styles.header}>
        <div className={styles.headerTitle}>
          <Eyebrow>LIVE / Studio</Eyebrow>
          <span className={styles.title}>Broadcast hub</span>
          <span className={`${styles.subtitle} tabular`}>Session {sessionId ?? "…"}</span>
        </div>
        <div className={styles.headerActions}>
          <Button variant="primary" disabled={busy} onClick={() => run(() => api.createSession())}>
            New demo session
          </Button>
          <Button
            disabled={busy || !demoTools}
            title={demoTools ? undefined : "Demo tools are disabled"}
            onClick={() => run(() => api.demoReset())}
          >
            Reset demo
          </Button>
          <ThemeToggle theme={theme} onToggle={toggle} />
        </div>
      </header>
      <main className={styles.body}>
        {error && <p className={styles.error}>{error}</p>}
        <div className={styles.grid}>
          {SCREENS.map((s) => {
            const href = withSession(s.path, sessionId);
            return (
              <Card key={s.path}>
                <a
                  className={styles.linkCard}
                  href={href}
                  onClick={(e) => {
                    if (e.metaKey || e.ctrlKey || e.shiftKey) return;
                    e.preventDefault();
                    navigate(href);
                  }}
                >
                  <span className={styles.linkCardTitle}>{s.title}</span>
                  <span className={styles.muted}>{s.text}</span>
                </a>
              </Card>
            );
          })}
        </div>
      </main>
    </div>
  );
}
