// Host screen (§12.3): the calm view in front of the host. No required clicks, no sounds; only the
// HIGH-risk compliance overlay covers the screen. Keyboard: Esc undoes an immediate switch, M toggles
// the mic, T the theme (§12.3.10).
import { LayoutGrid, Timer } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

import { api } from "../../app/api";
import { useMic, type MicSnapshot, type MicState } from "../../app/mic";
import type { ScreenProps } from "../../app/nav";
import {
  activeHighAlert,
  alertBlocking,
  RED_BLOCK_MS,
  unansweredCount,
  activePdCard,
  chatItems,
  cueStrip,
  formatClock,
  hostAlertStack,
  uncheckedStrip,
  hostSlots,
  runOfShow,
  clearedTiming,
  lineStillActive,
  shownTiming,
  timingLabel,
} from "../../app/selectors";
import type { ConnectionStatus } from "../../app/sse";
import type { ClientState } from "../../app/state";
import { useAudience, useCatalog, useNow, useSession } from "../../app/store";
import { useT } from "../../app/i18n";
import { COLS_MAX, HOST_LAYOUT_DEFAULT, setHostLayout, useHostLayout, useReadingSize } from "../../app/prefs";
import { useTheme, type ThemeName, type ThemePref } from "../../app/theme";
import type { HostBox } from "../../app/selectors";
import type { Catalog } from "../../app/types";
import { BroadcastControl, Countdown, Elapsed, HubLink, SettingsButton, Splitter } from "../../components";
import { CorrectedBar, CueStrip, FactNote, MediumBanner, SwitchedBar, UncheckedStrip } from "./Banners";
import { Chat } from "./Chat";
import { ComplianceOverlay } from "./ComplianceOverlay";
import { useCorrectedToast, useHostScale } from "./hooks";
import { correctedToastMs, hostProducts, hostPrompterView, promoChips } from "./hostSelectors";
import styles from "./host.module.css";
import { pointsStatus, Prompter } from "./Prompter";
import { Questions } from "./Questions";

const cx = (...n: (string | false | null | undefined)[]) => n.filter(Boolean).join(" ");

export interface HostActions {
  /** POST /alerts/{aid}/rendered (once per alert). */
  rendered: (alertId: string) => void;
  /** POST /segments/undo: take back an immediate switch (D-349). */
  undoSwitch: () => void;
  /** POST /sessions/{sid}/pd/dismiss {card_id: "..."}. */
  dismissPd: (cardId: string) => void;
}

function isTyping(target: EventTarget | null): boolean {
  const t = target as HTMLElement | null;
  return Boolean(t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable));
}

const MIC_LABEL: Record<MicState, string> = {
  off: "Microphone off",
  connecting: "Microphone connecting",
  listening: "Microphone listening",
  error: "Microphone error",
};

function TopBar({
  state,
  catalog,
  now,
  mic,
  onToggleMic,
  settings,
  embedded = false,
}: {
  state: ClientState;
  catalog: Catalog | null;
  now: number;
  mic: Pick<MicSnapshot, "state" | "level" | "message">;
  /** the mic chip is a button: a click turns the microphone on or off, like the M key */
  onToggleMic?: () => void;
  settings?: ReactNode;
  /** Studio pane: no link back to the Hub (Studio has its own) */
  embedded?: boolean;
}) {
  const t = useT();
  const s = state.session;
  const { now: onAir, next } = hostProducts(state, catalog);
  const promos = promoChips(state, catalog, now);
  const live = s?.status === "live" && s.started_at !== null;
  const ended = s?.status === "ended" && s.started_at !== null;
  return (
    <header className={styles.topbar} data-testid="host-topbar">
      {embedded ? (
        <span className={styles.brand}>LIVE / Studio</span>
      ) : (
        // back to the Hub; during a live show it asks first
        <HubLink sessionId={s?.session_id} live={s?.status === "live"} className={styles.brand}>
          <LayoutGrid className={styles.brandIcon} aria-hidden />
          LIVE / Studio
        </HubLink>
      )}
      <span className={cx(styles.live, live && styles.liveOn)} data-testid="host-live">
        {live || ended ? (
          <>
            <span className={live ? styles.liveDot : styles.readyDot} aria-hidden />
            <span className={styles.liveLabel}>{t("LIVE")}</span>
            {live ? (
              <Elapsed since={s!.started_at!} serverOffsetMs={state.serverOffsetMs} />
            ) : (
              <span className="tabular">{formatClock((s!.ended_at ?? now) - s!.started_at!)}</span>
            )}
          </>
        ) : (
          <>
            <span className={styles.readyDot} aria-hidden />
            <span className={styles.readyLabel}>{t("READY")}</span>
          </>
        )}
      </span>
      {state.market?.tier === "preview" && (
        // D-150: no sealed eval yet for this market or language: host cards only, nothing auto-posted
        <span className={styles.previewTag} data-testid="host-preview" title={t("Preview: nothing is posted automatically")}>
          {t("PREVIEW")} · {state.market.name}
        </span>
      )}
      {state.market?.law_checks === false && (
        // D-228: a category no law pack covers (apparel, supplements for now): no compliance alerts will come
        <span className={styles.previewTag} data-testid="host-no-law" title={t("No law checks for this category")}>
          {t("No law checks for this category")} · {state.market.category}
        </span>
      )}
      {/* D-412: the lines no judge could check, one compact strip (never an alert box) */}
      <UncheckedStrip {...uncheckedStrip(state)} />
      <div className={styles.nowNext}>
        <span className={styles.nnLabel}>{t("NOW")}</span>
        <span className={styles.nowName} data-testid="host-now">
          {onAir?.name ?? "—"}
        </span>
        <span className={styles.nnLabel}>{t("NEXT")}</span>
        <span className={styles.nextName} data-testid="host-next">
          {next?.name ?? t("End of run sheet")}
        </span>
      </div>
      <span className={styles.spacer} />
      {promos.map((p) => (
        <span key={p.promo.promo_id} className={styles.promoChip} data-testid="host-promo-chip">
          <Timer aria-hidden />
          {p.promo.host_text}
          <Countdown until={p.endsAt} serverOffsetMs={state.serverOffsetMs} />
        </span>
      ))}
      <button
        type="button"
        className={cx(styles.mic, live && mic.state === "off" && styles.micPrompt)}
        aria-label={t(MIC_LABEL[mic.state])}
        aria-pressed={mic.state === "listening" || mic.state === "connecting"}
        title={mic.message ?? t(mic.state === "off" ? "Turn the microphone on (M)" : MIC_LABEL[mic.state])}
        data-testid="host-mic"
        data-state={mic.state}
        onClick={onToggleMic}
        disabled={!onToggleMic}
      >
        {mic.state === "off" ? (live ? t("Mic off · click or press M") : t("mic off")) : t("mic")}
        {mic.state === "listening" && (
          <span className={styles.micLevel} aria-hidden>
            <span style={{ transform: `scaleX(${Math.max(0.04, mic.level)})` }} />
          </span>
        )}
        <span
          className={cx(
            styles.micDot,
            mic.state === "listening" && styles.micOn,
            mic.state === "error" && styles.micError,
            mic.state === "connecting" && styles.micConnecting,
          )}
        />
      </button>
      {/* the same Start / End control as the operator's: one session, so it acts for every screen. Not in a Studio
          pane, where the operator pane beside it already has it. */}
      {!embedded && <BroadcastControl sessionId={s?.session_id ?? null} status={s?.status} size="sm" />}
      {settings}
    </header>
  );
}

const SWITCHED_BAR_MS = 8000; // D-349: how long the host sees "Switched to … · Undo"
const EMBEDDED_MIN_SCALE = 0.7; // D-332: in a Studio pane the text stays readable (cautions about 10.5 px at 1440 px)

export function HostView({
  state,
  catalog,
  connection,
  embedded,
  theme,
  onToggleTheme,
  themePref,
  onSetTheme,
  actions,
  audience = null,
}: {
  state: ClientState;
  catalog: Catalog | null;
  connection: ConnectionStatus;
  embedded?: boolean;
  theme: ThemeName;
  onToggleTheme?: () => void;
  /** D-109: the Settings gear's theme choice (absent when the Studio controls the theme) */
  themePref?: ThemePref;
  onSetTheme?: (t: ThemePref) => void;
  actions: HostActions;
  /** D-477: how many are watching; null hides it */
  audience?: number | null;
}) {
  const t = useT();
  const rootRef = useRef<HTMLDivElement>(null);
  const readingSize = useReadingSize(); // D-119: 100 / 125 / 150% from the Settings gear
  const layout = useHostLayout(); // D-181: the panel sizes, one per browser (Studio's host pane too)
  const scale = useHostScale(rootRef, embedded ? EMBEDDED_MIN_SCALE : undefined) * readingSize;
  const clientNow = useNow(250);
  const now = clientNow + state.serverOffsetMs;
  const mic = useMic();
  const sessionId = state.session?.session_id ?? null;

  const sw = state.session?.switch;
  // D-349: an immediate switch shows "Switched to … · Undo" for a few seconds
  const switched = sw?.last_commit?.immediate && now - sw.last_commit.at < SWITCHED_BAR_MS ? sw.last_commit : null;
  const high = activeHighAlert(state); // D-177: full size until corrected
  const blocking = alertBlocking(state, now); // D-161, D-402: cards only after an alert's first 20 s, below it
  const pd = !blocking ? activePdCard(state, clientNow) : null;

  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      // D-429 (user): the host is hands-free; the keys Q, N, E and Esc are gone
      if ((e.key === "m" || e.key === "M") && sessionId) mic.toggle(sessionId);
      else if ((e.key === "t" || e.key === "T") && !embedded) onToggleTheme?.();
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [embedded, onToggleTheme, sessionId, mic]);

  const { now: product } = hostProducts(state, catalog);
  const prompter = hostPrompterView(state, catalog, product);
  const cue = cueStrip(state, clientNow);
  const onAir = runOfShow(state, catalog, now).find((i) => i.status === "on_air");
  const timing = onAir ? { elapsedMs: onAir.elapsedMs, plannedMs: onAir.plannedMs } : null;
  // D-306: also while the verifier checks a line's candidates (an alert shows only once it answers)
  const toast = useCorrectedToast(state.alerts, correctedToastMs(state));
  // D-106, D-107: compliance alerts, fact notes and the green Corrected bar take the prompter's
  // product box, in this order: HIGH, fact notes, MEDIUM. D-402 (user): red and orange at the same level: one stack
  // of same-size boxes, at most MAX_ALERT_BOXES; the last one shown carries "+N" (D-404: by alert id).
  const stack = hostAlertStack(state);
  const box = (b: HostBox, more: number) =>
    b.kind === "high" ? (
      // D-407: the ring marks only the newest red, within RED_BLOCK_MS of its own creation
      <ComplianceOverlay key={b.view.alert.alert_id} view={b.view}
        fresh={b.view.position === 1 && now - b.view.alert.created_at < RED_BLOCK_MS}
        catalog={catalog} serverOffsetMs={state.serverOffsetMs} onRendered={actions.rendered} more={more}
        retraction={state.market?.retraction_phrase}
        timing={timingLabel("shown", shownTiming(b.view.alert, state.transcripts), t)}
        then={b.then} cleared={b.cleared}
        timingOf={(a) => timingLabel("shown", shownTiming(a, state.transcripts), t)} />
    ) : b.kind === "fact" ? (
      <FactNote key={b.alert.alert_id} alert={b.alert} catalog={catalog} onRendered={actions.rendered} count={b.count}
        more={more} timing={timingLabel("shown", shownTiming(b.alert, state.transcripts), t)} />
    ) : (
      <MediumBanner key={b.alert.alert_id} alert={b.alert} catalog={catalog} onRendered={actions.rendered}
        count={b.count} more={more} />
    );
  const prompterAlerts =
    stack.shown.length ? <>{stack.shown.map((b, i) => box(b, i === stack.shown.length - 1 ? stack.more : 0))}</> : null;

  return (
    <div
      ref={rootRef}
      className={cx(styles.root, embedded && styles.embedded)}
      data-theme={theme}
      data-screen="host"
      style={{ "--hs": scale } as CSSProperties}
    >
      <TopBar
        state={state}
        catalog={catalog}
        now={now}
        mic={mic}
        onToggleMic={sessionId ? () => mic.toggle(sessionId) : undefined}
        settings={embedded ? null : <SettingsButton themePref={themePref} onTheme={onSetTheme} host />}
        embedded={embedded}
      />
      <div className={styles.content}>
        <div className={styles.main}
          style={{ gridTemplateColumns: `minmax(0, ${fr(layout.cols)}fr) var(--split-gap) minmax(0, ${fr(1 - layout.cols)}fr)` }}>
          <div className={styles.left}
            style={{ gridTemplateRows: `minmax(auto, ${fr(layout.rows)}fr) var(--split-gap) minmax(auto, ${fr(1 - layout.rows)}fr)` }}>
            <Prompter
              view={prompter}
              product={prompter.product ?? product}
              degraded={state.judgeDegraded}
              alerts={prompterAlerts}
              notice={!high && toast && !lineStillActive(state, toast)  // D-442: never "Corrected" while the line has an active alert
                ? <CorrectedBar timing={timingLabel("cleared", clearedTiming(toast, state.transcripts), t)} /> : null}
              status={
                // D-115: one reserved line, so nothing below the prompter moves
                switched ? (
                  <SwitchedBar productName={product?.name ?? t("the next product")} onUndo={actions.undoSwitch} />
                ) : cue ? (
                  <CueStrip cue={cue} />
                ) : (
                  <span className={cx(styles.pointsStatus, "tabular")} data-testid="host-points-status">
                    {pointsStatus(t, timing)}
                  </span>
                )
              }
              timing={timing}
            />
            <Splitter orientation="horizontal" value={layout.rows} onChange={(rows) => setHostLayout({ rows })}
              onReset={() => setHostLayout({ rows: HOST_LAYOUT_DEFAULT.rows })} label={t("Resize prompter and questions")}
              testId="host-split-rows" />
            {/* D-107: everything that comes and goes sits here, so the prompter box never moves;
                D-127: the AI PD card lives inside the questions panel */}
            <div className={styles.leftBottom}>
              <Questions slots={hostSlots(state)} card={pd} onDismiss={actions.dismissPd} correcting={blocking}
                unanswered={unansweredCount(state)} />
            </div>
          </div>
          <Splitter orientation="vertical" value={layout.cols} max={COLS_MAX} onChange={(cols) => setHostLayout({ cols })}
            onReset={() => setHostLayout({ cols: HOST_LAYOUT_DEFAULT.cols })} label={t("Resize prompter and chat")}
            testId="host-split-cols" />
          <div className={styles.right}>
            <Chat
              items={chatItems(state)}
              pinnedNotice={state.session?.pinned_notice ?? null}
              connection={connection}
              serverOffsetMs={state.serverOffsetMs}
              audience={audience}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

/** D-181: a split as whole fr units ("58fr"): when the prompter keeps its minimum height, the other panel's
 *  share stays at least 1fr, so it still takes all the space left (fractions below 1fr would leave a gap). */
const fr = (v: number) => Math.round(v * 1000) / 10;

// Render acks are sent once per (session, alert) per page, even with several host views mounted.
const acked = new Set<string>();

export function HostScreen(props: ScreenProps) {
  const [ownTheme, toggle, setTheme, themePref] = useTheme();
  const theme = props.theme ?? ownTheme;
  const { state, connection } = useSession(props.sessionId, "host");
  const catalog = useCatalog(props.sessionId);
  const sid = props.sessionId;
  const audience = useAudience(sid);

  const rendered = useCallback(
    (alertId: string) => {
      if (!sid) return;
      const key = `${sid}:${alertId}`;
      if (acked.has(key)) return;
      acked.add(key);
      void api.alertRendered(sid, alertId).catch(() => acked.delete(key));
    },
    [sid],
  );
  const undoSwitch = useCallback(() => {
    if (sid) void api.undoSwitch(sid).catch(() => undefined);
  }, [sid]);
  const dismissPd = useCallback(
    (cardId: string) => {
      if (!sid) return;
      void api.dismissPdCard(sid, cardId).catch(() => undefined);
    },
    [sid],
  );
  // One stable object for the view; its functions call the latest callbacks.
  const latest = useRef<HostActions>({ rendered, undoSwitch, dismissPd });
  latest.current = { rendered, undoSwitch, dismissPd };
  const [actions] = useState<HostActions>(() => ({
    rendered: (id) => latest.current.rendered(id),
    undoSwitch: () => latest.current.undoSwitch(),
    dismissPd: (id) => latest.current.dismissPd(id),
  }));

  return (
    <HostView
      state={state}
      catalog={catalog}
      connection={connection}
      embedded={props.embedded}
      theme={theme}
      onToggleTheme={props.theme ? undefined : toggle}
      themePref={themePref}
      onSetTheme={props.theme ? undefined : setTheme}
      actions={actions}
      audience={audience}
    />
  );
}
