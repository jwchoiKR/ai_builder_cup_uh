import { Check, Sparkles, User } from "lucide-react";

import { useT } from "../../app/i18n";
import type { PdCard as PdCardType, PdCardKind } from "../../app/types";
import styles from "./host.module.css";

const cx = (...n: (string | false | null | undefined)[]) => n.filter(Boolean).join(" ");

const KIND_LABELS: Record<PdCardKind, string> = {
  answer_question: "Answer",
  read_question: "Read out",
  clarify_product: "Which product?",
  shout_out: "Shout-out",
  cover_point: "Say this point",
  promo: "Promo",
  wrap_up: "Wrap up",
  switch_product: "Next product",
};

/** The server words a read-out card "{n} people asked: {question}". Say it right for one viewer. */
const ASKED = /^(\d+) people asked: ([\s\S]*)$/;

export function askedDetail(detail: string, t: (en: string, vars?: Record<string, string | number>) => string): { text: string; counted: boolean } {
  const m = ASKED.exec(detail);
  if (!m) return { text: detail, counted: false };
  const n = Number(m[1]);
  return { text: `${n === 1 ? t("1 viewer asked") : t("{n} viewers asked", { n })}: ${m[2]}`, counted: true };
}

export const QUESTION_KINDS = new Set<PdCardKind>(["answer_question", "read_question", "clarify_product"]);

export function PdCard({
  card,
  onDismiss,
}: {
  card: PdCardType;
  onDismiss?: (cardId: string) => void;
}) {
  const t = useT();
  const done = card.status === "done";
  const question = QUESTION_KINDS.has(card.kind);
  const kindLabel = t(KIND_LABELS[card.kind] ?? "Direction");
  const sourceLabel = card.source === "ai" ? "AI PD" : "PD";
  const asked = card.detail ? askedDetail(card.detail, t) : null;

  return (
    <div
      className={cx(styles.pdCard, done && styles.pdCardDone)}
      data-testid="host-pd-card"
      data-kind={card.kind}
      data-status={card.status}
      data-source={card.source}
      role="region"
      aria-label={t("AI PD card")}
    >
      <div className={styles.pdTop}>
        <div className={styles.pdHeaderLeft}>
          <span className={styles.pdSource}>
            {card.source === "ai" ? (
              <Sparkles aria-hidden className={styles.pdSourceIcon} />
            ) : (
              <User aria-hidden className={styles.pdSourceIcon} />
            )}
            {sourceLabel}
          </span>
          <span className={styles.pdKind} data-testid="host-pd-kind">
            {kindLabel}
          </span>
        </div>
        <div className={styles.pdHeaderRight}>
          {done ? (
            <span className={styles.pdDoneTag} data-testid="host-pd-done">
              <Check className={styles.pdCheck} aria-hidden />
              <span>{t("Done")}</span>
            </span>
          ) : (
            <button
              type="button"
              className={styles.pdDismiss}
              onClick={() => onDismiss?.(card.card_id)}
              aria-label={t("Dismiss (N)")}
              title={t("Dismiss (N)")}
              data-testid="host-pd-dismiss"
            >
              <span>{t("Dismiss")}</span>
              <kbd className={styles.pdKbd}>N</kbd>
            </button>
          )}
        </div>
      </div>
      {question && card.detail && (
        // D-113: the question and how many asked, above the answer
        <div className={styles.pdQuestion} data-testid="host-pd-question">
          {asked?.text}
          {card.askers && !asked?.counted ? <span className={styles.pdAskers}>{t("{n} asking", { n: card.askers })}</span> : null}
        </div>
      )}
      <div className={cx(styles.pdSay, question && styles.pdSayAnswer)} data-testid="host-pd-say">
        {card.say}
      </div>
      {!question && card.detail && (
        <div className={styles.pdDetail} data-testid="host-pd-detail">
          {card.detail}
        </div>
      )}
    </div>
  );
}
