// Viewer chat model (§12.5): comments in time order with replies under the question they answer.
// A reply to several askers (a coalesced reply) renders once, under the first visible asker; each
// later asker's comment shows a compact "Also answered: @Name" line instead.
// The viewer's own question also shows where it stands while it has no reply, and a reply to it shows in the
// language it was asked in when the server sent that translation. Both come from server events only.
import { chatItems } from "../../app/selectors";
import type { ClientState } from "../../app/state";
import type { Comment, Message, MessageKind, ReplyStatus } from "../../app/types";

export const CORRECTION_PIN_MS = 60_000;

export interface ReplyView {
  message: Message;
  /** the reply in the language of this viewer's own question; the original shows beneath it */
  translation: { language: string; text: string } | null;
}

export type WaitingStatus = Exclude<ReplyStatus, "answered">;

/** English labels (i18n keys) of the line under the viewer's own waiting question. */
export const WAITING_LABEL: Record<WaitingStatus, string> = {
  checking: "Checking…",
  host: "The host will answer this on air",
  team: "Sent to the team",
};

export interface AlsoAnswered {
  kind: MessageKind;
  messageId: string;
}

export type ViewerChatRow =
  | {
      kind: "comment";
      key: string;
      at: number;
      comment: Comment;
      replies: ReplyView[];
      alsoAnswered: AlsoAnswered | null;
      /** only on the viewer's own question, and only while no reply to it is shown */
      waiting: WaitingStatus | null;
    }
  | { kind: "message"; key: string; at: number; message: Message };

export const PROMO_PREFIX = "PROMO#";

/** "Source: …" labels of a reply: the product sheet, the active promotion (a `PROMO#` citation),
 * or both when it cites both. */
export function sourceLabels(m: Message): string[] {
  const promo = m.citations.some((c) => c.passage_id.startsWith(PROMO_PREFIX));
  const sheet = m.citations.some((c) => !c.passage_id.startsWith(PROMO_PREFIX));
  return [sheet && "Source: product sheet", promo && "Source: active promotion"].filter(Boolean) as string[];
}

const publishedAt = (m: Message) => m.published_at ?? m.created_at;

export function isPinnedCorrection(m: Message, now: number): boolean {
  return m.kind === "correction_notice" && m.state === "published" && now - publishedAt(m) < CORRECTION_PIN_MS;
}

/** The reply in the language one of this viewer's own questions was asked in, if the server sent it. */
function ownTranslation(state: ClientState, m: Message, me: string | null): ReplyView["translation"] {
  if (!me || !m.translations) return null;
  for (const cid of m.reply_to_comment_ids) {
    const c = state.comments[cid];
    const text = c?.author_id === me && c.language ? m.translations[c.language] : undefined;
    if (c?.language && text) return { language: c.language, text };
  }
  return null;
}

/** `me`: this viewer's author id (identity.ts), or null when they have not joined the chat. */
export function viewerChat(state: ClientState, now: number, me: string | null = null): ViewerChatRow[] {
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
    const latest = elsewhere[elsewhere.length - 1];
    const status = item.comment.reply_status;
    // a reply that is shown speaks for itself; other viewers' questions get no extra line
    const waiting =
      me !== null && item.comment.author_id === me && item.replies.length === 0 && !latest && status && status !== "answered"
        ? status
        : null;
    rows.push({
      kind: "comment",
      key: item.comment.comment_id,
      at: item.at,
      comment: item.comment,
      replies: item.replies.map((m) => ({ message: m, translation: ownTranslation(state, m, me) })),
      alsoAnswered: latest ? { kind: latest.kind, messageId: latest.message_id } : null,
      waiting,
    });
  }
  return rows;
}

/** A short, stable signature of what is visible, to keep the chat pinned to the bottom. */
export function chatSignature(rows: ViewerChatRow[]): string {
  const last = rows[rows.length - 1];
  let replies = 0;
  let extra = 0; // status lines and translations add height without adding rows
  for (const r of rows) {
    if (r.kind !== "comment") continue;
    replies += r.replies.length;
    extra += (r.waiting ? 1 : 0) + r.replies.filter((x) => x.translation).length;
  }
  return `${rows.length}:${replies}:${extra}:${last?.key ?? ""}`;
}
