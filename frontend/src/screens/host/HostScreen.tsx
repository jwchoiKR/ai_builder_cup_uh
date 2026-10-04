// Host screen (§12.3): the calm view in front of the host. No required clicks, no sounds; only the
// HIGH-risk compliance overlay covers the screen. Keyboard: Esc cancels a pending switch, M toggles
// the mic, T the theme (§12.3.10).
import { Menu, Timer } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";

import { api } from "../../app/api";
import { useMic, type MicSnapshot, type MicState } from "../../app/mic";
import type { ScreenProps } from "../../app/nav";
import {
  activeHighAlert,
  activePdCard,
  chatItems,
  cueStrip,
  formatClock,
  hostBanners,
  hostSlots,
  priceView,
  productById,
  provisionalAlerts,
} from "../../app/selectors";
import type { ConnectionStatus } from "../../app/sse";
import type { ClientState } from "../../app/state";
import { useCatalog, useNow, useSession } from "../../app/store";
import { useTheme, type ThemeName } from "../../app/theme";
import type { Catalog } from "../../app/types";
import { Countdown, Elapsed } from "../../components";
import { CorrectedBar, CueStrip, FactNote, MediumBanner, SwitchBanner } from "./Banners";
import { Chat } from "./Chat";
import { ComplianceOverlay } from "./ComplianceOverlay";
import { useCorrectedToast, useHostScale } from "./hooks";
import { correctedToastMs, hostProducts, hostPrompterView, promoChips, switchSecondsLeft } from "./hostSelectors";
import styles from "./host.module.css";
import { PdCard } from "./PdCard";
import { Prompter } from "./Prompter";
import { Questions } from "./Questions";

const cx = (...n: (string | false | null | undefined)[]) => n.filter(Boolean).join(" ");

export interface HostActions {
  /** POST /alerts/{aid}/rendered (once per alert). */
  rendered: (alertId: string) => void;
  /** POST /segments/cancel {by: "host"}. */
  cancelSwitch: () => void;
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
}: {
  state: ClientState;
  catalog: Catalog | null;
  now: number;
  mic: Pick<MicSnapshot, "state" | "level" | "message">;
}) {
  const s = state.session;
  const { now: onAir, next } = hostProducts(state, catalog);
  const promos = promoChips(state, catalog, now);
  const live = s?.status === "live" && s.started_at !== null;
  const ended = s?.status === "ended" && s.started_at !== null;
  return (
    <header className={styles.topbar} data-testid="host-topbar">
      <span className={styles.brand}>
        <Menu className={styles.brandIcon} aria-hidden />
        LIVE / Studio
      </span>
      <span className={cx(styles.live, live && styles.liveOn)} data-testid="host-live">
        {live || ended ? (
          <>
            <span className={live ? styles.liveDot : styles.readyDot} aria-hidden />
            <span className={styles.liveLabel}>LIVE</span>
            {live ? (
              <Elapsed since={s!.started_at!} serverOffsetMs={state.serverOffsetMs} />
            ) : (
              <span className="tabular">{formatClock((s!.ended_at ?? now) - s!.started_at!)}</span>
            )}
          </>
        ) : (
          <>
            <span className={styles.readyDot} aria-hidden />
            <span className={styles.readyLabel}>READY</span>
          </>
        )}
      </span>
      <div className={styles.nowNext}>
        <span className={styles.nnLabel}>NOW</span>
        <span className={styles.nowName} data-testid="host-now">
          {onAir?.name ?? "—"}
        </span>
        <span className={styles.nnLabel}>NEXT</span>
        <span className={styles.nextName} data-testid="host-next">
          {next?.name ?? "End of run sheet"}
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
        aria-label={MIC_LABEL[mic.state]}
        title={mic.message ?? MIC_LABEL[mic.state]}
        data-testid="host-mic"
        data-state={mic.state}
      >
        mic
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
    </header>
  );
}

export function HostView({
  state,
  catalog,
  connection,
  embedded,
  theme,
  onToggleTheme,
  actions,
}: {
  state: ClientState;
  catalog: Catalog | null;
  connection: ConnectionStatus;
  embedded?: boolean;
  theme: ThemeName;
  onToggleTheme?: () => void;
  actions: HostActions;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const scale = useHostScale(rootRef);
  const clientNow = useNow(250);
  const now = clientNow + state.serverOffsetMs;
  const mic = useMic();
  const sessionId = state.session?.session_id ?? null;

  const sw = state.session?.switch;
  const pendingSwitch = sw?.status === "pending" && sw.commit_at ? sw : null;
  const high = activeHighAlert(state);
  const pd = !high ? activePdCard(state, clientNow) : null;

  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "Escape" && pendingSwitch) actions.cancelSwitch();
      else if ((e.key === "m" || e.key === "M") && sessionId) mic.toggle(sessionId);
      else if ((e.key === "t" || e.key === "T") && !embedded) onToggleTheme?.();
      else if ((e.key === "n" || e.key === "N") && sessionId && pd && pd.status === "active") {
        actions.dismissPd(pd.card_id);
      }
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [actions, embedded, onToggleTheme, pendingSwitch, sessionId, mic, pd]);

  const { now: product } = hostProducts(state, catalog);
  const prompter = hostPrompterView(state, catalog, product);
  const price = priceView(state, catalog, prompter.product ?? product);
  const cue = cueStrip(state, clientNow);
  const { mediums, facts } = hostBanners(state);
  const checking = provisionalAlerts(state).length > 0;
  const toast = useCorrectedToast(state.alerts, correctedToastMs(state));
  const target = pendingSwitch ? productById(catalog, pendingSwitch.target_product_id) : null;
  const bannersOpen = Boolean(mediums.length || facts.length || pendingSwitch);

  return (
    <div
      ref={rootRef}
      className={cx(styles.root, embedded && styles.embedded)}
      data-theme={theme}
      data-screen="host"
      style={{ "--hs": scale } as CSSProperties}
    >
      <TopBar state={state} catalog={catalog} now={now} mic={mic} />
      <div className={styles.content}>
        {cue && <CueStrip cue={cue} />}
        <div className={cx(styles.banners, bannersOpen && styles.bannersOpen)}>
          <div className={styles.bannersInner}>
            {mediums.map(({ alert: a, fact }) => (
              <MediumBanner key={a.alert_id} alert={a} catalog={catalog} fact={fact} />
            ))}
            {facts.slice(0, 2).map((a) => (
              <FactNote key={a.alert_id} alert={a} catalog={catalog} />
            ))}
            {pendingSwitch && (
              <SwitchBanner
                productName={target?.name ?? "the next product"}
                secondsLeft={switchSecondsLeft(pendingSwitch.commit_at, now)}
                onCancel={actions.cancelSwitch}
              />
            )}
          </div>
        </div>
        {/* D-095: live chat is what the host watches most, so it has the whole right column; the
            prompter and the audience questions share the left one. */}
        <div className={styles.main}>
          <div className={cx(styles.left, pd && styles.leftWithPd)}>
            {pd && <PdCard card={pd} onDismiss={actions.dismissPd} />}
            <Prompter view={prompter} product={prompter.product ?? product} price={price} checking={checking} />
            <Questions slots={hostSlots(state)} catalog={catalog} />
          </div>
          <div className={styles.right}>
            <Chat
              items={chatItems(state)}
              pinnedNotice={state.session?.pinned_notice ?? null}
              connection={connection}
              serverOffsetMs={state.serverOffsetMs}
            />
          </div>
        </div>
        {high && (
          <ComplianceOverlay
            key={high.alert.alert_id}
            view={high}
            catalog={catalog}
            serverOffsetMs={state.serverOffsetMs}
            onRendered={actions.rendered}
          />
        )}
        {!high && toast && <CorrectedBar />}
      </div>
    </div>
  );
}

// Render acks are sent once per (session, alert) per page, even with several host views mounted.
const acked = new Set<string>();

export function HostScreen(props: ScreenProps) {
  const [ownTheme, toggle] = useTheme("host");
  const theme = props.theme ?? ownTheme;
  const { state, connection } = useSession(props.sessionId, "host");
  const catalog = useCatalog();
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
  const cancelSwitch = useCallback(() => {
    if (sid) void api.cancelSwitch(sid, "host").catch(() => undefined);
  }, [sid]);
  const dismissPd = useCallback(
    (cardId: string) => {
      if (!sid) return;
      void api.dismissPdCard(sid, cardId).catch(() => undefined);
    },
    [sid],
  );
  // One stable object for the view; its functions call the latest callbacks.
  const latest = useRef<HostActions>({ rendered, cancelSwitch, dismissPd });
  latest.current = { rendered, cancelSwitch, dismissPd };
  const [actions] = useState<HostActions>(() => ({
    rendered: (id) => latest.current.rendered(id),
    cancelSwitch: () => latest.current.cancelSwitch(),
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
      actions={actions}
    />
  );
}
