// Viewer chat model (§12.5): comments in time order with replies under the question they answer.
// A reply to several askers renders once, under the first visible asker, with "@Name" mentions of the
// others; the other askers' comments show a compact "answered above" line.
import { chatItems } from "../../app/selectors";
import type { ClientState } from "../../app/state";
import type { Comment, Message, MessageKind } from "../../app/types";

export const CORRECTION_PIN_MS = 60_000;

export interface ReplyView {
  message: Message;
  /** other askers this reply also answers ("@Name"), excluding the comment it sits under */
  mentions: string[];
}

export type ViewerChatRow =
  | { kind: "comment"; key: string; at: number; comment: Comment; replies: ReplyView[]; answeredAbove: MessageKind | null }
  | { kind: "message"; key: string; at: number; message: Message };

const publishedAt = (m: Message) => m.published_at ?? m.created_at;

export function isPinnedCorrection(m: Message, now: number): boolean {
  return m.kind === "correction_notice" && m.state === "published" && now - publishedAt(m) < CORRECTION_PIN_MS;
}

export function viewerChat(state: ClientState, now: number): ViewerChatRow[] {
  const items = chatItems(state);
  // comment id -> published replies that answer it
  const answering = new Map<string, Message[]>();
  for (const m of Object.values(state.messages)) {
    if (m.state !== "published") continue;
    for (const cid of m.reply_to_comment_ids) answering.set(cid, [...(answering.get(cid) ?? []), m]);
  }
  const rows: ViewerChatRow[] = [];
  for (const item of items) {
    if (item.kind === "message") {
      if (isPinnedCorrection(item.message, now)) continue; // shown pinned above the chat for 60 s
      rows.push({ kind: "message", key: item.message.message_id, at: item.at, message: item.message });
      continue;
    }
    const own = new Set(item.replies.map((r) => r.message_id));
    const elsewhere = (answering.get(item.comment.comment_id) ?? []).filter((m) => !own.has(m.message_id));
    rows.push({
      kind: "comment",
      key: item.comment.comment_id,
      at: item.at,
      comment: item.comment,
      replies: item.replies.map((m) => ({
        message: m,
        mentions: m.reply_to_author_names.filter((n) => n !== item.comment.author_name),
      })),
      answeredAbove: elsewhere.length ? elsewhere[elsewhere.length - 1].kind : null,
    });
  }
  return rows;
}

/** A short, stable signature of what is visible, to keep the chat pinned to the bottom. */
export function chatSignature(rows: ViewerChatRow[]): string {
  const last = rows[rows.length - 1];
  const replies = rows.reduce((n, r) => n + (r.kind === "comment" ? r.replies.length : 0), 0);
  return `${rows.length}:${replies}:${last?.key ?? ""}`;
}
