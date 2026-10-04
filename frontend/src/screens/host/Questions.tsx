// Audience questions card (§12.3.4): the host's top N, the suggested answer under item 01, the
// "Posting answer…" window, and stable positions (FLIP moves, fade on replace).
import { CheckCheck, FileText, Inbox, MessagesSquare, Mic, Pin, Sparkles, Users } from "lucide-react";
import { useRef } from "react";

import { useT } from "../../app/i18n";
import type { HostSlotView } from "../../app/selectors";
import type { Catalog } from "../../app/types";
import { answerSource } from "./hostSelectors";
import { useFlip, usePresence } from "./hooks";
import styles from "./host.module.css";

const cx = (...n: (string | false | null | undefined)[]) => n.filter(Boolean).join(" ");

function Tag({ tag }: { tag: HostSlotView["tag"] }) {
  const t = useT();
  if (tag === "AI answered")
    return (
      <span className={cx(styles.qTag, styles.qTagAi)}>
        <CheckCheck aria-hidden />
        {t("AI answered")}
      </span>
    );
  if (tag === "From your PD")
    return (
      <span className={cx(styles.qTag, styles.qTagPd)}>
        <Pin aria-hidden />
        {t("From your PD")}
      </span>
    );
  return (
    <span className={styles.qTag}>
      <Mic aria-hidden />
      {t("For you")}
    </span>
  );
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

function Item({ view, first, catalog }: { view: HostSlotView; first: boolean; catalog: Catalog | null }) {
  const t = useT();
  const { group, answer, pending, tag } = view;
  const asking = group.unique_author_ids.length;
  const source = answerSource(catalog, answer);
  const windowMs = pending?.publish_at ? Math.max(500, pending.publish_at - pending.created_at) : 2000;
  return (
    <>
      <div className={styles.qMeta}>
        <span className={styles.qIndex}>{String(view.index).padStart(2, "0")}</span>
        <span className={styles.qAsking}>
          <Users aria-hidden />
          <span className="tabular">{t("{n} asking", { n: asking })}</span>
        </span>
        <Tag tag={tag} />
      </div>
      <div className={cx(styles.qText, !first && styles.qTextSmall)}>{group.canonical_question}</div>
      {answer && first && (
        <div className={styles.suggest}>
          <span className={styles.suggestLabel}>
            <Sparkles aria-hidden />
            {t("SUGGESTED ANSWER")}
          </span>
          <div className={styles.suggestText}>{answer.text}</div>
          {source && (
            <span className={styles.sourceChip}>
              <FileText aria-hidden />
              {source}
            </span>
          )}
        </div>
      )}
      {answer && !first && <div className={styles.suggestLine}>{answer.text}</div>}
      {pending && <Posting windowMs={windowMs} />}
    </>
  );
}

export function Questions({ slots, catalog }: { slots: HostSlotView[]; catalog: Catalog | null }) {
  const t = useT();
  const listRef = useRef<HTMLDivElement>(null);
  const shown = usePresence(slots, (s) => s.group.group_id);
  useFlip(listRef, [slots.map((s) => s.group.group_id).join("|")]);
  const filled = slots.length;
  const firstId = slots[0]?.group.group_id;

  return (
    <section className={styles.card} data-testid="host-questions" aria-label={t("Audience questions")}>
      <header className={styles.cardHeader}>
        <span className={styles.cardTitle}>
          <MessagesSquare aria-hidden />
          {t("AUDIENCE QUESTIONS")}
        </span>
        <span className={styles.cardMeta}>
          <span className={styles.topChip}>{t("TOP {n}", { n: filled })}</span>
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
              <Item view={item} first={item.group.group_id === firstId} catalog={catalog} />
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
