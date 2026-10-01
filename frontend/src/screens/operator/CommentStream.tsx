// Comment stream (§12.4.8): newest first, product and kind chips, filtered comments with Unhide.
import { useState } from "react";

import { api } from "../../app/api";
import { hiddenComments, productById, relativeTime } from "../../app/selectors";
import type { Comment } from "../../app/types";
import { Button, Chip, VirtualList } from "../../components";
import { useAction, useOperator } from "./context";
import { SET_INTENT, sentenceCase, setOfferFor } from "./model";
import styles from "./operator.module.css";

const KIND_LABEL: Record<Comment["kind"], string> = {
  question: "Question",
  reaction: "Reaction",
  pending: "Checking",
  hide: "Hidden",
};

export function CommentStream() {
  const { state } = useOperator();
  const [showFiltered, setShowFiltered] = useState(false);
  const hidden = hiddenComments(state);
  const visible = Object.values(state.comments)
    .filter((c) => c.visibility === "visible")
    .sort((a, b) => b.received_at - a.received_at);
  const items = showFiltered ? hidden : visible;
  return (
    <section className={[styles.block, styles.stream].join(" ")} data-testid="op-comment-stream" aria-label="Comment stream">
      <div className={styles.blockHeader}>
        <h2 className={styles.blockTitle}>Comment stream</h2>
        <button
          type="button"
          className={[styles.tab, showFiltered && styles.tabActive].filter(Boolean).join(" ")}
          aria-pressed={showFiltered}
          onClick={() => setShowFiltered((v) => !v)}
        >
          Show filtered ({hidden.length})
        </button>
      </div>
      {items.length === 0 ? (
        <p className={styles.empty}>{showFiltered ? "Nothing filtered." : "No comments yet."}</p>
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

function CommentRow({ comment: c }: { comment: Comment }) {
  const { sid, state, catalog, now, focusGroup } = useOperator();
  const act = useAction();
  const analysis = state.analyses[c.comment_id];
  const group = state.groups[c.group_id ?? ""];
  const product = productById(catalog, analysis?.product_id ?? group?.product_id);
  const intent = group?.intent ?? (analysis?.output as { intent?: string } | undefined)?.intent;
  // A set-price question is about the set: show the products.json set name, not one product.
  const setName = intent === SET_INTENT ? setOfferFor(catalog, product?.product_id)?.name : undefined;
  const productChip = setName ?? (product ? product.short_name.replace(/^the /, "") : null);
  return (
    <div className={styles.commentRow} data-testid={`op-comment-${c.comment_id}`}>
      <div className={styles.commentLine}>
        <span className={styles.author}>{c.author_name}</span>
        <span className={styles.commentText}>{c.text}</span>
        <span className={["tabular", styles.muted].join(" ")}>{relativeTime(c.received_at, now)}</span>
      </div>
      <div className={styles.commentChips}>
        {c.visibility === "hidden" ? (
          <>
            <Chip tone="risk">{sentenceCase((c.hide_category ?? "hidden").replace(/_/g, " "))}</Chip>
            <Button size="sm" disabled={act.busy} onClick={() => act.run(() => api.unhide(sid, c.comment_id))}>
              Unhide
            </Button>
          </>
        ) : (
          <>
            <Chip>{KIND_LABEL[c.kind]}</Chip>
            {productChip && <Chip tone="accent">{productChip}</Chip>}
            {c.kind === "question" && c.group_id && (
              <button type="button" className={styles.linkish} onClick={() => focusGroup(c.group_id)}>
                Open question
              </button>
            )}
          </>
        )}
      </div>
      {act.error && <p className={styles.error}>{act.error}</p>}
    </div>
  );
}
