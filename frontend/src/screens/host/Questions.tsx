// Audience questions and the AI PD card in one panel (D-127, option D, replaces the separate card slot
// of D-113): a question card opens in place of its own row, so the question never shows twice; any
// other card goes on top. A shown card has a fixed height, the panel never moves, and nothing animates.
import { MessagesSquare, Pin, Users } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, type RefObject } from "react";

import { useT } from "../../app/i18n";
import { Watching } from "../../components";
import type { HostSlotView } from "../../app/selectors";
import type { PdCard as PdCardType } from "../../app/types";
import { PdCard } from "./PdCard";
import styles from "./host.module.css";

const cx = (...n: (string | false | null | undefined)[]) => n.filter(Boolean).join(" ");

const PD_MIN_ZOOM = 0.8; // as the prompter's: below this the line to say gets too small to read

/** D-182: the host must always read the whole line to say. The waiting rows give way first (the list scrolls and
 *  keeps the card in view); then the card's text shrinks step by step down to PD_MIN_ZOOM; if it still does not fit,
 *  the card box grows, and the panel asks the host grid for the room (the min-height of its row, as the prompter's
 *  useFit does). */
function usePdFit(
  section: RefObject<HTMLElement>,
  list: RefObject<HTMLDivElement>,
  slot: RefObject<HTMLDivElement>,
  cardId: string | null,
) {
  const run = useRef(() => {});
  // D-469: the screen re-renders every 250 ms; the card is scrolled into view only when it is new or its box changed
  // height, so a list the host scrolled stays where it is
  const shown = useRef<{ id: string | null; height: number }>({ id: null, height: 0 });
  run.current = () => {
    const sec = section.current;
    const holder = sec?.parentElement; // the questions row of the host grid
    if (!sec || !holder) return;
    holder.style.minHeight = "";
    const box = slot.current;
    const rows = list.current;
    const card = box?.firstElementChild as HTMLElement | null | undefined;
    if (!box || !rows || !card) {
      shown.current = { id: null, height: 0 };
      return;
    }
    card.style.zoom = "1";
    box.style.height = "";
    if (!(box.clientHeight > 0)) return; // no layout (tests, hidden pane)
    const fits = () => box.scrollHeight <= box.clientHeight + 1;
    let z = 1;
    while (!fits() && z > PD_MIN_ZOOM) {
      z = Math.round((z - 0.05) * 100) / 100;
      card.style.zoom = String(z);
    }
    if (!fits()) {
      const b = getComputedStyle(box);
      box.style.height = `${Math.ceil(box.scrollHeight + parseFloat(b.borderTopWidth) + parseFloat(b.borderBottomWidth))}px`;
    }
    const need = sec.offsetHeight - rows.clientHeight + box.offsetHeight; // header and footer, plus the card box
    if (need > sec.offsetHeight + 1) holder.style.minHeight = `${Math.ceil(need)}px`;
    const before = shown.current;
    shown.current = { id: cardId, height: box.offsetHeight };
    if (before.id === cardId && before.height === box.offsetHeight) return;
    const r = rows.getBoundingClientRect();
    const c = box.getBoundingClientRect();
    if (c.top < r.top) rows.scrollTop -= r.top - c.top;
    else if (c.bottom > r.bottom) rows.scrollTop += c.bottom - r.bottom;
  };
  useLayoutEffect(() => run.current());
  useEffect(() => {
    if (!section.current || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => run.current());
    ro.observe(section.current);
    return () => ro.disconnect();
  }, [section]);
}

function Posting({ windowMs }: { windowMs: number }) {
  const t = useT();
  return (
    <div className={styles.posting} role="status">
      {t("Posting answer…")}
      <span className={styles.progress} aria-hidden>
        <span className={styles.progressBar} style={{ animationDuration: `${windowMs}ms` }} />
      </span>
    </div>
  );
}

function postingWindow(pending: HostSlotView["pending"]): number {
  return pending?.publish_at ? Math.max(500, pending.publish_at - pending.created_at) : 2000;
}

/** D-469: the state pill's look, from the question's own fields (never from its label text) */
function stateTone({ group, answer }: HostSlotView): string | undefined {
  if (group.status === "composing") return styles.pillDrafting;
  if (group.status === "needs_review" && group.route_reason === "unresolved_product") return undefined;
  if (group.status === "auto_answered") return styles.pillReadout;
  return answer ? styles.pillReady : undefined;
}

/** D-113: one compact row per waiting question. D-384 (user): its suggested answer shows under it at once; D-431: a
 *  read-out question too (no AI PD card supplies it since D-429). D-469 (user): "Q1" and an "A1" chip in a label
 *  column, question and answer starting at the same x; no answer yet keeps the answer line's height. */
function Item({ view }: { view: HostSlotView }) {
  const t = useT();
  const { group, pending, waiting, answer } = view;
  // the first line of the suggested reply (verified only), so the host can prepare while waiting
  const preview = answer?.text.split(/\r?\n/).find((l) => l.trim())?.trim() ?? null;
  const windowMs = postingWindow(pending);
  return (
    <>
      <div className={styles.qa}>
        <span className={styles.qLabel}>Q{view.index}</span>
        <div className={styles.wRow}>
          <span className={styles.wText}>{group.canonical_question}</span>
          <span className={cx(styles.pill, styles.pillCount, "tabular")}>
            <Users aria-hidden />
            {group.unique_author_ids.length}
          </span>
          <span className={cx(styles.pill, stateTone(view))} data-testid="host-question-state">
            {t(waiting)}
          </span>
          {view.slot.pinned && (
            <span className={styles.pill}>
              <Pin aria-hidden />
              {t("From your PD")}
            </span>
          )}
        </div>
        {preview ? (
          <>
            <span className={styles.aLabel}>A{view.index}</span>
            <p className={styles.wPreview} data-testid="host-question-preview">
              {preview}
            </p>
          </>
        ) : (
          <>
            <span className={styles.aNone} aria-hidden />
            <span className={styles.aEmpty} aria-hidden />
          </>
        )}
      </div>
      {pending && <Posting windowMs={windowMs} />}
    </>
  );
}

export function Questions({
  slots,
  card,
  onDismiss,
  correcting = false,
  unanswered = 0,
  audience = null,
}: {
  slots: HostSlotView[];
  card?: PdCardType | null;
  onDismiss?: (cardId: string) => void;
  /** an alert is up: AI PD cards wait (D-161) */
  correcting?: boolean;
  /** D-178: solo show: how many questions only the operator could answer (no card, nothing posted) */
  unanswered?: number;
  /** D-477: how many are watching; null hides it */
  audience?: number | null;
}) {
  const t = useT();
  const sectionRef = useRef<HTMLElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const slotRef = useRef<HTMLDivElement>(null);
  usePdFit(sectionRef, listRef, slotRef, card?.card_id ?? null);
  // D-429: the AI PD makes no question cards; its other cards (promo, switch, wrap-up, shout-out) go on top
  const cardBox = (c: PdCardType) => (
    <div ref={slotRef} className={styles.pdSlot} data-testid="host-pd-slot">
      <PdCard card={c} onDismiss={onDismiss} />
    </div>
  );
  const rows = slots.map((item) => (
    <article key={item.group.group_id} data-testid={`host-question-${item.group.group_id}`} className={styles.question}>
      <Item view={item} />
    </article>
  ));

  return (
    <section ref={sectionRef} className={styles.card} data-testid="host-questions" aria-label={t("Audience questions")}>
      <header className={styles.cardHeader}>
        <span className={styles.cardTitle}>
          <MessagesSquare aria-hidden />
          {t("AI PD · QUESTIONS")}
        </span>
        {correcting && (  // D-429: no Q key hint (the host is hands-free)
          <span className={styles.cardMeta} data-testid="host-questions-hint">
            {t("Questions resume after the correction")}
          </span>
        )}
        <Watching count={audience} className={styles.cardWatching} />
      </header>
      <div ref={listRef} className={styles.questions}>
        {card && cardBox(card)}
        {rows}
        {!card && !slots.length && <p className={styles.panelEmpty}>{t("No questions waiting.")}</p>}
      </div>
      <footer className={styles.cardFooter}>
        <span className={styles.footerNote}>
          <Pin aria-hidden />
          {t("Questions stay in place while you speak")}
        </span>
        {unanswered > 0 && (
          <span className="tabular" data-testid="host-unanswered">
            {unanswered === 1 ? t("1 unanswered question") : t("{n} unanswered questions", { n: unanswered })}
          </span>
        )}
      </footer>
    </section>
  );
}
