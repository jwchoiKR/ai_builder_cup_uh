// D-474 (user, like SOOP): small viewer figures standing on the bottom edge of the video, with a one-line chat
// bubble over the ones who just wrote. D-475 (user): a figure raises its hand when its comment is a question, and
// is happy with hearts when the host answers it on air. Display only: built from what the chat already shows.
import { memo, useEffect, useLayoutEffect, useReducer, useRef } from "react";

import type { Comment } from "../../app/types";
import styles from "./viewer.module.css";

export const CROWD_MAX = 10; // the user: about 10, so the page stays light
export const BUBBLE_MAX = 3;
export const BUBBLE_MS = 4000; // the same as the time-sale pop-up (POPUP_MS)
/** a comment first seen older than this (page load, a reconnect replay) adds its figure but no bubble or hand */
export const BUBBLE_STALE_MS = 10_000;
export const HAND_MS = 4000;
export const CHEER_MS = 2000;
export const CHEER_MAX = 3;
/** D-475: figures with a pending question keep their slot, up to this many */
const PROTECT_MAX = 4;
const PENDING = new Set(["checking", "host", "team"]);

/** one asker of a published host answer: `key` is message_id:comment_id */
export interface HostAnswered {
  key: string;
  authorId: string;
}

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

/** A new commenter takes a free slot, or the slot of the longest-silent figure that is neither the viewer's own nor
 *  waiting for an answer (D-475); if every other figure waits, the longest-silent of them. */
function place(slots: Figure[], c: Comment, me: string | null, waiting: Set<string>) {
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
  const oldest = (skip: (f: Figure) => boolean) => {
    let i = -1;
    slots.forEach((f, j) => {
      if (!skip(f) && (i < 0 || f.lastAt < slots[i]!.lastAt)) i = j;
    });
    return i;
  };
  let i = oldest((f) => f.authorId === me || waiting.has(f.authorId));
  if (i < 0) i = oldest((f) => f.authorId === me);
  if (i >= 0) slots[i] = fig;
}

/** The authors of the most recent pending questions, at most PROTECT_MAX. */
function waitingAuthors(comments: Comment[]): Set<string> {
  const out = new Set<string>();
  for (let i = comments.length - 1; i >= 0 && out.size < PROTECT_MAX; i--) {
    const c = comments[i]!;
    if (c.reply_status && PENDING.has(c.reply_status)) out.add(c.author_id);
  }
  return out;
}

/** djb2, then mixed (D-475: close ids like u0..u9 gave the same low bits, so every figure had the same hair) */
function hash(s: string): number {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
  h = Math.imul(h ^ (h >>> 16), 0x45d9f3b);
  h = Math.imul(h ^ (h >>> 16), 0x45d9f3b);
  return (h ^ (h >>> 16)) >>> 0;
}

/** three hair forms that read apart at 22-34 px */
const HAIR = [
  // bangs with side locks down to the cheeks
  "M5.5 19V14a10.5 10.5 0 0 1 21 0v5h-3v-5.5c-3-2.5-6-3-7.5-1c-1.5-2-4.5-1.5-7.5 1V19z",
  // a big round bun on top, flat fringe
  "M6 14a10 10 0 0 1 20 0c-6-2.5-14-2.5-20 0zM16 0a5 5 0 1 1 0 10a5 5 0 1 1 0-10z",
  // a cap with a long brim and a button
  "M5.5 13.5a10.5 10 0 0 1 21 0zM14 11h15.5a2 2 0 0 1 0 4H14zM16 1.5a1.8 1.8 0 1 1 0 3.6a1.8 1.8 0 1 1 0-3.6z",
];

const reducedMotion = () =>
  typeof window !== "undefined" && typeof window.matchMedia === "function"
  && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Colour (8) and hair (3) come from the author id, so people differ without colour vision too. */
const Person = memo(function Person({
  authorId,
  name,
  slot,
  own,
  bubble,
  rank,
  hand,
  happy,
}: {
  authorId: string;
  name: string;
  slot: number;
  own: boolean;
  bubble: string | null;
  rank: number;
  hand: boolean;
  happy: boolean;
}) {
  const h = hash(authorId);
  const color = `var(--crowd-${(h % 8) + 1})`; // colour from the low bits, hair from higher ones
  const edge = slot <= 2 ? "start" : slot >= CROWD_MAX - 3 ? "end" : "mid";
  // reduced motion: one still heart instead of three floating ones
  const hearts = happy ? (reducedMotion() ? ["still"] : ["left", "right", "top"]) : [];
  return (
    <div
      className={styles.person}
      style={{ gridColumn: slot + 1 }}
      data-testid={`viewer-figure-${authorId}`}
      data-own={own || undefined}
      data-hand={hand || undefined}
      data-happy={happy || undefined}
    >
      {bubble !== null && (
        <span className={styles.bubble} data-edge={edge} style={{ zIndex: rank }} data-testid={`viewer-bubble-${authorId}`}>
          <span className={styles.bubbleText}>{bubble}</span>
        </span>
      )}
      {hearts.map((p) => (
        <span key={p} className={styles.heart} data-at={p} data-testid="viewer-heart">
          ♥
        </span>
      ))}
      <span className={styles.personName}>{name}</span>
      <svg className={styles.personBody} viewBox="0 0 32 40">
        <rect x="9" y="24" width="14" height="15" rx="6" fill={color} />
        {hand && (
          <>
            <path d="M21 28L27.5 15" stroke={color} strokeWidth="3.5" strokeLinecap="round" />
            <circle cx="28" cy="13.5" r="2.4" className={styles.personHead} />
          </>
        )}
        <circle className={styles.personHead} cx="16" cy="15" r="10" />
        <path d={HAIR[(h >>> 8) % HAIR.length]} fill={color} />
        {happy ? (
          <path d="M11 17.5q1.5-2 3 0M18 17.5q1.5-2 3 0M13.5 20.5q2.5 2 5 0" className={styles.personSmile} />
        ) : (
          <>
            <circle cx="12.5" cy="17" r="1.3" className={styles.personEye} />
            <circle cx="19.5" cy="17" r="1.3" className={styles.personEye} />
          </>
        )}
      </svg>
    </div>
  );
});

interface CrowdProps {
  comments: Comment[];
  /** D-475: the askers of published host answers */
  answered: HostAnswered[];
  me: string | null;
  serverOffsetMs: number;
  /** the first snapshot is in: answers already there are not celebrated */
  loaded: boolean;
}

function CrowdView({ comments, answered, me, serverOffsetMs, loaded }: CrowdProps) {
  const slots = useRef<Figure[]>([]);
  const seen = useRef(new Set<string>());
  const bubbles = useRef<Bubble[]>([]);
  const hands = useRef(new Map<string, string>()); // author id -> the question's comment id
  const asked = useRef(new Set<string>()); // comment ids whose question status this client has handled
  const cheers = useRef<string[]>([]); // author ids, oldest first
  const cheered = useRef<Set<string> | null>(null); // answer keys already handled; null until the first snapshot
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const [, rerender] = useReducer((n: number) => n + 1, 0);
  const root = useRef<HTMLDivElement>(null);

  const stop = (key: string) => {
    clearTimeout(timers.current.get(key));
    timers.current.delete(key);
  };
  const arm = (key: string, ms: number, done: () => void) => {
    stop(key);
    timers.current.set(key, setTimeout(() => {
      timers.current.delete(key);
      done();
      rerender();
    }, ms));
  };

  const sig = comments.map((c) => `${c.comment_id}:${c.reply_status ?? ""}`).join(" ");
  const answeredSig = answered.map((a) => a.key).join(" ");

  useEffect(() => {
    const visible = new Map(comments.map((c) => [c.comment_id, c]));
    const now = Date.now() + serverOffsetMs;
    const waiting = waitingAuthors(comments);

    let list: Bubble[] = [];
    for (const b of bubbles.current) {
      if (visible.has(b.commentId)) list.push(b);
      else stop(`b:${b.commentId}`); // a comment hidden while its bubble is up loses the bubble at once
    }
    for (const c of comments) {
      if (seen.current.has(c.comment_id)) continue;
      seen.current.add(c.comment_id);
      place(slots.current, c, me, waiting);
      if (now - c.received_at > BUBBLE_STALE_MS) continue;
      // one bubble per figure; at most BUBBLE_MAX, a newer one closes the oldest (bursts are sampled, not queued)
      const before = list.find((b) => b.authorId === c.author_id);
      if (before) {
        stop(`b:${before.commentId}`);
        list = list.filter((b) => b !== before);
      }
      list.push({ authorId: c.author_id, commentId: c.comment_id, text: c.text });
      while (list.length > BUBBLE_MAX) stop(`b:${list.shift()!.commentId}`);
    }
    for (const b of list) {
      const key = `b:${b.commentId}`;
      if (timers.current.has(key)) continue;
      arm(key, BUBBLE_MS, () => {
        bubbles.current = bubbles.current.filter((x) => x.commentId !== b.commentId);
      });
    }
    bubbles.current = list;

    // D-475 hand: the comment pipeline marked it a question (any reply status); only a young comment raises it,
    // for HAND_MS from when this client first sees the status, whether or not its bubble is still up
    const lower = (authorId: string) => {
      hands.current.delete(authorId);
      stop(`h:${authorId}`);
    };
    for (const [authorId, commentId] of hands.current) {
      if (!visible.get(commentId)?.reply_status) lower(authorId); // closed back to chat, or hidden
    }
    for (const c of comments) {
      if (!c.reply_status || asked.current.has(c.comment_id)) continue;
      asked.current.add(c.comment_id);
      if (now - c.received_at > BUBBLE_STALE_MS) continue;
      hands.current.set(c.author_id, c.comment_id);
      arm(`h:${c.author_id}`, HAND_MS, () => hands.current.delete(c.author_id));
    }

    // D-475 hearts: each asker of a host answer published after the first snapshot, if their figure is shown
    if (loaded && cheered.current === null) {
      cheered.current = new Set(answered.map((a) => a.key)); // page load: nothing to celebrate
    } else if (cheered.current) {
      for (const a of answered) {
        if (cheered.current.has(a.key)) continue;
        cheered.current.add(a.key);
        if (!slots.current.some((f) => f.authorId === a.authorId)) continue;
        lower(a.authorId); // happy beats the raised hand
        cheers.current = [...cheers.current.filter((x) => x !== a.authorId), a.authorId];
        while (cheers.current.length > CHEER_MAX) stop(`c:${cheers.current.shift()!}`);
        arm(`c:${a.authorId}`, CHEER_MS, () => {
          cheers.current = cheers.current.filter((x) => x !== a.authorId);
        });
      }
    }
    rerender();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- sig and answeredSig stand for the two lists
  }, [sig, answeredSig, me, serverOffsetMs, loaded]);

  // D-475: bubbles that overlap side by side cut each other's text, so the older one moves up a row (the newest
  // stays on the bottom row, at most 3 rows); --lift also stretches its tail down to its own head
  useLayoutEffect(() => {
    const shown = Array.from(root.current?.querySelectorAll<HTMLElement>("[data-edge]") ?? [])
      .sort((a, b) => Number(b.style.zIndex) - Number(a.style.zIndex)); // newest first
    const placed: { left: number; right: number; row: number }[] = [];
    for (const el of shown) {
      const r = el.getBoundingClientRect();
      let row = 0;
      while (row < BUBBLE_MAX - 1 && placed.some((p) => p.row === row && r.left < p.right && p.left < r.right)) row++;
      placed.push({ left: r.left, right: r.right, row });
      el.style.setProperty("--lift", String(row));
    }
  });

  useEffect(() => () => {
    timers.current.forEach(clearTimeout);
    timers.current.clear();
    bubbles.current = [];
    hands.current.clear();
    cheers.current = [];
  }, []);

  if (slots.current.length === 0) return null;
  return (
    <div ref={root} className={styles.crowd} aria-hidden data-testid="viewer-crowd">
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
            hand={hands.current.has(f.authorId)}
            happy={cheers.current.includes(f.authorId)}
          />
        );
      })}
    </div>
  );
}

const crowdSig = (p: CrowdProps) =>
  `${p.me}|${p.serverOffsetMs}|${p.loaded}|${p.answered.map((a) => a.key).join(" ")}|`
  + p.comments.map((c) => `${c.comment_id}:${c.reply_status ?? ""}`).join(" ");

/** ViewerView re-renders every second; the crowd only when what it shows from could change. */
export const Crowd = memo(CrowdView, (a, b) => crowdSig(a) === crowdSig(b));
