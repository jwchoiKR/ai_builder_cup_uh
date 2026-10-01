// Live chat (§12.3.8): visible comments and replies in time order, newest at the bottom; replies sit
// under the question they answer. Hidden comments never reach the host store.
import { CornerDownRight, Mic, Pin, Sparkles, Store } from "lucide-react";
import { useMemo } from "react";

import type { ChatItem } from "../../app/selectors";
import type { ConnectionStatus } from "../../app/sse";
import type { Message } from "../../app/types";
import { RelativeTime, VirtualList } from "../../components";
import { initialOf } from "./hostSelectors";
import styles from "./host.module.css";

const cx = (...n: (string | false | null | undefined)[]) => n.filter(Boolean).join(" ");

function ReplyBadge({ kind }: { kind: Message["kind"] }) {
  if (kind === "ai_answer")
    return (
      <span className={styles.badge}>
        <Sparkles aria-hidden />
        AI answer
      </span>
    );
  if (kind === "host_answer")
    return (
      <span className={styles.badge}>
        <Mic aria-hidden />
        Host answer
      </span>
    );
  return (
    <span className={cx(styles.badge, styles.badgeBrand)}>
      <Store aria-hidden />
      DAON LAB
    </span>
  );
}

/** Comments answered by a coalesced reply that sits under an earlier asker: the reply renders once,
 * under the first asker; every later asker gets a compact "Also answered: @Name" line. */
export function alsoAnsweredIds(items: ChatItem[]): Set<string> {
  const out = new Set<string>();
  for (const it of items) {
    if (it.kind !== "comment") continue;
    for (const m of it.replies) {
      for (const cid of m.reply_to_comment_ids) if (cid !== it.comment.comment_id) out.add(cid);
    }
  }
  return out;
}

function Row({ item, offset, alsoAnswered }: { item: ChatItem; offset: number; alsoAnswered: boolean }) {
  if (item.kind === "message") {
    const m = item.message;
    return (
      <div className={styles.chatRow}>
        <span className={cx(styles.avatar, styles.brandAvatar)} aria-hidden>
          D
        </span>
        <span>
          <ReplyBadge kind={m.kind} />{" "}
          {m.kind === "correction_notice" && <span className={styles.chatName}>Correction</span>}
          {m.text}
        </span>
        <span className={styles.chatTime}>
          <RelativeTime at={item.at} serverOffsetMs={offset} />
        </span>
      </div>
    );
  }
  const c = item.comment;
  return (
    <div className={styles.chatRow}>
      <span className={styles.avatar} aria-hidden>
        {initialOf(c.author_name)}
      </span>
      <span>
        <span className={styles.chatName}>{c.author_name}</span>
        {c.text}
      </span>
      <span className={styles.chatTime}>
        <RelativeTime at={c.received_at} serverOffsetMs={offset} />
      </span>
      {item.replies.map((m) => (
        <div key={m.message_id} className={styles.reply}>
          <CornerDownRight className={styles.replyArrow} aria-hidden size="1em" />
          <ReplyBadge kind={m.kind} />
          <span>{m.text}</span>
        </div>
      ))}
      {alsoAnswered && item.replies.length === 0 && (
        <div className={cx(styles.reply, styles.alsoAnswered)} data-testid={`host-also-answered-${c.comment_id}`}>
          <CornerDownRight className={styles.replyArrow} aria-hidden size="1em" />
          <span>Also answered: @{c.author_name}</span>
        </div>
      )}
    </div>
  );
}

export function Chat({
  items,
  pinnedNotice,
  connection,
  serverOffsetMs,
}: {
  items: ChatItem[];
  pinnedNotice: string | null;
  connection: ConnectionStatus;
  serverOffsetMs: number;
}) {
  const ok = connection === "connected";
  const also = useMemo(() => alsoAnsweredIds(items), [items]);
  return (
    <section className={styles.card} data-testid="host-chat" aria-label="Live chat">
      <header className={styles.cardHeader}>
        <span className={styles.cardTitle}>LIVE CHAT</span>
        <span className={styles.connection} aria-live="polite">
          <span className={cx(styles.connDot, !ok && styles.connDotOff)} aria-hidden />
          {ok ? "Connected" : "Reconnecting…"}
        </span>
      </header>
      {pinnedNotice && (
        <div className={styles.pinned}>
          <Pin aria-hidden />
          <span>{pinnedNotice}</span>
        </div>
      )}
      <VirtualList
        className={styles.chatList}
        items={items}
        stickToBottom
        rowHeight={52}
        getKey={(it) => (it.kind === "comment" ? it.comment.comment_id : it.message.message_id)}
        renderItem={(it) => (
          <Row item={it} offset={serverOffsetMs} alsoAnswered={it.kind === "comment" && also.has(it.comment.comment_id)} />
        )}
      />
    </section>
  );
}
