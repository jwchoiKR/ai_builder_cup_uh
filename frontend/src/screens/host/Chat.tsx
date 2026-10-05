// Live chat (§12.3.8): visible comments and replies in time order, newest at the bottom; replies sit
// under the question they answer. Hidden comments never reach the host store.
import { CornerDownRight, Mic, Pin, Sparkles, Store } from "lucide-react";
import { useMemo } from "react";

import { useT } from "../../app/i18n";
import type { ChatItem } from "../../app/selectors";
import type { ConnectionStatus } from "../../app/sse";
import type { Message } from "../../app/types";
import { RelativeTime, VirtualList } from "../../components";
import { initialOf } from "./hostSelectors";
import styles from "./host.module.css";

const cx = (...n: (string | false | null | undefined)[]) => n.filter(Boolean).join(" ");

function ReplyBadge({ kind }: { kind: Message["kind"] }) {
  const t = useT();
  if (kind === "ai_answer")
    return (
      <span className={styles.badge}>
        <Sparkles aria-hidden />
        {t("AI answer")}
      </span>
    );
  if (kind === "host_answer")
    return (
      <span className={styles.badge}>
        <Mic aria-hidden />
        {t("Host answer")}
      </span>
    );
  return (
    <span className={cx(styles.badge, styles.badgeBrand)}>
      <Store aria-hidden />
      {t("Brand")}
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

/** D-115: the names of later askers, once, under the first asker's reply ("Also answered: @A, @B"). */
export function alsoAnsweredNames(items: ChatItem[]): Map<string, string[]> {
  const names = new Map<string, string>();
  for (const it of items) if (it.kind === "comment") names.set(it.comment.comment_id, it.comment.author_name);
  const out = new Map<string, string[]>();
  for (const it of items) {
    if (it.kind !== "comment") continue;
    const others = it.replies.flatMap((m) => m.reply_to_comment_ids.filter((cid) => cid !== it.comment.comment_id));
    const list = [...new Set(others.map((cid) => names.get(cid)).filter((n): n is string => Boolean(n)))];
    if (list.length) out.set(it.comment.comment_id, list);
  }
  return out;
}

/** D-239: the source behind an AI reply, in the host chat too: the section (or document) and a short quote. */
function Cite({ message }: { message: Message }) {
  const c = message.citations?.[0] as { section?: string | null; doc?: string | null; quote?: string } | undefined;
  if (!c?.quote) return null;
  const quote = c.quote.length > 80 ? `${c.quote.slice(0, 77)}…` : c.quote;
  return (
    <span className={styles.cite} data-testid="host-citation">
      {[c.section, c.doc].filter(Boolean)[0] ?? "Source"} · “{quote}”
    </span>
  );
}

function Row({ item, offset, alsoNames }: { item: ChatItem; offset: number; alsoNames: string[] | undefined }) {
  const t = useT();
  if (item.kind === "message") {
    const m = item.message;
    return (
      <div className={styles.chatRow}>
        <span className={cx(styles.avatar, styles.brandAvatar)} aria-hidden>
          <Store size="1em" />
        </span>
        <span>
          <ReplyBadge kind={m.kind} />{" "}
          {m.kind === "correction_notice" && <span className={styles.chatName}>{t("Correction")}</span>}
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
          <Cite message={m} />
        </div>
      ))}
      {alsoNames && (
        <div className={cx(styles.reply, styles.alsoAnswered)} data-testid={`host-also-answered-${c.comment_id}`}>
          <span>
            {t("Also answered:")} {alsoNames.map((n) => `@${n}`).join(", ")}
          </span>
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
  const t = useT();
  const ok = connection === "connected";
  const also = useMemo(() => alsoAnsweredIds(items), [items]);
  const alsoNames = useMemo(() => alsoAnsweredNames(items), [items]);
  // later askers of a coalesced reply are folded into the first asker's note
  const rows = useMemo(() => items.filter((it) => it.kind !== "comment" || !also.has(it.comment.comment_id) || it.replies.length > 0), [items, also]);
  return (
    <section className={styles.card} data-testid="host-chat" aria-label={t("Live chat")}>
      <header className={styles.cardHeader}>
        <span className={styles.cardTitle}>{t("LIVE CHAT")}</span>
        <span className={styles.connection} aria-live="polite">
          <span className={cx(styles.connDot, !ok && styles.connDotOff)} aria-hidden />
          {ok ? t("Connected") : t("Reconnecting…")}
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
        items={rows}
        stickToBottom
        rowHeight={52}
        getKey={(it) => (it.kind === "comment" ? it.comment.comment_id : it.message.message_id)}
        renderItem={(it) => (
          <Row item={it} offset={serverOffsetMs} alsoNames={it.kind === "comment" ? alsoNames.get(it.comment.comment_id) : undefined} />
        )}
      />
    </section>
  );
}
