// Viewer page body (§12.5). Pure presentation over the client state; Viewer.tsx wires the store.
import { BadgeCheck, Gift, Mic, Pin, Send, Sparkles } from "lucide-react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type FormEvent } from "react";

import { ApiError } from "../../app/api";
import {
  activePricePromo,
  activePromos,
  nextProduct,
  onAirProduct,
  priceView,
} from "../../app/selectors";
import type { ConnectionStatus } from "../../app/sse";
import type { ClientState } from "../../app/state";
import { useServerNow } from "../../app/store";
import type { ThemeName } from "../../app/theme";
import type { Catalog, Message, MessageKind } from "../../app/types";
import { Countdown, RelativeTime, ThemeToggle, windowRange } from "../../components";
import { chatSignature, isPinnedCorrection, sourceLabels, viewerChat, type ViewerChatRow } from "./chat";
import { readIdentity, saveIdentity, type ViewerIdentity } from "./identity";
import { useCamera } from "./useCamera";
import styles from "./viewer.module.css";

export const POPUP_MS = 4000;
const WINDOW_THRESHOLD = 200; // §12.10: chat lists are windowed beyond 200 rows
const ROW_ESTIMATE = 72;

const cx = (...names: (string | false | null | undefined)[]) => names.filter(Boolean).join(" ");

export interface ViewerViewProps {
  state: ClientState;
  catalog: Catalog | null;
  connection: ConnectionStatus;
  theme: ThemeName;
  embedded?: boolean;
  inputEnabled: boolean;
  cameraEnabled?: boolean;
  onToggleTheme?: () => void;
  onSend?: (identity: ViewerIdentity, text: string) => Promise<unknown>;
}

export function ViewerView({
  state,
  catalog,
  connection,
  theme,
  embedded = false,
  inputEnabled,
  cameraEnabled = false,
  onToggleTheme,
  onSend,
}: ViewerViewProps) {
  const now = useServerNow(state, 1000);
  const offset = state.serverOffsetMs;
  const brand = catalog?.brand ?? "DAON LAB";
  const live = state.session?.status === "live";
  const product = onAirProduct(state, catalog) ?? (state.session?.status === "ended" ? null : nextProduct(state, catalog));
  const price = priceView(state, catalog, product);
  const pricePromo = activePricePromo(state, catalog);
  const promos = activePromos(state, catalog, now);
  const salePromo = promos.find((p) => p.promo.changes_prices) ?? null;
  const otherPromos = promos.filter((p) => !p.promo.changes_prices);
  const corrections = useMemo(
    () => Object.values(state.messages).filter((m) => isPinnedCorrection(m, now)).sort((a, b) => (a.published_at ?? 0) - (b.published_at ?? 0)),
    [state.messages, now],
  );
  const rows = useMemo(() => viewerChat(state, now), [state, now]);
  const camera = useCamera(cameraEnabled && !embedded);
  const popup = useTimeSalePopup(state);

  return (
    <div className={cx(styles.page, !embedded && styles.standalone)} data-theme={theme}>
      {!embedded && onToggleTheme && (
        <div className={styles.pageTools}>
          <ThemeToggle theme={theme} onToggle={onToggleTheme} label="Viewer" />
        </div>
      )}
      <div className={cx(styles.phone, !embedded && styles.framed)} data-testid="viewer-phone">
        {/* video area */}
        <div className={styles.video} data-testid="viewer-video" data-camera={camera.state}>
          {cameraEnabled && !embedded && (
            <video
              ref={camera.videoRef}
              className={cx(styles.cameraFeed, camera.state !== "on" && styles.cameraHidden)}
              autoPlay
              muted
              playsInline
              aria-label="Camera preview"
            />
          )}
          {camera.state !== "on" && (
            <div className={styles.placeholder}>
              <div className={styles.productMark} aria-hidden />
              {product?.eyebrow && <span className={cx("eyebrow", styles.placeholderEyebrow)}>{product.eyebrow}</span>}
              <span className={styles.placeholderName}>{product?.name ?? brand}</span>
              <span className={styles.placeholderNote}>Sample product preview</span>
            </div>
          )}
          <div className={styles.overlayTop}>
            {live ? (
              <span className={styles.liveBadge}>
                <span className={styles.liveDot} aria-hidden />
                LIVE
              </span>
            ) : (
              <span />
            )}
            <span className={styles.brandBadge}>{brand}</span>
          </div>
          {connection === "reconnecting" && (
            <div className={styles.overlayBottom}>
              <span className={styles.reconnecting}>Reconnecting…</span>
            </div>
          )}
        </div>

        {/* D-122: a compact time-sale banner right above the price, not a pop-up over the video */}
        {popup && salePromo && salePromo.promo.promo_id === popup && (
          <div className={styles.saleBanner} role="status" aria-label="Time sale" data-testid="viewer-timesale-popup">
            <span className={styles.popupEyebrow}>TIME SALE</span>
            <span className={styles.saleBannerText}>{popupText(salePromo.promo.viewer_text)}</span>
            <Countdown until={salePromo.endsAt} serverOffsetMs={offset} className={styles.popupCountdown} />
          </div>
        )}
        {/* product strip */}
        {product && price && (
          <div className={styles.strip} data-testid="viewer-product-strip">
            <div className={styles.stripMain}>
              <span className={styles.stripName}>{product.name}</span>
              {price.set && (
                <span className={cx(styles.stripSet, "tabular")} data-testid="viewer-set-price">
                  Set {price.set}
                </span>
              )}
            </div>
            <div className={styles.stripPrice}>
              <div className={styles.priceRow}>
                {price.struck && <span className={styles.priceStruck}>{price.struck}</span>}
                <span className={cx(styles.priceNow, pricePromo && styles.priceSale)} data-testid="viewer-price">
                  {price.current}
                </span>
              </div>
              {salePromo && (
                <span className={styles.saleChip} data-testid="viewer-timesale-chip">
                  TIME SALE <Countdown until={salePromo.endsAt} serverOffsetMs={offset} />
                </span>
              )}
            </div>
          </div>
        )}
        {otherPromos.map((p) => (
          <div key={p.promo.promo_id} className={styles.promoLine}>
            <Gift size={14} aria-hidden />
            <span>{p.promo.viewer_text}</span>
          </div>
        ))}

        {/* pinned notice and correction notices */}
        {(state.session?.pinned_notice || corrections.length > 0) && (
          <div className={styles.notices}>
            {state.session?.pinned_notice && (
              <div className={styles.notice} data-testid="viewer-pinned-notice">
                <Pin size={14} className={styles.noticeIcon} aria-hidden />
                <span>{state.session.pinned_notice}</span>
              </div>
            )}
            {corrections.map((m) => (
              <div key={m.message_id} className={styles.notice} data-testid="viewer-correction-notice">
                <span>
                  <span className={styles.noticeLabel}>Correction</span>
                  {m.text}
                </span>
              </div>
            ))}
          </div>
        )}

        <ChatList rows={rows} brand={brand} serverOffsetMs={offset} catalog={catalog} />

        <Composer enabled={inputEnabled && Boolean(onSend)} onSend={onSend} />


      </div>
    </div>
  );
}

/** The card already carries the "TIME SALE" label; drop it from the start of the promo text. */
export function popupText(viewerText: string): string {
  return viewerText.replace(/^\s*TIME SALE\s*[·:\-–—]?\s*/i, "") || viewerText;
}

/** Shows the pop-up when a price-changing promo starts while the page is open (§12.5); it closes
 * after 4 s and the countdown stays as the chip in the product strip. */
function useTimeSalePopup(state: ClientState): string | null {
  const promoId = state.session?.active_promo_id ?? null;
  const seen = useRef<string | null | undefined>(undefined);
  const [popup, setPopup] = useState<string | null>(null);

  useEffect(() => {
    if (!state.loaded) return;
    if (seen.current === undefined) {
      seen.current = promoId; // already running when the page opened: chip only
      return;
    }
    if (promoId && promoId !== seen.current) setPopup(promoId);
    if (!promoId) setPopup(null);
    seen.current = promoId;
  }, [state.loaded, promoId]);

  useEffect(() => {
    if (!popup) return;
    const t = setTimeout(() => setPopup(null), POPUP_MS);
    return () => clearTimeout(t);
  }, [popup]);

  return popup;
}

// ---- chat ----------------------------------------------------------------------------------------

const BADGE: Record<MessageKind, { label: string; icon: "ai" | "host" | "brand" | null }> = {
  ai_answer: { label: "AI answer", icon: "ai" },
  host_answer: { label: "Host answer", icon: "host" },
  brand_answer: { label: "DAON LAB", icon: "brand" },
  notice: { label: "DAON LAB", icon: "brand" },
  correction_notice: { label: "Correction", icon: null },
};

function Badge({ kind, brand }: { kind: MessageKind; brand: string }) {
  const b = BADGE[kind];
  const label = b.icon === "brand" ? brand : b.label;
  return (
    <span className={cx(styles.badge, styles[`badge_${kind}`])}>
      {b.icon === "ai" && <Sparkles size={12} aria-hidden />}
      {b.icon === "host" && <Mic size={12} aria-hidden />}
      {b.icon === "brand" && <BadgeCheck size={12} aria-hidden />}
      {label}
    </span>
  );
}

function ChatList({
  rows,
  brand,
  serverOffsetMs,
  catalog,
}: {
  rows: ViewerChatRow[];
  brand: string;
  serverOffsetMs: number;
  catalog: Catalog | null;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const pinned = useRef(true); // following the newest message until the viewer scrolls up
  const [view, setView] = useState({ top: 0, height: 600 });
  const signature = chatSignature(rows);
  const windowed = rows.length > WINDOW_THRESHOLD;

  useLayoutEffect(() => {
    const el = ref.current;
    if (el && pinned.current) el.scrollTop = el.scrollHeight;
  }, [signature]);

  const onScroll = () => {
    const el = ref.current;
    if (!el) return;
    pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 32;
    if (windowed) setView({ top: el.scrollTop, height: el.clientHeight || 600 });
  };

  const [first, last] = windowed ? windowRange(rows.length, view.top, view.height, ROW_ESTIMATE) : [0, rows.length];
  return (
    <div ref={ref} className={styles.chat} onScroll={onScroll} data-testid="viewer-chat" aria-live="polite">
      {rows.length === 0 && <p className={styles.chatEmpty}>Chat will appear here.</p>}
      {windowed && <div style={{ height: first * ROW_ESTIMATE }} aria-hidden />}
      {rows.slice(first, last).map((row) =>
        row.kind === "comment" ? (
          <div key={row.key} className={styles.row} data-testid={`viewer-comment-${row.comment.comment_id}`}>
            <span className={styles.avatar} aria-hidden>
              {(row.comment.author_name.trim()[0] ?? "?").toUpperCase()}
            </span>
            <div className={styles.rowBody}>
              <div className={styles.rowHead}>
                <span className={styles.author}>{row.comment.author_name}</span>
                <span className={styles.time}>
                  <RelativeTime at={row.comment.received_at} serverOffsetMs={serverOffsetMs} />
                </span>
              </div>
              <p className={styles.text}>{row.comment.text}</p>
              {row.replies.map((r) => (
                <Reply key={r.message.message_id} message={r.message} brand={brand} catalog={catalog} />
              ))}
              {row.alsoAnswered && row.replies.length === 0 && (
                <p className={styles.answeredAbove} data-testid={`viewer-also-answered-${row.comment.comment_id}`}>
                  ↳ Also answered: @{row.comment.author_name}
                </p>
              )}
            </div>
          </div>
        ) : (
          <div key={row.key} className={styles.systemRow}>
            <Reply message={row.message} brand={brand} catalog={catalog} />
          </div>
        ),
      )}
      {windowed && <div style={{ height: (rows.length - last) * ROW_ESTIMATE }} aria-hidden />}
    </div>
  );
}

function Reply({
  message,
  brand,
  catalog,
}: {
  message: Message;
  brand: string;
  catalog: Catalog | null;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className={styles.reply} data-testid={`viewer-reply-${message.message_id}`} data-kind={message.kind}>
      <span className={styles.replyArrow} aria-hidden>
        ↳
      </span>
      <div className={styles.replyBody}>
        <Badge kind={message.kind} brand={brand} />
        <p className={styles.text}>{message.text}</p>
        {message.kind === "ai_answer" &&
          sourceLabels(message).map((label) => (
            <button
              key={label}
              type="button"
              className={styles.source}
              onClick={() => setOpen((o) => !o)}
              aria-expanded={open}
              data-testid="viewer-source"
            >
              {label}
            </button>
          ))}
        {open && <SourceDetails message={message} catalog={catalog} />}
      </div>
    </div>
  );
}

/** D-122: the source of an AI answer, expanded inline under the reply. */
function SourceDetails({ message, catalog }: { message: Message; catalog: Catalog | null }) {
  return (
    <div className={styles.sourceDetails} data-testid="viewer-source-details">
      {message.citations.map((c) => {
        const passage = catalog?.passages?.[c.passage_id];
        const product = catalog?.products.find((p) => p.product_id === passage?.product_id);
        const section = passage?.section ?? c.section ?? (c.passage_id.startsWith("PROMO#") ? "Active promotion" : "");
        return (
          <div key={`${c.passage_id}:${c.quote}`} className={styles.citation}>
            <span className={styles.citationMeta}>{[product?.name, section].filter(Boolean).join(" · ")}</span>
            <span className={styles.quote}>“{c.quote}”</span>
          </div>
        );
      })}
    </div>
  );
}

// ---- input ---------------------------------------------------------------------------------------

function Composer({
  enabled,
  onSend,
}: {
  enabled: boolean;
  onSend?: (identity: ViewerIdentity, text: string) => Promise<unknown>;
}) {
  const [identity, setIdentity] = useState<ViewerIdentity | null>(() => (enabled ? readIdentity() : null));
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (enabled && !identity) setIdentity(readIdentity());
  }, [enabled, identity]);

  if (!enabled) {
    return (
      <div className={styles.composer}>
        <input
          className={styles.input}
          disabled
          placeholder="Chat is read-only in this demo"
          aria-label="Chat is read-only in this demo"
          data-testid="viewer-input"
        />
        <button type="button" className={styles.send} disabled aria-label="Send">
          <Send size={16} aria-hidden />
        </button>
      </div>
    );
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const text = value.trim();
    if (!text) return;
    if (!identity) {
      setIdentity(saveIdentity(text));
      setValue("");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSend?.(identity, text);
      setValue("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {error && (
        <p className={styles.composerError} role="alert">
          {error}
        </p>
      )}
      <form className={styles.composer} onSubmit={submit}>
        <input
          className={styles.input}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={identity ? `Chat as ${identity.name}` : "Your display name"}
          aria-label={identity ? "Message" : "Your display name"}
          maxLength={identity ? 300 : 40}
          disabled={busy}
          data-testid="viewer-input"
        />
        <button
          type="submit"
          className={styles.send}
          disabled={busy || !value.trim()}
          aria-label={identity ? "Send" : "Join chat"}
        >
          <Send size={16} aria-hidden />
        </button>
      </form>
    </>
  );
}
