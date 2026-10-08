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
  hostSlots,
  priceView,
  runOfShow,
} from "../../app/selectors";
import type { ConnectionStatus } from "../../app/sse";
import type { ClientState } from "../../app/state";
import { useCatalog, useNow, useSession } from "../../app/store";
import { useT } from "../../app/i18n";
import { COLS_MAX, HOST_LAYOUT_DEFAULT, setHostLayout, useHostLayout, useReadingSize } from "../../app/prefs";
import { useTheme, type ThemeName, type ThemePref } from "../../app/theme";
import type { HostBox } from "../../app/selectors";
import type { Catalog } from "../../app/types";
import { Countdown, Elapsed, HubLink, SettingsButton, Splitter } from "../../components";
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
  /** POST /sessions/{sid}/pd/pull: the top waiting question now (key Q, D-113). */
  pullQuestion: () => void;
  /** POST /sessions/{sid}/segments/extend: +2 min on the on-air product (key E, D-138). */
  extendSegment: () => void;
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
  settings,
  embedded = false,
}: {
  state: ClientState;
  catalog: Catalog | null;
  now: number;
  mic: Pick<MicSnapshot, "state" | "level" | "message">;
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
      <UncheckedStrip count={state.unchecked.ids.length} cause={state.unchecked.cause} />
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
      <span
        className={styles.mic}
        aria-label={t(MIC_LABEL[mic.state])}
        title={mic.message ?? t(MIC_LABEL[mic.state])}
        data-testid="host-mic"
        data-state={mic.state}
      >
        {t("mic")}
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
      </span>
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
      if (e.key === "Escape" && switched) actions.undoSwitch();
      else if ((e.key === "m" || e.key === "M") && sessionId) mic.toggle(sessionId);
      else if ((e.key === "t" || e.key === "T") && !embedded) onToggleTheme?.();
      else if ((e.key === "n" || e.key === "N") && sessionId && pd && pd.status === "active") {
        actions.dismissPd(pd.card_id);
      } else if ((e.key === "q" || e.key === "Q") && sessionId) actions.pullQuestion();
      else if ((e.key === "e" || e.key === "E") && sessionId) actions.extendSegment();
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [actions, embedded, onToggleTheme, switched, sessionId, mic, pd]);

  const { now: product } = hostProducts(state, catalog);
  const prompter = hostPrompterView(state, catalog, product);
  const price = priceView(state, catalog, prompter.product ?? product);
  const cue = cueStrip(state, clientNow);
  const onAir = runOfShow(state, catalog, now).find((i) => i.status === "on_air");
  const timing = onAir ? { elapsedMs: onAir.elapsedMs, plannedMs: onAir.plannedMs } : null;
  // D-306: also while the verifier checks a line's candidates (an alert shows only once it answers)
  const checking = Object.keys(state.verifying).length > 0;  // D-410: no provisional alert any more
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
        catalog={catalog} serverOffsetMs={state.serverOffsetMs} onRendered={actions.rendered} more={more} />
    ) : b.kind === "fact" ? (
      <FactNote key={b.alert.alert_id} alert={b.alert} catalog={catalog} onRendered={actions.rendered} count={b.count}
        more={more} />
    ) : (
      <MediumBanner key={b.alert.alert_id} alert={b.alert} catalog={catalog} fact={b.fact} onRendered={actions.rendered}
        count={b.count} more={more} factCount={b.factCount} />
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
              price={price}
              checking={checking}
              degraded={state.judgeDegraded}
              alerts={prompterAlerts}
              notice={!high && toast ? <CorrectedBar /> : null}
              status={
                // D-115: one reserved line, so nothing below the prompter moves
                switched ? (
                  <SwitchedBar productName={product?.name ?? t("the next product")} onUndo={actions.undoSwitch} />
                ) : cue ? (
                  <CueStrip cue={cue} />
                ) : (
                  <span className={cx(styles.pointsStatus, "tabular")} data-testid="host-points-status">
                    {pointsStatus(t, prompter.requiredTotal - prompter.requiredCovered, timing, prompter.requiredTotal)}
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
  const pullQuestion = useCallback(() => {
    if (sid) void api.pullQuestion(sid).catch(() => undefined);
  }, [sid]);
  const extendSegment = useCallback(() => {
    if (sid) void api.extendSegment(sid).catch(() => undefined);
  }, [sid]);
  // One stable object for the view; its functions call the latest callbacks.
  const latest = useRef<HostActions>({ rendered, undoSwitch, dismissPd, pullQuestion, extendSegment });
  latest.current = { rendered, undoSwitch, dismissPd, pullQuestion, extendSegment };
  const [actions] = useState<HostActions>(() => ({
    rendered: (id) => latest.current.rendered(id),
    undoSwitch: () => latest.current.undoSwitch(),
    dismissPd: (id) => latest.current.dismissPd(id),
    pullQuestion: () => latest.current.pullQuestion(),
    extendSegment: () => latest.current.extendSegment(),
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
    />
  );
}
