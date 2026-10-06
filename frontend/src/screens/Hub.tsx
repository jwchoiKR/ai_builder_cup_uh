import { ChartColumn, ChevronRight, FileUp, Headset, Mic, Smartphone, type LucideIcon } from "lucide-react";
import { useEffect, useState, type CSSProperties, type MouseEvent } from "react";

import { api } from "../app/api";
import { useLang, useT } from "../app/i18n";
import { navigate, withSession, type ScreenProps } from "../app/nav";
import { useHealth } from "../app/store";
import { useTheme } from "../app/theme";
import { Button, SettingsButton } from "../components";
import { BRIEF_RUNNING_NOTE, onboardingApi, type ReleaseRow } from "./onboarding/onboardingApi";
import styles from "./screens.module.css";

interface Screen {
  path: string;
  title: string;
  icon: LucideIcon;
  who: string;
  text: string;
}

// The screens in the order of a show; Studio (all of them side by side, for the demo) is the hero button.
const PHASES: { label: string; live?: boolean; screens: Screen[] }[] = [
  {
    label: "Before the show",
    screens: [{ path: "/setup", title: "Setup", icon: FileUp, who: "For the operator",
      text: "Upload product documents. The AI drafts the host's talking points." }],
  },
  {
    label: "During the show",
    live: true,
    screens: [
      { path: "/host", title: "Host screen", icon: Mic, who: "For the host",
        text: "Prompter, instant correction alerts and viewer questions to read out." },
      { path: "/operator", title: "Operator", icon: Headset, who: "For the operator",
        text: "Show schedule, product switch and the question desk." },
      { path: "/viewer", title: "Viewer", icon: Smartphone, who: "What viewers see",
        text: "Live video, product strip and chat with checked AI answers." },
    ],
  },
  {
    label: "After the show",
    screens: [{ path: "/summary", title: "Summary", icon: ChartColumn, who: "For the team",
      text: "Alerts, corrections, answered questions and an AI recap." }],
  },
];

const LEAD = "An AI assistant beside the live host. It checks what the host says, answers viewer questions from the "
  + "product documents and cues the next move.";

/** In-app navigation for a plain left click; a modified click opens a new tab as usual. */
const go = (href: string) => (e: MouseEvent) => {
  if (e.metaKey || e.ctrlKey || e.shiftKey) return;
  e.preventDefault();
  navigate(href);
};

/** D-264: start a show from a product approved earlier (the list survives a cold start, D-263). */
function ReleasePicker() {
  const t = useT();
  const [rows, setRows] = useState<ReleaseRow[] | null>(null);
  const [picked, setPicked] = useState("");
  const [more, setMore] = useState<string[]>([]);  // D-279: up to 2 more products, in the order ticked
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    onboardingApi.releases().then((r) => {
      setRows(r);
      setPicked((p) => p || (r[0]?.release_id ?? ""));
    }, () => setRows([]));
  }, []);
  // D-266: while a brief runs, look again every few seconds
  const running = rows?.some((r) => r.brief === "running") ?? false;
  useEffect(() => {
    if (!running) return;
    const timer = window.setTimeout(() => onboardingApi.releases().then(setRows, () => undefined), 4000);
    return () => window.clearTimeout(timer);
  }, [rows, running]);
  if (!rows?.length) return null;
  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const s = await onboardingApi.startShow([picked, ...more.filter((id) => id !== picked)]);
      navigate(`/studio?session=${encodeURIComponent(s.session_id)}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className={styles.hubStudio} data-testid="hub-releases">
      <label className={styles.hubStudioNote}>
        {t("Previously approved products")}{" "}
        <select value={picked} onChange={(e) => setPicked(e.target.value)} data-testid="hub-release-select">
          {rows.map((r) => (
            <option key={r.release_id} value={r.release_id}>
              {r.brand} · {r.product_name} (v{r.version}{r.markets.length ? `, ${r.markets.join("/")}` : ""},{" "}
              {new Date(r.approved_at).toLocaleDateString()}){r.brief === "done" ? "" : ` · brief ${r.brief}`}
            </option>
          ))}
        </select>
      </label>
      {rows.length > 1 && (
        <span className={styles.hubStudioNote} data-testid="hub-release-more">
          {t("Then")}{" "}
          {rows.filter((r) => r.release_id !== picked).map((r) => {
            const at = more.indexOf(r.release_id);
            return (
              <label key={r.release_id}>
                <input type="checkbox" checked={at >= 0} disabled={at < 0 && more.length >= 2}
                  onChange={() => setMore((m) => (at >= 0 ? m.filter((x) => x !== r.release_id) : [...m, r.release_id]))}
                  data-testid={`hub-release-more-${r.release_id}`} />
                {at >= 0 ? `${at + 2}. ` : ""}{r.product_name}{" "}
              </label>
            );
          })}
        </span>
      )}
      <Button disabled={busy || !picked} onClick={start} data-testid="hub-release-start">
        {t("Start a show")}
      </Button>
      {rows.find((r) => r.release_id === picked)?.brief === "running" && (
        <span className={styles.hubStudioNote} data-testid="hub-brief-running">{t(BRIEF_RUNNING_NOTE)}</span>
      )}
      {error && <span className={styles.error}>{error}</span>}
    </div>
  );
}

export function Hub({ sessionId, onSessionChange }: ScreenProps) {
  const [theme, , setTheme, themePref] = useTheme();
  const t = useT();
  const lang = useLang();
  const health = useHealth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const demoTools = health?.demo_tools_enabled ?? false;
  const studio = withSession("/studio", sessionId);

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
    <div className={styles.root} data-theme={theme} lang={lang}>
      <header className={`${styles.header} ${styles.hubHeader}`}>
        <div className={styles.hubBrand}>
          <span className="eyebrow">LIVE / STUDIO</span>
          <div className={styles.hubBrandLine}>
            <h1 className={styles.hubTitle}>{t("Broadcast hub")}</h1>
            <span className={`${styles.subtitle} tabular`}>{t("Session {id}", { id: sessionId ?? "…" })}</span>
          </div>
        </div>
        <div className={styles.headerActions}>
          <Button variant="primary" disabled={busy} onClick={() => run(() => api.createSession())}>
            {t("New demo session")}
          </Button>
          <Button
            disabled={busy || !demoTools}
            title={demoTools ? undefined : t("Demo tools are disabled")}
            onClick={() => run(() => api.demoReset())}
          >
            {t("Reset demo")}
          </Button>
          <SettingsButton themePref={themePref} onTheme={setTheme} />
        </div>
      </header>
      <main className={`${styles.body} ${styles.hubBody}`}>
        <div className={styles.hubContent}>
          {error && <p className={styles.error}>{error}</p>}
          <section className={styles.hubHero}>
            <p className={styles.hubLead}>{t(LEAD)}</p>
            <div className={styles.hubStudio}>
              <a className={styles.hubStudioButton} href={studio} onClick={go(studio)} data-testid="hub-open-studio">
                {t("Open Studio (demo) →")}
              </a>
              <span className={styles.hubStudioNote}>{t("Host, operator and viewer side by side, with prepared demo scenes.")}</span>
              <a className={styles.hubStudioButton} href="/testdrive" onClick={go("/testdrive")} data-testid="hub-testdrive">
                {t("Try it with a sample product →")}
              </a>
              <a className={styles.hubStudioNote} href="/onboarding" onClick={go("/onboarding")} data-testid="hub-onboarding">
                {t("Onboard a new product →")}
              </a>
            </div>
            <ReleasePicker />
          </section>
          <div className={styles.hubPhases}>
            {PHASES.map((phase, i) => (
              <div key={phase.label} className={styles.hubPhaseSlot} data-phase={i}>
                {i > 0 && <ChevronRight className={styles.hubChevron} aria-hidden />}
                <section className={`${styles.hubPhase} ${phase.live ? styles.hubPhaseLive : ""}`} aria-label={t(phase.label)}>
                  <h2 className={styles.hubPhaseLabel}>{t(phase.label)}</h2>
                  <div className={styles.hubPhaseCards} style={{ "--cards": phase.screens.length } as CSSProperties}>
                    {phase.screens.map((s) => {
                      const href = withSession(s.path, sessionId);
                      const Icon = s.icon;
                      return (
                        <a key={s.path} className={styles.hubCard} href={href} onClick={go(href)}
                          data-testid={`hub-card-${s.path.slice(1)}`}>
                          <span className={styles.hubIcon}>
                            <Icon aria-hidden />
                          </span>
                          <span className={styles.hubCardTitle}>{t(s.title)}</span>
                          <span className={styles.hubWho}>{t(s.who)}</span>
                          <span className={styles.hubText}>{t(s.text)}</span>
                        </a>
                      );
                    })}
                  </div>
                </section>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
