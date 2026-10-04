// Audience questions (§12.3.4, D-113): the host's waiting list, one compact row per question with its
// state; the answer appears only on the AI PD card. "Posting answer…" window and stable positions
// (FLIP moves, fade on replace).
import { Inbox, MessagesSquare, Pin, Users } from "lucide-react";
import { useRef } from "react";

import { useT } from "../../app/i18n";
import type { HostSlotView } from "../../app/selectors";
import { useFlip, usePresence } from "./hooks";
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

/** D-113: one compact row per waiting question. The answer itself appears only on the AI PD card. */
function Item({ view }: { view: HostSlotView }) {
  const t = useT();
  const { group, pending, waiting } = view;
  const windowMs = pending?.publish_at ? Math.max(500, pending.publish_at - pending.created_at) : 2000;
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

export function Questions({ slots }: { slots: HostSlotView[] }) {
  const t = useT();
  const listRef = useRef<HTMLDivElement>(null);
  const shown = usePresence(slots, (s) => s.group.group_id);
  useFlip(listRef, [slots.map((s) => s.group.group_id).join("|")]);

  return (
    <section className={styles.card} data-testid="host-questions" aria-label={t("Audience questions")}>
      <header className={styles.cardHeader}>
        <span className={styles.cardTitle}>
          <MessagesSquare aria-hidden />
          {t("AUDIENCE QUESTIONS")}
        </span>
        <span className={styles.cardMeta}>
          <kbd className={styles.pdKbd}>Q</kbd> {t("take the top one now")}
        </span>
      </header>
      {shown.length ? (
        <div className={styles.questions} ref={listRef}>
          {shown.map(({ item, leaving }) => (
            <article
              key={item.group.group_id}
              data-flip-key={item.group.group_id}
              data-testid={`host-question-${item.group.group_id}`}
              className={cx(styles.question, leaving && styles.leaving)}
              aria-hidden={leaving || undefined}
            >
              <Item view={item} />
            </article>
          ))}
        </div>
      ) : (
        <div className={styles.emptyQuestions}>
          <Inbox aria-hidden />
          <span className={styles.emptyTitle}>{t("You have the floor.")}</span>
          <span className={styles.emptySub}>{t("Your next audience question will appear here.")}</span>
        </div>
      )}
      <footer className={styles.cardFooter}>
        <span className={styles.footerNote}>
          <Pin aria-hidden />
          {t("Questions stay in place while you speak")}
        </span>
      </footer>
    </section>
  );
}
