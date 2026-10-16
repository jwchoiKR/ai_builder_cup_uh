import { ChartColumn, ChevronDown, ChevronRight, FileUp, Headset, LayoutGrid, ListChecks, Loader2, Mic, Smartphone, X, type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState, type CSSProperties, type Dispatch, type MouseEvent, type SetStateAction } from "react";

import { api, userMessage } from "../app/api";
import { useT } from "../app/i18n";
import { navigate, withSession, type ScreenProps } from "../app/nav";
import { useTheme } from "../app/theme";
import { Chip, SettingsButton } from "../components";
import { onboardingApi, type ReleaseRow } from "./onboarding/onboardingApi";
import { LoadingBar } from "./summary/SummaryView";
import styles from "./screens.module.css";

interface Screen {
  path: string;
  title: string;
  icon: LucideIcon;
  text: string;
  picker?: true;
  wide?: true;  // a full-width row under the phase's other cards  // the card holds the approved-products picker instead of being one link
}

// The screens in the order of a show; Studio (all of them side by side, for the demo) is the hero button.
const PHASES: { label: string; live?: boolean; screens: Screen[] }[] = [
  {
    label: "Pre-show",
    screens: [
      { path: "/onboarding", title: "Product onboarding", icon: FileUp,
        text: "Upload product documents, review the AI analysis, and approve products for broadcast." },
      { path: "/pick", title: "Select products", icon: ListChecks, picker: true,
        text: "Choose approved products to feature in this show." },
    ],
  },
  {
    label: "Live operations",
    live: true,
    screens: [
      { path: "/host", title: "Host screen", icon: Mic,
        text: "Read the prompter, review correction alerts, and see viewer questions to address on air." },
      { path: "/operator", title: "Operator screen", icon: Headset,
        text: "Manage the show schedule, switch featured products, and handle viewer questions." },
      { path: "/viewer", title: "Viewer screen", icon: Smartphone,
        text: "Live video, featured products, viewer chat, and AI answers based on product documents." },
      { path: "/studio", title: "Multi-screen view", icon: LayoutGrid, wide: true,
        text: "View the host, operator, and viewer screens side by side. Show or hide each screen as needed." },
    ],
  },
  {
    label: "Post-show",
    screens: [{ path: "/summary", title: "Broadcast report", icon: ChartColumn,
      text: "Review alerts, corrections, answered questions, and an AI summary of the show." }],
  },
];

const MAX_SHOW = 3;
const REPORT_POLL_MS = 10_000;  // D-279: a show of up to 3 products

const LEAD = "Keep the show moving. Keep the facts straight.\nAI checks product claims, suggests corrections, and "
  + "answers viewer questions based on your product documents.";

/** In-app navigation for a plain left click; a modified click opens a new tab as usual. */
const go = (href: string) => (e: MouseEvent) => {
  if (e.metaKey || e.ctrlKey || e.shiftKey) return;
  e.preventDefault();
  navigate(href);
};

/** D-264: start a show from products approved earlier (the list survives a cold start, D-263). D-315: one row per
 * release; the rows picked, in order, are the show's line-up (D-279: at most 3). D-319: a secondary button in the hero
 * row opens them in a popover (a bottom sheet at phone width). */
function ReleasePicker({ lineup, setLineup }: { lineup: string[]; setLineup: Dispatch<SetStateAction<string[]>> }) {
  const t = useT();
  const [rows, setRows] = useState<ReleaseRow[] | null>(null);
  const [open, setOpen] = useState(false);
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
  if (!rows?.length) return null;
  const byId = new Map(rows.map((r) => [r.release_id, r]));
  const toggle = (id: string) =>
    setLineup((l) => (l.includes(id) ? l.filter((x) => x !== id) : l.length < MAX_SHOW ? [...l, id] : l));
  return (
    <div className={styles.hubPicker}>
      <button ref={button} type="button" className={styles.hubPickerButton} aria-haspopup="dialog" aria-expanded={open}
        aria-controls="hub-releases" onClick={() => setOpen((o) => !o)} data-testid="hub-releases-open">
        {t("Approved products")}
        <span className={styles.hubPickerCount}>{rows.length}</span>
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
            {rows.map((r) => {
              const at = lineup.indexOf(r.release_id);
              const full = at < 0 && lineup.length >= MAX_SHOW;
              return (
                <button key={r.release_id} type="button" className={styles.hubRelease} aria-pressed={at >= 0}
                  disabled={full} onClick={() => toggle(r.release_id)} data-testid={`hub-release-${r.release_id}`}>
                  {at >= 0 && <span className={styles.hubReleaseOrder} aria-label={t("Product {n}", { n: at + 1 })}>{at + 1}</span>}
                  <span className={styles.hubReleaseBrand}>{r.brand}</span>
                  <span className={styles.hubReleaseName}>
                    {r.product_name}
                  </span>
                  <span className={styles.hubReleaseMeta}>
                    {r.markets.map((m) => <Chip key={m}>{m}</Chip>)}
                    <span>{new Date(r.approved_at).toLocaleDateString()}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>
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
              <span className={styles.hubStudioNote}>{t("No products selected.")}</span>
            )}
          </div>
    </div>
  );
}

export function Hub({ sessionId }: ScreenProps) {
  const [theme, , setTheme, themePref] = useTheme();
  const t = useT();
  const [starting, setStarting] = useState<string | null>(null);  // the card whose show is being created
  const [error, setError] = useState<string | null>(null);
  const [lineup, setLineup] = useState<string[]>([]);
  const [nudge, setNudge] = useState(false);  // a During-the-show card was pressed with no show and no product picked
  const pickCard = useRef<HTMLDivElement>(null);
  const shown = useRef("");  // the open show's line-up: picking the same products reopens it instead of starting a new one
  // back on the hub with a show open: its products stay picked
  useEffect(() => {
    if (!sessionId) return;
    api.state(sessionId, "operator").then(({ session }) => {
      const ids = session?.release_ids?.length ? session.release_ids : session?.release_id ? [session.release_id] : [];
      shown.current = ids.join();
      setLineup((cur) => (cur.length ? cur : ids));
    }, () => {});
  }, [sessionId]);
  useEffect(() => {
    if (lineup.length) setNudge(false);
  }, [lineup.length]);
  // D-496 (user): the report opens only once the show has ended and its summary is ready; checked every 10 s.
  // D-498: a failed one offers a retry, and shows the report being made again
  const [reportStatus, setReportStatus] = useState<string | null>(null);
  const reportReady = reportStatus === "ready";
  useEffect(() => {
    setReportStatus(null);
    if (!sessionId) return;
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const check = async () => {
      try {
        const status = (await api.summary(sessionId)).status;
        if (live) setReportStatus(typeof status === "string" ? status : null);
        if (status === "ready") return;
      } catch {
        // not there yet: check again
      }
      if (live) timer = setTimeout(check, REPORT_POLL_MS);
    };
    void check();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [sessionId]);
  const retryReport = async (e: MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();  // the card itself stays disabled
    if (!sessionId) return;
    setReportStatus("computing");
    try {
      setReportStatus((await api.retrySummary(sessionId)).status);
    } catch {
      setReportStatus("failed");
    }
  };

  // a During-the-show card starts the show with the picked line-up, then opens that screen of it
  const openLive = (path: string) => async (e: MouseEvent) => {
    if (starting) return e.preventDefault();  // one show per press: the first one is still being created
    if (!lineup.length && !sessionId && !(e.metaKey || e.ctrlKey || e.shiftKey)) {
      // no show to open yet: point at Pick products instead
      e.preventDefault();
      setNudge(true);
      pickCard.current?.scrollIntoView?.({ behavior: "smooth", block: "center" });
      pickCard.current?.querySelector<HTMLElement>("button")?.focus({ preventScroll: true });
      return;
    }
    if (!lineup.length || lineup.join() === shown.current || e.metaKey || e.ctrlKey || e.shiftKey) return go(withSession(path, sessionId))(e);
    e.preventDefault();
    setStarting(path);
    setError(null);
    try {
      const s = await onboardingApi.startShow(lineup);
      navigate(withSession(path, s.session_id));
    } catch (err) {
      setError(t(userMessage(err)));
      setStarting(null);
    }
  };

  return (
    <div className={`${styles.root} ${styles.hubRoot}`} data-theme={theme} lang="en">
      <header className={`${styles.header} ${styles.hubHeader}`}>
        <div className={styles.hubBrand}>
          <span className="eyebrow">LIVE / STUDIO</span>
          <div className={styles.hubBrandLine}>
            <h1 className={styles.hubTitle}>{t("Live Shopping Hub")}</h1>
            {sessionId && <span className={`${styles.subtitle} tabular`}>{t("Session {id}", { id: sessionId })}</span>}
          </div>
        </div>
        <div className={styles.headerActions}>
          <SettingsButton themePref={themePref} onTheme={setTheme} />
        </div>
      </header>
      <main className={`${styles.body} ${styles.hubBody}`}>
        <div className={styles.hubContent}>
          {error && <p className={styles.error}>{error}</p>}
          <section className={styles.hubHero}>
            <p className={styles.hubLead}>{t(LEAD)}</p>
          </section>
          <div className={styles.hubPhases}>
            {PHASES.map((phase, i) => (
              <div key={phase.label} className={styles.hubPhaseSlot} data-phase={i}>
                {i > 0 && <ChevronRight className={styles.hubChevron} aria-hidden />}
                <section className={styles.hubPhase} aria-label={t(phase.label)}>
                  <h2 className={styles.hubPhaseLabel}>{t(phase.label)}</h2>
                  <div className={styles.hubPhaseCards} style={{ "--cards": phase.screens.filter((s) => !s.wide).length } as CSSProperties}>
                    {phase.screens.map((s) => {
                      const href = withSession(s.path, sessionId);
                      const Icon = s.icon;
                      // the picked line-up becomes this hub's show: the cards below then open that show
                      if (s.picker) return (
                        <div key={s.path} ref={pickCard} data-testid="hub-card-pick"
                          className={`${styles.hubCard} ${styles.hubCardStatic} ${nudge ? styles.hubCardNudge : ""}`}>
                          <span className={styles.hubIcon}>
                            <Icon aria-hidden />
                          </span>
                          <span className={styles.hubCardTitle}>{t(s.title)}</span>
                                    <span className={styles.hubText}>{t(s.text)}</span>
                          {nudge && (
                            <p className={styles.hubNudge} role="alert" data-testid="hub-pick-nudge">
                              {t("Pick the show's products here first.")}
                            </p>
                          )}
                          <ReleasePicker lineup={lineup} setLineup={setLineup} />
                        </div>
                      );
                      const waiting = s.path === "/summary" && !reportReady;  // D-496
                      if (waiting) return (
                        // D-496/D-498: not a link until the report is ready; a failed report offers a retry
                        <div key={s.path} className={`${styles.hubCard} ${styles.hubCardDisabled}`} aria-disabled="true"
                          data-testid={`hub-card-${s.path.slice(1)}`}>
                          <span className={styles.hubIcon}>
                            <Icon aria-hidden />
                          </span>
                          <span className={styles.hubCardTitle}>{t(s.title)}</span>
                          <span className={styles.hubText}>{t(s.text)}</span>
                          {reportStatus === "failed" && (
                            <span className={styles.hubReportState} data-testid="hub-report-failed">
                              <span className={styles.hubStudioNote}>{t("Report failed")}</span>
                              <button type="button" className={styles.hubRetry} onClick={retryReport}
                                data-testid="hub-report-retry">
                                {t("Retry")}
                              </button>
                            </span>
                          )}
                          {reportStatus === "computing" && (
                            <span className={styles.hubReportState} data-testid="hub-report-making">
                              <span className={styles.hubStudioNote}>{t("Making the report…")}</span>
                              <LoadingBar label="Making the report" />
                            </span>
                          )}
                        </div>
                      );
                      return (
                        <a key={s.path} className={`${styles.hubCard} ${s.wide ? styles.hubCardWide : ""}`} href={href}
                          onClick={phase.live ? openLive(s.path) : go(href)}
                          aria-disabled={!!starting || undefined} aria-busy={starting === s.path || undefined}
                          data-testid={`hub-card-${s.path.slice(1)}`}>
                          <span className={styles.hubIcon}>
                            <Icon aria-hidden />
                          </span>
                          <span className={styles.hubCardTitle}>{t(s.title)}</span>
                                    <span className={styles.hubText}>{t(s.text)}</span>
                          {starting === s.path && (
                            <span className={styles.hubStarting} role="status">
                              <Loader2 className={styles.spin} aria-hidden /> {t("Starting the show…")}
                            </span>
                          )}
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
