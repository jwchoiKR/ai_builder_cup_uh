// Comment stream (§12.4.8): newest first, product and kind chips, filtered comments with Unhide.
import { useState } from "react";

import { api } from "../../app/api";
import { useT } from "../../app/i18n";
import { hiddenComments, productById, relativeTime } from "../../app/selectors";
import type { Comment } from "../../app/types";
import { Button, Chip, VirtualList } from "../../components";
import { useArrivalDot } from "./attention";
import { useAction, useOperator } from "./context";
import { SET_INTENT, sentenceCase, setLabel, setOfferFor } from "./model";
import styles from "./operator.module.css";

const KIND_LABEL: Record<Comment["kind"], string> = {
  question: "Question",
  reaction: "Reaction",
  pending: "Checking",
  hide: "Hidden",
};

export function CommentStream() {
  const t = useT();
  const { state } = useOperator();
  const [showFiltered, setShowFiltered] = useState(false);
  const hidden = hiddenComments(state);
  const visible = Object.values(state.comments)
    .filter((c) => c.visibility === "visible")
    .sort((a, b) => b.received_at - a.received_at);
  const items = showFiltered ? hidden : visible;
  // a comment hidden while the operator is not looking at the hidden list: a dot until it is opened
  const hiddenDot = useArrivalDot(hidden.map((c) => c.comment_id).sort(), state.loaded, showFiltered);
  return (
    <section className={[styles.block, styles.stream].join(" ")} data-testid="op-comment-stream" aria-label={t("Comment stream")}>
      <div className={styles.blockHeader}>
        <h2 className={styles.blockTitle}>{t("Comment stream")}</h2>
        <button
          type="button"
          className={[styles.tab, showFiltered && styles.tabActive].filter(Boolean).join(" ")}
          aria-pressed={showFiltered}
          onClick={() => setShowFiltered((v) => !v)}
        >
          {t("Hidden comments ({n})", { n: hidden.length })}
          {hiddenDot && <span className={styles.attnDot} data-testid="op-hidden-dot" role="img" aria-label={t("New hidden comment")} />}
        </button>
      </div>
      {items.length === 0 ? (
        <p className={styles.empty}>{showFiltered ? t("No hidden comments.") : t("No comments yet.")}</p>
      ) : (
        <VirtualList
          className={styles.streamList}
          items={items}
          rowHeight={52}
          getKey={(c) => c.comment_id}
          renderItem={(c) => <CommentRow comment={c} />}
        />
      )}
    </section>
  );
}

/** A comment in another language: its language tag and triage's English reading, under the original text. */
export function CommentTranslation({ comment: c }: { comment: Comment }) {
  const t = useT();
  if (!c.translation_en) return null;
  return (
    <div className={styles.translation} data-testid={`op-comment-translation-${c.comment_id}`}>
      {c.language && (
        <span className={styles.langTag} title={t("Comment language")}>
          {c.language.toUpperCase()}
        </span>
      )}
      <span lang="en">{c.translation_en}</span>
    </div>
  );
}

function CommentRow({ comment: c }: { comment: Comment }) {
  const t = useT();
  const { sid, state, catalog, now, focusGroup } = useOperator();
  const act = useAction();
  const analysis = state.analyses[c.comment_id];
  const group = state.groups[c.group_id ?? ""];
  // the one-line reason triage gave for hiding it, so a wrong hide is clear at a glance
  const hideReason = typeof analysis?.output?.reason === "string" ? analysis.output.reason : null;
  const product = productById(catalog, analysis?.product_id ?? group?.product_id);
  const intent = group?.intent ?? (analysis?.output as { intent?: string } | undefined)?.intent;
  // A set-price question is about the set: show the set label, not one product.
  const set = intent === SET_INTENT ? setOfferFor(catalog, product?.product_id) : null;
  const setName = set ? setLabel(set) : undefined;
  const productChip = setName ?? (product ? product.short_name.replace(/^the /, "") : null);
  return (
    <div className={styles.commentRow} data-testid={`op-comment-${c.comment_id}`}>
      <div className={styles.commentLine}>
        <span className={styles.author}>{c.author_name}</span>
        <span className={styles.commentText}>{c.text}</span>
        <span className={["tabular", styles.muted].join(" ")}>{relativeTime(c.received_at, now)}</span>
      </div>
      <CommentTranslation comment={c} />
      <div className={styles.commentChips}>
        {c.visibility === "hidden" ? (
          <>
            <Chip tone="risk">{t(sentenceCase((c.hide_category ?? "hidden").replace(/_/g, " ")))}</Chip>
            {hideReason && (
              <span className={styles.hideReason} title={hideReason} data-testid={`op-hide-reason-${c.comment_id}`}>
                {hideReason}
              </span>
            )}
            <Button size="sm" disabled={act.busy} onClick={() => act.run(() => api.unhide(sid, c.comment_id))}>
              {t("Unhide")}
            </Button>
          </>
        ) : (
          <>
            {c.armor === "unscreened" ? <Chip tone="risk">{t("Unscreened")}</Chip> : <Chip>{t(KIND_LABEL[c.kind])}</Chip>}
            {productChip && <Chip tone="accent">{productChip}</Chip>}
            {c.kind === "question" && c.group_id && (
              <button type="button" className={styles.linkish} onClick={() => focusGroup(c.group_id)}>
                {t("Open question")}
              </button>
            )}
          </>
        )}
      </div>
      {act.error && <p className={styles.error}>{act.error}</p>}
    </div>
  );
}
