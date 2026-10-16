// D-474 (user, like SOOP): small viewer figures standing on the bottom edge of the video, with a one-line chat
// bubble over the ones who just wrote. Display only: built from the comment rows the chat already shows.
import { memo, useEffect, useReducer, useRef } from "react";

import type { Comment } from "../../app/types";
import styles from "./viewer.module.css";

export const CROWD_MAX = 10; // the user: about 10, so the page stays light
export const BUBBLE_MAX = 3;
export const BUBBLE_MS = 4000; // the same as the time-sale pop-up (POPUP_MS)
/** a comment first seen older than this (page load, a reconnect replay) adds its figure but no bubble */
export const BUBBLE_STALE_MS = 10_000;

interface Figure {
  authorId: string;
  name: string;
  lastAt: number;
}

interface Bubble {
  authorId: string;
  commentId: string;
  text: string;
}

/** A new commenter takes a free slot, or the slot of the longest-silent figure; the viewer's own figure stays. */
function place(slots: Figure[], c: Comment, me: string | null) {
  const known = slots.find((f) => f.authorId === c.author_id);
  if (known) {
    known.lastAt = c.received_at;
    known.name = c.author_name;
    return;
  }
  const fig = { authorId: c.author_id, name: c.author_name, lastAt: c.received_at };
  if (slots.length < CROWD_MAX) {
    slots.push(fig);
    return;
  }
  let i = -1;
  slots.forEach((f, j) => {
    if (f.authorId !== me && (i < 0 || f.lastAt < slots[i]!.lastAt)) i = j;
  });
  if (i >= 0) slots[i] = fig;
}

function hash(s: string): number {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
  return h;
}

const HAIR = [
  // bangs
  "M6 15a10 10 0 0 1 20 0c-3-3-7-4-10-2c-3-2-7-1-10 2z",
  // bangs and a bun
  "M6 15a10 10 0 0 1 20 0c-3-3-7-4-10-2c-3-2-7-1-10 2zM16 0.5a4 4 0 1 1 0 8a4 4 0 1 1 0-8z",
  // a cap with a brim
  "M5.5 13a10.5 9 0 0 1 21 0zM15 10.5h13a1.5 1.5 0 0 1 0 3h-13z",
];

/** Colour (8) and hair (3) come from the author id, so people differ without colour vision too. */
const Person = memo(function Person({
  authorId,
  name,
  slot,
  own,
  bubble,
  rank,
}: {
  authorId: string;
  name: string;
  slot: number;
  own: boolean;
  bubble: string | null;
  rank: number;
}) {
  const h = hash(authorId);
  const color = `var(--crowd-${(h % 8) + 1})`;
  const edge = slot <= 2 ? "start" : slot >= CROWD_MAX - 3 ? "end" : "mid";
  return (
    <div className={styles.person} style={{ gridColumn: slot + 1 }} data-testid={`viewer-figure-${authorId}`} data-own={own || undefined}>
      {bubble !== null && (
        <span className={styles.bubble} data-edge={edge} style={{ zIndex: rank }} data-testid={`viewer-bubble-${authorId}`}>
          <span className={styles.bubbleText}>{bubble}</span>
        </span>
      )}
      <span className={styles.personName}>{name}</span>
      <svg className={styles.personBody} viewBox="0 0 32 40">
        <rect x="9" y="24" width="14" height="15" rx="6" fill={color} />
        <circle className={styles.personHead} cx="16" cy="15" r="10" />
        <path d={HAIR[(h >>> 3) % HAIR.length]} fill={color} />
        <circle cx="12.5" cy="17" r="1.3" className={styles.personEye} />
        <circle cx="19.5" cy="17" r="1.3" className={styles.personEye} />
      </svg>
    </div>
  );
});

function CrowdView({ comments, me, serverOffsetMs }: { comments: Comment[]; me: string | null; serverOffsetMs: number }) {
  const slots = useRef<Figure[]>([]);
  const seen = useRef(new Set<string>());
  const bubbles = useRef<Bubble[]>([]);
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const [, rerender] = useReducer((n: number) => n + 1, 0);
  const sig = comments.map((c) => c.comment_id).join(" ");

  useEffect(() => {
    const stop = (commentId: string) => {
      clearTimeout(timers.current.get(commentId));
      timers.current.delete(commentId);
    };
    const visible = new Set(comments.map((c) => c.comment_id));
    let list: Bubble[] = [];
    for (const b of bubbles.current) {
      if (visible.has(b.commentId)) list.push(b);
      else stop(b.commentId); // a comment hidden while its bubble is up loses the bubble at once
    }
    const now = Date.now() + serverOffsetMs;
    for (const c of comments) {
      if (seen.current.has(c.comment_id)) continue;
      seen.current.add(c.comment_id);
      place(slots.current, c, me);
      if (now - c.received_at > BUBBLE_STALE_MS) continue;
      // one bubble per figure; at most BUBBLE_MAX, a newer one closes the oldest (bursts are sampled, not queued)
      const before = list.find((b) => b.authorId === c.author_id);
      if (before) {
        stop(before.commentId);
        list = list.filter((b) => b !== before);
      }
      list.push({ authorId: c.author_id, commentId: c.comment_id, text: c.text });
      while (list.length > BUBBLE_MAX) stop(list.shift()!.commentId);
    }
    for (const b of list) {
      if (timers.current.has(b.commentId)) continue;
      timers.current.set(b.commentId, setTimeout(() => {
        timers.current.delete(b.commentId);
        bubbles.current = bubbles.current.filter((x) => x.commentId !== b.commentId);
        rerender();
      }, BUBBLE_MS));
    }
    bubbles.current = list;
    rerender();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- sig stands for the comment list
  }, [sig, me, serverOffsetMs]);

  useEffect(() => () => {
    timers.current.forEach(clearTimeout);
    timers.current.clear();
    bubbles.current = [];
  }, []);

  if (slots.current.length === 0) return null;
  return (
    <div className={styles.crowd} aria-hidden data-testid="viewer-crowd">
      {slots.current.map((f, i) => {
        const rank = bubbles.current.findIndex((b) => b.authorId === f.authorId);
        return (
          <Person
            key={f.authorId}
            authorId={f.authorId}
            name={f.name}
            slot={i}
            own={f.authorId === me}
            bubble={rank >= 0 ? bubbles.current[rank]!.text : null}
            rank={rank + 1}
          />
        );
      })}
    </div>
  );
}

/** ViewerView re-renders every second; the crowd only when the comment list, the viewer or the clock offset change. */
export const Crowd = memo(
  CrowdView,
  (a, b) => a.me === b.me && a.serverOffsetMs === b.serverOffsetMs
    && a.comments.length === b.comments.length && a.comments.every((c, i) => c.comment_id === b.comments[i]!.comment_id),
);
