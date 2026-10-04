// Audience questions and the AI PD card in one panel (D-127, option D, replaces the separate card slot
// of D-113): a question card opens in place of its own row, so the question never shows twice; any
// other card goes on top. A shown card has a fixed height, the panel never moves, and nothing animates.
import { MessagesSquare, Pin, Users } from "lucide-react";
import { useRef } from "react";

import { useT } from "../../app/i18n";
import type { HostSlotView } from "../../app/selectors";
import type { PdCard as PdCardType } from "../../app/types";
import { PdCard, QUESTION_KINDS } from "./PdCard";
import styles from "./host.module.css";

const cx = (...n: (string | false | null | undefined)[]) => n.filter(Boolean).join(" ");

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

/** D-113: one compact row per waiting question. The answer itself appears only on the AI PD card. */
function Item({ view }: { view: HostSlotView }) {
  const t = useT();
  const { group, pending, waiting } = view;
  const windowMs = postingWindow(pending);
  return (
    <>
      <div className={styles.wRow}>
        <span className={styles.qIndex}>{String(view.index).padStart(2, "0")}</span>
        <span className={styles.wText}>{group.canonical_question}</span>
        <span className={cx(styles.qAsking, "tabular")}>
          <Users aria-hidden />
          {group.unique_author_ids.length}
        </span>
        <span className={cx(styles.wState, waiting === "On your card" && styles.wStateOn)} data-testid="host-question-state">
          {t(waiting)}
        </span>
        {view.slot.pinned && (
          <span className={cx(styles.qTag, styles.qTagPd)}>
            <Pin aria-hidden />
            {t("From your PD")}
          </span>
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
}: {
  slots: HostSlotView[];
  card?: PdCardType | null;
  onDismiss?: (cardId: string) => void;
  /** a HIGH alert is up: one instruction on screen, so the Q hint gives way */
  correcting?: boolean;
}) {
  const t = useT();
  const isQuestion = !!card && QUESTION_KINDS.has(card.kind);
  const inPlace = isQuestion ? slots.find((s) => s.group.group_id === card.ref_id) : undefined;
  // A question card that is done often loses its row at the same moment (answered). It keeps the row's
  // place for its short "done" fade, so the list moves once, when the card goes.
  const lastAt = useRef<{ cardId: string; index: number } | null>(null);
  if (card && inPlace) lastAt.current = { cardId: card.card_id, index: slots.indexOf(inPlace) };
  const keptAt = card && isQuestion && !inPlace && card.status === "done" && lastAt.current?.cardId === card.card_id
    ? Math.min(lastAt.current.index, slots.length) : null;
  // other cards (and a question card whose row is not on the list) go on top; a done question card
  // with no known place is not shown again
  const onTop = card && !inPlace && !(isQuestion && card.status === "done") ? card : null;
  // the "Posting answer…" bar of the question goes inside the card's fixed box, so nothing grows
  const cardBox = (c: PdCardType, posting?: HostSlotView["pending"]) => (
    <div className={styles.pdSlot} data-testid="host-pd-slot">
      <PdCard card={c} onDismiss={onDismiss} />
      {posting && <Posting windowMs={postingWindow(posting)} />}
    </div>
  );
  const rows = slots.map((item) =>
    item === inPlace && card ? (
      <div key={item.group.group_id} data-testid={`host-question-${item.group.group_id}`}>
        {cardBox(card, item.pending)}
      </div>
    ) : (
      <article key={item.group.group_id} data-testid={`host-question-${item.group.group_id}`} className={styles.question}>
        <Item view={item} />
      </article>
    ),
  );
  if (keptAt !== null && card) rows.splice(keptAt, 0, <div key={`done-${card.card_id}`}>{cardBox(card)}</div>);

  return (
    <section className={styles.card} data-testid="host-questions" aria-label={t("Audience questions")}>
      <header className={styles.cardHeader}>
        <span className={styles.cardTitle}>
          <MessagesSquare aria-hidden />
          {t("AI PD · QUESTIONS")}
        </span>
        <span className={styles.cardMeta} data-testid="host-questions-hint">
          {correcting ? (
            t("Finish the correction first")
          ) : (
            <>
              <kbd className={styles.pdKbd}>Q</kbd> {t("take the top one now")}
            </>
          )}
        </span>
      </header>
      <div className={styles.questions}>
        {onTop && cardBox(onTop)}
        {rows}
        {!card && !slots.length && <p className={styles.panelEmpty}>{t("No questions waiting.")}</p>}
      </div>
      <footer className={styles.cardFooter}>
        <span className={styles.footerNote}>
          <Pin aria-hidden />
          {t("Questions stay in place while you speak")}
        </span>
      </footer>
    </section>
  );
}
