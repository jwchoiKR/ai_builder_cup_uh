import { ChartColumn, ChevronDown, ChevronRight, FileUp, Headset, Loader2, Mic, Smartphone, X, type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState, type CSSProperties, type MouseEvent } from "react";

import { api, userMessage } from "../app/api";
import { useLang, useT } from "../app/i18n";
import { navigate, withSession, type ScreenProps } from "../app/nav";
import { useHealth } from "../app/store";
import { useTheme } from "../app/theme";
import { Button, Chip, SettingsButton } from "../components";
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
        text: "Live video, product strip and chat with fact-checked AI answers." },
    ],
  },
  {
    label: "After the show",
    screens: [{ path: "/summary", title: "Summary", icon: ChartColumn, who: "For the team",
      text: "Alerts, corrections, answered questions and an AI recap." }],
  },
];

const MAX_SHOW = 3;  // D-279: a show of up to 3 products

const LEAD = "An AI assistant beside the live host. It checks what the host says, answers viewer questions from the "
  + "product documents and cues the next move.";

/** In-app navigation for a plain left click; a modified click opens a new tab as usual. */
const go = (href: string) => (e: MouseEvent) => {
  if (e.metaKey || e.ctrlKey || e.shiftKey) return;
  e.preventDefault();
  navigate(href);
};

/** D-264: start a show from products approved earlier (the list survives a cold start, D-263). D-315: one row per
 * release; the rows picked, in order, are the show's line-up (D-279: at most 3). D-319: a secondary button in the hero
 * row opens them in a popover (a bottom sheet at phone width). */
function ReleasePicker() {
  const t = useT();
  const [rows, setRows] = useState<ReleaseRow[] | null>(null);
  const [lineup, setLineup] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [showOlder, setShowOlder] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const wasOpen = useRef(false);
  useEffect(() => {
    onboardingApi.releases().then(setRows, () => setRows([]));
  }, []);
  // D-319: focus into the panel on open and back to the button on close; Escape and an outside click close it
  useEffect(() => {
    if (!open) {
      if (wasOpen.current) button.current?.focus();
      wasOpen.current = false;
      return;
    }
    wasOpen.current = true;
    panel.current?.querySelector<HTMLElement>("button:not(:disabled)")?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onDown = (e: PointerEvent) => {
      const at = e.target as Node;
      if (!panel.current?.contains(at) && !button.current?.contains(at)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onDown);
    };
  }, [open]);
  // D-266: while a brief runs, look again every few seconds
  const running = rows?.some((r) => r.brief === "running") ?? false;
  useEffect(() => {
    if (!running) return;
    const timer = window.setTimeout(() => onboardingApi.releases().then(setRows, () => undefined), 4000);
    return () => window.clearTimeout(timer);
  }, [rows, running]);
  if (!rows?.length) return null;
  const byId = new Map(rows.map((r) => [r.release_id, r]));
  // D-332: a product's latest approved version; its older versions behind "Older versions"
  const product = (r: ReleaseRow) => r.release_id.replace(/_v\d+$/, "");
  const latest = new Map<string, ReleaseRow>();
  for (const r of rows) {
    const cur = latest.get(product(r));
    if (!cur || r.version > cur.version) latest.set(product(r), r);
  }
  const older = rows.filter((r) => latest.get(product(r)) !== r);
  const shown = [...latest.values(), ...(showOlder ? older : [])];
  const toggle = (id: string) =>
    setLineup((l) => (l.includes(id) ? l.filter((x) => x !== id) : l.length < MAX_SHOW ? [...l, id] : l));
  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const s = await onboardingApi.startShow(lineup);
      setOpen(false);
      navigate(`/studio?session=${encodeURIComponent(s.session_id)}`);
    } catch (e) {
      setError(t(userMessage(e)));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className={styles.hubPicker}>
      <button ref={button} type="button" className={styles.hubPickerButton} aria-haspopup="dialog" aria-expanded={open}
        aria-controls="hub-releases" onClick={() => setOpen((o) => !o)} data-testid="hub-releases-open">
        {t("Start with approved products")}
        <span className={styles.hubPickerCount}>{latest.size}</span>
        <ChevronDown aria-hidden className={styles.hubPickerChevron} />
      </button>
      {open && (
        <div id="hub-releases" ref={panel} role="dialog" aria-labelledby="hub-releases-title" className={styles.hubPickerPanel}
          data-testid="hub-releases">
          <div className={styles.hubReleasesHead}>
            <h2 id="hub-releases-title" className={styles.hubReleasesTitle}>{t("Previously approved products")}</h2>
            <span className={styles.hubStudioNote}>{t("Pick up to {n}, in the order of the show.", { n: MAX_SHOW })}</span>
          </div>
          <div className={styles.hubReleaseGrid}>
            {shown.map((r) => {
              const at = lineup.indexOf(r.release_id);
              const full = at < 0 && lineup.length >= MAX_SHOW;
              return (
                <button key={r.release_id} type="button" className={styles.hubRelease} aria-pressed={at >= 0}
                  disabled={full} onClick={() => toggle(r.release_id)} data-testid={`hub-release-${r.release_id}`}>
                  {at >= 0 && <span className={styles.hubReleaseOrder} aria-label={t("Product {n}", { n: at + 1 })}>{at + 1}</span>}
                  <span className={styles.hubReleaseBrand}>{r.brand}</span>
                  <span className={styles.hubReleaseName}>
                    {r.product_name}
                    {latest.get(product(r)) !== r && <span className={styles.hubReleaseOld}> · {t("older version")}</span>}
                  </span>
                  <span className={styles.hubReleaseMeta}>
                    {r.markets.map((m) => <Chip key={m}>{m}</Chip>)}
                    <span>v{r.version} · {new Date(r.approved_at).toLocaleDateString()}</span>
                    {r.brief === "running" ? (
                      <Chip tone="accent"><Loader2 className={styles.spin} aria-hidden />{t("brief running")}</Chip>
                    ) : r.brief === "done" ? (
                      <Chip tone="ok">{t("ready")}</Chip>
                    ) : null}
                  </span>
                </button>
              );
            })}
          </div>
          {older.length > 0 && (
            <button type="button" className={styles.hubLineupClear} aria-expanded={showOlder}
              onClick={() => setShowOlder((v) => !v)} data-testid="hub-releases-older">
              {showOlder ? t("Hide older versions") : t("Older versions ({n})", { n: older.length })}
            </button>
          )}
          <div className={styles.hubLineup} data-testid="hub-lineup">
            {lineup.length ? (
              <>
                <ol className={styles.hubLineupList} aria-label={t("Show line-up")}>
                  {lineup.map((id, i) => (
                    <li key={id}>
                      {i > 0 && <span aria-hidden>→ </span>}
                      {i + 1}. {byId.get(id)?.product_name ?? id}
                      <button type="button" className={styles.hubLineupRemove} onClick={() => toggle(id)}
                        aria-label={t("Remove {name}", { name: byId.get(id)?.product_name ?? id })}>
                        <X aria-hidden />
                      </button>
                    </li>
                  ))}
                </ol>
                <button type="button" className={styles.hubLineupClear} onClick={() => setLineup([])}
                  data-testid="hub-lineup-clear">
                  {t("Clear")}
                </button>
              </>
            ) : (
              <span className={styles.hubStudioNote}>{t("No product picked yet.")}</span>
            )}
          </div>
          <div className={styles.hubStudio}>
            <Button variant="primary" disabled={busy || !lineup.length} onClick={start} data-testid="hub-release-start">
              {lineup.length > 1 ? t("Start a show with {n} products", { n: lineup.length }) : t("Start a show with 1 product")}
            </Button>
            {lineup.some((id) => byId.get(id)?.brief === "running") && (
              <span className={styles.hubStudioNote} data-testid="hub-brief-running">{t(BRIEF_RUNNING_NOTE)}</span>
            )}
          </div>
          {error && <span className={styles.error} role="alert">{error}</span>}
        </div>
      )}
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
      setError(t(userMessage(e)));
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
          <Button variant="primary" disabled={busy} onClick={() => run(() => api.demoSession())}>
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
              <ReleasePicker />
            </div>
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
