import { ArrowUpRight, ChartColumn, Clapperboard, FileUp, Headset, Mic, Smartphone, type LucideIcon } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

import { api } from "../app/api";
import { navigate, withSession, type ScreenProps } from "../app/nav";
import { useHealth } from "../app/store";
import { useTheme } from "../app/theme";
import { Button, Chip, Eyebrow, ThemeToggle } from "../components";
import styles from "./screens.module.css";

/** A term a visitor may not know: dotted underline, and a short tooltip on hover and on keyboard focus. */
function Term({ children, tip }: { children: ReactNode; tip: string }) {
  const id = useId();
  return (
    <span className={styles.term} tabIndex={0} aria-describedby={id}
      onKeyDown={(e) => e.key === "Escape" && e.currentTarget.blur()}>
      {children}
      <span role="tooltip" id={id} className={styles.termTip}>
        {tip}
      </span>
    </span>
  );
}

type Phase = "Before the show" | "During the show" | "After the show" | "Demo";
const PHASE_TONE = { "Before the show": "neutral", "During the show": "accent", "After the show": "neutral", Demo: "fact" } as const;

// In the order they are used: before, during and after the show, then the recording view.
const SCREENS: { path: string; title: string; icon: LucideIcon; phase: Phase; who: string; points: ReactNode[] }[] = [
  {
    path: "/setup", title: "Setup", icon: FileUp, phase: "Before the show", who: "For the operator.",
    points: [
      "Upload the product documents (PDF).",
      <>The <Term tip="An AI agent that reads the product documents and drafts the host's talking points.">Brief Agent</Term> writes the prompter points.</>,
      <>Confirm the <Term tip="Product names and ingredients given to speech recognition, so it spells them right.">glossary</Term> so speech recognition spells product words right.</>,
    ],
  },
  {
    path: "/host", title: "Host screen", icon: Mic, phase: "During the show", who: "For the host.",
    points: [
      "Prompter with the next point to say.",
      "A full-screen alert when a line breaks a rule or states a wrong fact, with the line to say instead.",
      "Viewer questions with checked answers to read out.",
    ],
  },
  {
    path: "/operator", title: "Operator", icon: Headset, phase: "During the show", who: "For the operator.",
    points: [
      "Run of show and product switch.",
      <>The <Term tip="The operator's list of viewer questions, each with its status and a draft answer when there is one.">question desk</Term>: questions the product info cannot answer, to approve or answer.</>,
      "Alerts, banners and notices.",
    ],
  },
  {
    path: "/viewer", title: "Viewer", icon: Smartphone, phase: "During the show", who: "What viewers see.",
    points: [
      "Phone layout with video and the product strip.",
      "Chat with the AI's checked answers.",
      "Host and brand replies.",
    ],
  },
  {
    path: "/studio", title: "Studio", icon: Clapperboard, phase: "Demo", who: "For recording the demo.",
    points: [
      "Host, operator and viewer screens side by side.",
      <>The <Term tip="A control panel that plays prepared scenes on cue: viewer comments, host lines and promos.">Demo Console</Term> plays prepared scenes.</>,
    ],
  },
  {
    path: "/summary", title: "Summary", icon: ChartColumn, phase: "After the show", who: "For the team.",
    points: [
      "Show numbers: alerts, corrections, answered questions.",
      "Logs.",
      "A recap written by the AI.",
    ],
  },
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
      <main className={`${styles.body} ${styles.hubBody}`}>
        {error && <p className={styles.error}>{error}</p>}
        <div className={styles.hubGrid}>
          {SCREENS.map((s) => {
            const href = withSession(s.path, sessionId);
            const Icon = s.icon;
            return (
              <article key={s.path} className={styles.hubCard} data-testid={`hub-card-${s.path.slice(1)}`}>
                <div className={styles.hubCardTop}>
                  <span className={styles.hubIcon}>
                    <Icon aria-hidden />
                  </span>
                  <Chip tone={PHASE_TONE[s.phase]}>{s.phase}</Chip>
                </div>
                <a
                  className={styles.hubCardLink}
                  href={href}
                  onClick={(e) => {
                    if (e.metaKey || e.ctrlKey || e.shiftKey) return;
                    e.preventDefault();
                    navigate(href);
                  }}
                >
                  {s.title}
                  <ArrowUpRight aria-hidden />
                </a>
                <p className={styles.hubWho}>{s.who}</p>
                <ul className={styles.hubPoints}>
                  {s.points.map((pt, i) => (
                    <li key={i}>{pt}</li>
                  ))}
                </ul>
              </article>
            );
          })}
        </div>
      </main>
    </div>
  );
}
