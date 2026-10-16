// D-474 (user, like SOOP): viewers on the bottom edge of the video, with a one-line chat bubble over the ones who just
// wrote. D-475 (user): a raised paw when the comment is a question, hearts when the host answers it on air. D-476
// (user): cute animals that walk about. D-481 (user): a question's bubble and paw stay up until it is answered. D-482
// (user): a bubble comes up once triage has judged the comment.
// Display only: built from what the chat already shows.
import { memo, useEffect, useLayoutEffect, useReducer, useRef, useState, type CSSProperties } from "react";

import type { Comment, MessageKind } from "../../app/types";
import { Animal, SPECIES, type Species } from "./animals";
import { Badge } from "./Badge";
import styles from "./viewer.module.css";

export const CROWD_MAX = 6; // D-476: 6 on a 390 px phone (was 10)
export const BUBBLE_MAX = 3;
export const BUBBLE_MS = 4000; // the same as the time-sale pop-up (POPUP_MS)
/** a comment first seen older than this (page load, a reconnect replay) adds its animal but no bubble or paw */
export const BUBBLE_STALE_MS = 10_000;
/** D-481: a question's bubble and paw stay up while it waits for an answer, at most this long from the comment */
export const HOLD_CAP_MS = 90_000;
/** D-481: at most this many held question bubbles, so one bubble stays free for chat */
export const HOLD_MAX = 2;
/** D-481: after "answered", the bubble waits this long for the host answer's hearts before it closes */
export const ANSWER_GRACE_MS = 1000;
export const CHEER_MS = 2000;
export const CHEER_MAX = 3;
const PENDING = new Set(["checking", "host", "team"]);
/** D-487 (user: heavy chatters first, questions sent to the host stay): at most this many of the 6 places are kept */
export const PROTECT_MAX = 4;
/** D-487: at most this many askers of a question sent to the host are pinned */
export const HOST_PINS = 2;
/** D-487: a host question's pin ends this long after the comment at the latest */
export const HOST_PIN_MS = 300_000;
/** D-487: the chat score counts comments in this window, at most one per author per SCORE_GAP_MS */
export const SCORE_WINDOW_MS = 600_000;
export const SCORE_GAP_MS = 5000;
/** D-487: a newcomer takes the place only of an animal that has been silent this long */
export const QUIET_MS = 15_000;
const LEAVE_MS = 400;
const HEARTS = 6;
/** D-478: walking lanes, so bunched animals stand apart; the lower lane is in front */
export const LANES = 3;
/** D-488: the drawing's opacity while the animal walks */
export const WALK_OPACITY = 0.85;
/** D-485: the answer bubble (the reply over its question) shows this long */
export const PAIR_MS = 5000;
/** D-485: a newer reply replaces the shown answer bubble only after it has shown this long */
export const PAIR_MIN_MS = 3000;

/** a published reply to viewer questions (D-483: AI, host or brand) */
export interface ReplyPost {
  messageId: string;
  kind: MessageKind;
  text: string;
  /** the reply in the language of this viewer's own question, when the server sent it */
  ownText: string | null;
  askers: { commentId: string; authorId: string }[];
}

interface Pair {
  messageId: string;
  commentId: string;
  authorId: string;
}

interface Figure {
  authorId: string;
  name: string;
  lastAt: number;
  species: Species;
}

interface Bubble {
  authorId: string;
  commentId: string;
  text: string;
  /** D-481: a waiting question's bubble, held until it is answered */
  held: boolean;
}

function hash(s: string): number {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
  h = Math.imul(h ^ (h >>> 16), 0x45d9f3b);
  h = Math.imul(h ^ (h >>> 16), 0x45d9f3b);
  return (h ^ (h >>> 16)) >>> 0;
}

/** D-476: the species hashed from the id; if another animal on screen has it, the next free one */
function pickSpecies(authorId: string, others: Figure[]): Species {
  const taken = new Set(others.map((f) => f.species));
  const start = hash(authorId) % SPECIES.length;
  for (let i = 0; i < SPECIES.length; i++) {
    const s = SPECIES[(start + i) % SPECIES.length]!;
    if (!taken.has(s)) return s;
  }
  return SPECIES[start]!;
}

/** D-487: how much each viewer chats: their comments in the last SCORE_WINDOW_MS, at most one per SCORE_GAP_MS (a
 *  burst of spam counts once). `comments` are in time order. */
export function chatScores(comments: Comment[], now: number): Map<string, number> {
  const last = new Map<string, number>();
  const score = new Map<string, number>();
  for (const c of comments) {
    if (now - c.received_at > SCORE_WINDOW_MS) continue;
    const prev = last.get(c.author_id);
    if (prev !== undefined && c.received_at - prev < SCORE_GAP_MS) continue;
    last.set(c.author_id, c.received_at);
    score.set(c.author_id, (score.get(c.author_id) ?? 0) + 1);
  }
  return score;
}

/** D-487: the animals that keep their place, at most PROTECT_MAX in all: the viewer's own, then the askers of a
 *  question sent to the host (at most HOST_PINS; until it is replied to, closed, hidden, the product changes, or
 *  HOST_PIN_MS after the comment), then askers waiting on the team. Newest questions first. */
export function protectedAuthors(comments: Comment[], me: string | null, onScreen: Set<string>, replied: Set<string>,
  segmentSince: number, now: number): Set<string> {
  const out = new Set<string>();
  if (me && onScreen.has(me)) out.add(me);
  const newest = [...comments].reverse().filter((c) => onScreen.has(c.author_id));
  let pins = 0;
  for (const c of newest) {
    if (out.size >= PROTECT_MAX || pins >= HOST_PINS) break;
    if (c.reply_status !== "host" || replied.has(c.comment_id) || out.has(c.author_id)) continue;
    if (c.received_at < segmentSince || now - c.received_at >= HOST_PIN_MS) continue;
    out.add(c.author_id);
    pins++;
  }
  for (const c of newest) {
    if (out.size >= PROTECT_MAX) break;
    if (c.reply_status === "team") out.add(c.author_id);
  }
  return out;
}

/** A new commenter joins while there is room; else takes the place of the lowest-scoring animal that is not kept
 *  and has been silent QUIET_MS (tie: the longest silent); if there is none, it gets no animal (D-487). Returns
 *  whether the author is on screen, and the animal that left. */
function place(roster: Figure[], c: Comment, keep: Set<string>, scores: Map<string, number>, now: number):
  { shown: boolean; gone: Figure | null } {
  const known = roster.find((f) => f.authorId === c.author_id);
  if (known) {
    known.lastAt = Math.max(known.lastAt, c.received_at);
    known.name = c.author_name;
    return { shown: true, gone: null };
  }
  const join = (others: Figure[]) =>
    ({ authorId: c.author_id, name: c.author_name, lastAt: c.received_at, species: pickSpecies(c.author_id, others) });
  if (roster.length < CROWD_MAX) {
    roster.push(join(roster));
    return { shown: true, gone: null };
  }
  let i = -1;
  roster.forEach((f, j) => {
    if (keep.has(f.authorId) || now - f.lastAt < QUIET_MS) return;
    const best = roster[i];
    const [sf, sb] = [scores.get(f.authorId) ?? 0, best ? scores.get(best.authorId) ?? 0 : Infinity];
    if (!best || sf < sb || (sf === sb && f.lastAt < best.lastAt)) i = j;
  });
  if (i < 0) return { shown: false, gone: null };
  const gone = roster[i]!;
  roster[i] = join(roster.filter((_, j) => j !== i));
  return { shown: true, gone };
}

const reducedMotion = () =>
  typeof window !== "undefined" && typeof window.matchMedia === "function"
  && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** the animal's size, as --aw in the CSS: clamp(30px, 11cqw, 44px) */
const animalWidth = (w: number) => Math.min(44, Math.max(30, w * 0.11));

/** D-476: each animal's own walk, from its id: 18-32 px/s across the video, a 1-3 s pause at each turn (the walk
 *  keyframes hold 5% at each end), some also stop midway, and a start spread along the path. */
function walkStyle(authorId: string, width: number): CSSProperties {
  const h = hash(authorId);
  const span = Math.max(40, width - 24 - animalWidth(width));
  const speed = 18 + (h % 15);
  const half = span / speed / 0.9; // one way, holds included (moving takes 90% of it)
  return {
    "--walk": `${half.toFixed(2)}s`,
    "--turn": `${(half * 2).toFixed(2)}s`,
    "--delay": `-${(((h >>> 8) % 1000) / 1000 * half * 2).toFixed(2)}s`,
  } as CSSProperties;
}

/** about a third of the animals also stop midway (data-path="stop") */
const stopsMidway = (authorId: string) => (hash(authorId) >>> 20) % 3 === 0;

const Walker = memo(function Walker({
  authorId,
  name,
  species,
  own,
  bubble,
  rank,
  hand,
  happy,
  leaving,
  still,
  spot,
  width,
  lane,
  pair,
  brand,
}: {
  authorId: string;
  name: string;
  species: Species;
  own: boolean;
  bubble: string | null;
  rank: number;
  hand: boolean;
  happy: boolean;
  leaving: boolean;
  /** reduced motion: stands at `spot` (0-1 along the path), no walking */
  still: boolean;
  spot: number;
  width: number;
  /** D-478: 0 (bottom, in front) to LANES - 1 */
  lane: number;
  /** D-485: the answer bubble: the reply over its question */
  pair: { question: string; answer: string; kind: MessageKind } | null;
  brand: string;
}) {
  const stopped = bubble !== null || hand || happy || pair !== null;
  const style: CSSProperties = still
    ? ({ "--spot": spot } as CSSProperties)
    : walkStyle(authorId, width);
  // a speaking animal is in front of the walkers, the newest bubble on top; among walkers the lower lane is in front
  style.zIndex = stopped ? 10 + rank : LANES - lane;
  (style as Record<string, unknown>)["--lane"] = lane;
  // D-480 (user): a speaking animal faces front, for a chat or a question (a question also raises the paw); the
  // hearts alone keep the side view
  const front = bubble !== null || hand || pair !== null;
  return (
    <div
      className={styles.walker}
      style={style}
      data-testid={`viewer-figure-${authorId}`}
      data-species={species}
      data-path={!still && stopsMidway(authorId) ? "stop" : undefined}
      data-own={own || undefined}
      data-hand={hand || undefined}
      data-happy={happy || undefined}
      data-stopped={stopped || undefined}
      data-still={still || undefined}
      data-leaving={leaving || undefined}
    >
      <div className={styles.walkerInner}>
        {pair ? (
          // D-485: one bubble (one rect to place, one tail): the reply on top, its question below; light tokens inside,
          // since the bubble is white in both themes
          <span className={[styles.bubble, styles.bubblePair].join(" ")} data-theme="light" data-pair
            data-testid={`viewer-bubble-${authorId}`}>
            <span className={styles.pairAnswer} data-testid={`viewer-pair-answer-${authorId}`}>
              <Badge kind={pair.kind} brand={brand} />
              <span className={styles.pairAnswerText}>{pair.answer}</span>
            </span>
            <span className={styles.pairQuestion}>{pair.question}</span>
          </span>
        ) : bubble !== null && (
          <span className={styles.bubble} data-testid={`viewer-bubble-${authorId}`}>
            <span className={styles.bubbleText}>{bubble}</span>
          </span>
        )}
        {happy && (
          <span className={styles.hearts}>
            {(still ? [0] : Array.from({ length: HEARTS }, (_, i) => i)).map((i) => (
              <span key={i} className={styles.heart} data-i={i} data-still={still || undefined} data-testid="viewer-heart">
                ♥
              </span>
            ))}
          </span>
        )}
        {/* D-478: names only on a speaking animal and the viewer's own, so bunched walkers' names never run together */}
        <span className={styles.personName} data-shown={stopped || own || undefined}>{name}</span>
        <div className={styles.facing}>
          <Animal
            species={species}
            view={front ? "front" : "side"}
            frame={front || still || stopped ? 0 : "both"}
            happy={happy}
            paw={hand}
            className={styles.animal}
            // D-488 (user): a walking animal is a little see-through; a speaking one is solid (the name, bubble and
            // hearts stay solid either way)
            style={{ opacity: stopped ? 1 : WALK_OPACITY }}
          />
        </div>
      </div>
    </div>
  );
});

interface CrowdProps {
  comments: Comment[];
  /** D-475: the published replies and their askers (D-483: AI, host or brand) */
  replies: ReplyPost[];
  /** the catalog's brand, the label of a brand reply's tag */
  brand: string;
  me: string | null;
  serverOffsetMs: number;
  /** the first snapshot is in: answers already there are not celebrated */
  loaded: boolean;
  /** D-484: turned on again at this server time: comments from before it never speak */
  since?: number;
  /** D-487: when the product on air started: a host question from before it no longer pins its asker */
  segmentSince?: number;
}

function CrowdView({ comments, replies, brand, me, serverOffsetMs, loaded, since, segmentSince = 0 }: CrowdProps) {
  const roster = useRef<Figure[]>([]);
  const leaving = useRef<Figure[]>([]);
  const seen = useRef(new Set<string>());
  const bubbles = useRef<Bubble[]>([]);
  const hands = useRef(new Map<string, string>()); // author id -> the question's comment id
  const holds = useRef(new Map<string, string>()); // D-481: waiting question's comment id -> author id
  const awaiting = useRef(new Set<string>()); // D-482: comments seen live whose triage verdict is not in yet
  const spoke = useRef(new Set<string>()); // D-482: comments that have had their bubble
  const asked = useRef(new Set<string>()); // comment ids whose question status this client has handled
  const cheers = useRef<string[]>([]); // author ids, oldest first
  const cheered = useRef<Set<string> | null>(null); // answer keys already handled; null until the first snapshot
  const pair = useRef<(Pair & { startedAt: number }) | null>(null); // D-485: the answer bubble shown
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const [, rerender] = useReducer((n: number) => n + 1, 0);
  const root = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(390);
  const [hidden, setHidden] = useState(() => typeof document !== "undefined" && document.hidden);

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

  const sig = comments.map((c) => `${c.comment_id}:${c.kind}:${c.reply_status ?? ""}`).join(" ");
  const answered = replies.flatMap((r) => r.askers.map((a) => ({ key: `${r.messageId}:${a.commentId}`, authorId: a.authorId })));
  const answeredSig = answered.map((a) => a.key).join(" ");

  useEffect(() => {
    const visible = new Map(comments.map((c) => [c.comment_id, c]));
    const now = Date.now() + serverOffsetMs;
    const replied = new Set(replies.flatMap((r) => r.askers.map((a) => a.commentId)));
    const scores = chatScores(comments, now);
    const isHost = (b: Bubble) => visible.get(b.commentId)?.reply_status === "host";
    const young = (c: Comment) => now - c.received_at <= BUBBLE_STALE_MS;
    const pending = (c: Comment) => PENDING.has(c.reply_status ?? "");

    const pairs = () => (pair.current ? 1 : 0); // D-485: the answer bubble takes a held slot
    const closePair = () => {
      pair.current = null;
      stop("pair");
    };
    // D-485: a retracted reply, a hidden question or an animal no longer shown ends the answer bubble
    if (pair.current) {
      const { messageId, commentId, authorId } = pair.current;
      if (!replies.some((r) => r.messageId === messageId) || !visible.has(commentId)
        || !roster.current.some((f) => f.authorId === authorId)) closePair();
    }
    const closeBubble = (commentId: string) => {
      stop(`b:${commentId}`);
      bubbles.current = bubbles.current.filter((b) => b.commentId !== commentId);
    };
    // D-481: a question's bubble and paw end together
    const endHold = (commentId: string) => {
      closeBubble(commentId);
      const authorId = holds.current.get(commentId);
      if (authorId && hands.current.get(authorId) === commentId) hands.current.delete(authorId);
      holds.current.delete(commentId);
      stop(`cap:${commentId}`);
      stop(`ans:${commentId}`);
    };
    // D-481: a waiting question keeps its bubble (if it is still up: never reopened) and raises the paw until it is
    // answered or closed, at most HOLD_CAP_MS from the comment; at most HOLD_MAX held bubbles, the oldest gives way
    const hold = (c: Comment) => {
      const before = hands.current.get(c.author_id);
      if (before && before !== c.comment_id) endHold(before);
      holds.current.set(c.comment_id, c.author_id);
      hands.current.set(c.author_id, c.comment_id);
      const b = bubbles.current.find((x) => x.commentId === c.comment_id);
      if (b && !b.held) {
        // D-487: a host question's bubble is never closed for another question; with no other held bubble to close,
        // this one stays a 4 s chat bubble (the paw is still held)
        const others = bubbles.current.filter((x) => x.held);
        const victim = others.length + pairs() >= HOLD_MAX ? others.find((x) => !isHost(x)) : undefined;
        if (victim) endHold(victim.commentId);
        if (victim || others.length + pairs() < HOLD_MAX) {
          stop(`b:${c.comment_id}`);
          bubbles.current = bubbles.current.map((x) => (x === b ? { ...x, held: true } : x));
        }
      }
      arm(`cap:${c.comment_id}`, Math.max(0, c.received_at + HOLD_CAP_MS - now), () => endHold(c.comment_id));
    };

    // ends: a hidden comment, a question closed back to chat (its status goes back to null after it was pending);
    // "answered" closes 1 s later, or at once when the host answer's hearts start (below), so the animal does not
    // walk off for a moment in between
    for (const [commentId] of [...holds.current]) {
      const c = visible.get(commentId);
      if (!c || (!c.reply_status && asked.current.has(commentId))) endHold(commentId);
      else if (c.reply_status === "answered" && !timers.current.has(`ans:${commentId}`)) {
        arm(`ans:${commentId}`, ANSWER_GRACE_MS, () => endHold(commentId));
      }
    }
    for (const b of [...bubbles.current]) {
      if (!visible.has(b.commentId)) closeBubble(b.commentId); // hidden wins: a hidden comment loses its bubble at once
    }

    // the animal joins at once; its bubble waits for triage's verdict (D-482)
    for (const c of comments) {
      if (seen.current.has(c.comment_id)) continue;
      seen.current.add(c.comment_id);
      const keep = protectedAuthors(comments, me, new Set(roster.current.map((f) => f.authorId)), replied, segmentSince, now);
      const { shown, gone } = place(roster.current, c, keep, scores, now);
      if (gone) {
        // its bubbles, paw and answer bubble go with it (no ghost bubble holding a slot)
        for (const b of bubbles.current.filter((x) => x.authorId === gone.authorId)) {
          if (b.held) endHold(b.commentId);
          else closeBubble(b.commentId);
        }
        for (const [commentId, authorId] of [...holds.current]) if (authorId === gone.authorId) endHold(commentId);
        hands.current.delete(gone.authorId);
        if (pair.current?.authorId === gone.authorId) closePair();
        // a replaced animal fades out
        leaving.current = [...leaving.current.filter((f) => f.authorId !== gone.authorId), gone];
        arm(`l:${gone.authorId}`, LEAVE_MS, () => {
          leaving.current = leaving.current.filter((f) => f.authorId !== gone.authorId);
        });
      }
      // first seen live (not an old one from a snapshot or a replay): it may speak once its verdict is in, however
      // long triage takes
      if (shown && young(c) && (since === undefined || c.received_at > since)) awaiting.current.add(c.comment_id);
    }

    // D-482 (user): a bubble comes up when triage has judged the comment: a question raises the paw with it and is
    // held (D-481); a chat, or a question already answered, gets the 4 s bubble; still pending, nothing (no time
    // fallback). A comment hidden meanwhile never speaks, even if it is unhidden later.
    for (const commentId of [...awaiting.current]) {
      const c = visible.get(commentId);
      if (c?.kind === "pending") continue;
      awaiting.current.delete(commentId);
      if (!c || c.kind === "hide" || !roster.current.some((f) => f.authorId === c.author_id)) continue;
      spoke.current.add(commentId);
      const question = c.kind === "question" && c.reply_status !== "answered";
      const mine = bubbles.current.find((b) => b.authorId === c.author_id);
      if (mine?.held && !question) continue; // a chat never closes a held question, not even the same viewer's
      // one bubble per animal: a new question replaces the same viewer's held one
      if (mine?.held) endHold(mine.commentId);
      else if (mine) closeBubble(mine.commentId);
      if (question) {
        if (pending(c)) asked.current.add(c.comment_id);
        const held = bubbles.current.filter((b) => b.held);
        if (held.length + pairs() >= HOLD_MAX) {
          // D-487: never a host question's bubble; if every held bubble is one, no bubble, the paw goes up for 4 s
          const victim = held.find((b) => !isHost(b));
          if (!victim) {
            hands.current.set(c.author_id, c.comment_id);
            arm(`h:${c.author_id}`, BUBBLE_MS, () => {
              if (hands.current.get(c.author_id) === c.comment_id) hands.current.delete(c.author_id);
            });
            continue;
          }
          endHold(victim.commentId);
        }
        const plain = bubbles.current.find((b) => !b.held);
        if (bubbles.current.length + pairs() >= BUBBLE_MAX && plain) closeBubble(plain.commentId);
        bubbles.current = [...bubbles.current, { authorId: c.author_id, commentId: c.comment_id, text: c.text, held: true }];
        hold(c);
      } else {
        // all slots up: the oldest chat bubble gives way (bursts are sampled, not queued); never a held question,
        // and with at most HOLD_MAX held there is always a chat bubble or a free slot
        if (bubbles.current.length + pairs() >= BUBBLE_MAX) {
          const plain = bubbles.current.find((b) => !b.held);
          if (!plain) continue;
          closeBubble(plain.commentId);
        }
        bubbles.current = [...bubbles.current, { authorId: c.author_id, commentId: c.comment_id, text: c.text, held: false }];
        arm(`b:${c.comment_id}`, BUBBLE_MS, () => closeBubble(c.comment_id));
      }
    }

    // a waiting status on a comment that has already spoken: an open bubble is held from then on; a closed one is
    // not reopened, only the paw goes up. Before the verdict the status waits for it (the bubble brings the paw).
    for (const c of comments) {
      if (!pending(c) || asked.current.has(c.comment_id) || awaiting.current.has(c.comment_id)) continue;
      asked.current.add(c.comment_id);
      if (spoke.current.has(c.comment_id)) hold(c);
    }

    // D-475 hearts: each asker of a reply (D-483: AI, host or brand) published after the first snapshot, if their
    // animal is shown
    if (loaded && cheered.current === null) {
      cheered.current = new Set(answered.map((a) => a.key)); // page load: nothing to celebrate
    } else if (cheered.current) {
      const fresh = new Set<string>(); // replies with an asker not handled yet
      for (const a of answered) {
        if (cheered.current.has(a.key)) continue;
        cheered.current.add(a.key);
        fresh.add(a.key.slice(0, a.key.indexOf(":")));
        if (!roster.current.some((f) => f.authorId === a.authorId)) continue;
        for (const [commentId, authorId] of [...holds.current]) if (authorId === a.authorId) endHold(commentId);
        cheers.current = [...cheers.current.filter((x) => x !== a.authorId), a.authorId];
        while (cheers.current.length > CHEER_MAX) stop(`c:${cheers.current.shift()!}`);
        arm(`c:${a.authorId}`, CHEER_MS, () => {
          cheers.current = cheers.current.filter((x) => x !== a.authorId);
        });
      }
      // D-485: the reply over its question, on this viewer's own animal if it is one of the askers, else on the first
      // asker shown; the paw is down (above) and the animal stays front for PAIR_MS; a newer reply waits until the
      // shown one has had PAIR_MIN_MS (only the latest waits). A question bubble that had closed comes back with it.
      for (const r of replies) {
        if (!fresh.has(r.messageId)) continue;
        const shown = r.askers.filter((a) => visible.has(a.commentId) && roster.current.some((f) => f.authorId === a.authorId));
        const target = shown.find((a) => a.authorId === me) ?? shown[0];
        if (!target) continue;
        const next = { messageId: r.messageId, ...target };
        const start = () => {
          const mine = bubbles.current.find((b) => b.authorId === next.authorId);
          if (mine?.held) endHold(mine.commentId);
          else if (mine) closeBubble(mine.commentId);
          if (!pair.current) {
            const held = bubbles.current.filter((b) => b.held);
            // D-486: the pair adds one held bubble: make room only when the slots are full (was one too early, and
            // closed another viewer's held question); D-487: never a host question's bubble
            const victim = held.length >= HOLD_MAX ? held.find((b) => !isHost(b)) : undefined;
            if (victim) endHold(victim.commentId);
            const plain = bubbles.current.find((b) => !b.held);
            if (bubbles.current.length >= BUBBLE_MAX && plain) closeBubble(plain.commentId);
          }
          pair.current = { ...next, startedAt: Date.now() };
          arm("pair", PAIR_MS, closePair);
        };
        const shownFor = pair.current ? Date.now() - pair.current.startedAt : PAIR_MIN_MS;
        if (shownFor >= PAIR_MIN_MS) {
          stop("pairq");
          start();
        } else {
          arm("pairq", PAIR_MIN_MS - shownFor, start);
        }
      }
    }
    rerender();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- sig and answeredSig stand for the two lists
  }, [sig, answeredSig, me, serverOffsetMs, loaded]);

  // the walk's speed is in px/s, so the durations follow the video's width; walking stops while the tab is hidden
  const shown = roster.current.length > 0;
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const measure = () => el.offsetWidth > 0 && setWidth(el.offsetWidth);
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [shown]);
  useEffect(() => {
    const onVisibility = () => setHidden(document.hidden);
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  // bubbles are placed once their animal has stopped (it stays put while it speaks): kept inside the video by its
  // side of the screen; an older bubble that overlaps another goes up by the measured height of what is below it
  // (D-475; D-485: px, as an answer bubble is taller), never above the top of the video
  useLayoutEffect(() => {
    const crowd = root.current;
    if (!crowd) return;
    const box = crowd.getBoundingClientRect();
    const top = crowd.parentElement?.getBoundingClientRect().top ?? -Infinity;
    const walkerOf = (el: HTMLElement) => el.closest<HTMLElement>("[data-testid^='viewer-figure-']");
    const els = Array.from(crowd.querySelectorAll<HTMLElement>("[data-testid^='viewer-bubble-']"));
    for (const el of els) {
      const walker = walkerOf(el)?.getBoundingClientRect();
      const at = walker && box.width > 0 ? (walker.left + walker.width / 2 - box.left) / box.width : 0.5;
      el.dataset.edge = at < 0.3 ? "start" : at > 0.7 ? "end" : "mid";
      el.style.setProperty("--lift", "0px");
    }
    const newest = els.sort((a, b) => Number(walkerOf(b)?.style.zIndex) - Number(walkerOf(a)?.style.zIndex));
    // D-486: placed in page coordinates, since the lanes put the bubbles' bottoms up to 14 px apart; the size is the
    // layout size (offsetWidth/Height), as the entry animation scales the drawn rect for a moment
    const placed: { left: number; right: number; top: number; bottom: number }[] = [];
    for (const el of newest) {
      const r = el.getBoundingClientRect();
      const w = el.offsetWidth || r.width;
      const h = el.offsetHeight || r.height;
      const cx = (r.left + r.right) / 2;
      const left = cx - w / 2;
      const right = cx + w / 2;
      const bottom = (r.top + r.bottom) / 2 + h / 2;
      const beside = placed.filter((p) => left < p.right && p.left < right);
      const clear = (lift: number) => beside.every((p) => bottom - lift + 4 <= p.top || bottom - lift - h >= p.bottom + 4);
      const lift = [0, ...beside.map((p) => bottom - p.top + 4)].filter((x) => x >= 0).sort((a, b) => a - b).find(clear) ?? 0;
      const capped = Math.min(lift, Math.max(0, bottom - h - top - 2));
      placed.push({ left, right, top: bottom - capped - h, bottom: bottom - capped });
      el.style.setProperty("--lift", `${Math.round(capped)}px`);
    }
    // D-486: two shown names that overlap (stopped neighbours): the newer speaker's name stays, the other one hides
    const names = Array.from(crowd.querySelectorAll<HTMLElement>(`.${styles.personName}`));
    for (const n of names) delete n.dataset.clash;
    const kept: DOMRect[] = [];
    const shownNames = names.filter((n) => n.dataset.shown !== undefined)
      .sort((a, b) => Number(walkerOf(b)?.style.zIndex) - Number(walkerOf(a)?.style.zIndex));
    for (const n of shownNames) {
      const r = n.getBoundingClientRect();
      if (kept.some((k) => r.left < k.right && k.left < r.right && r.top < k.bottom && k.top < r.bottom)) n.dataset.clash = "";
      else kept.push(r);
    }
  });

  useEffect(() => () => {
    timers.current.forEach(clearTimeout);
    timers.current.clear();
    bubbles.current = [];
    hands.current.clear();
    holds.current.clear();
    cheers.current = [];
    leaving.current = [];
    pair.current = null;
  }, []);

  if (!shown && leaving.current.length === 0) return null;
  const still = reducedMotion();
  const all = [...roster.current.map((f) => ({ f, gone: false })), ...leaving.current.map((f) => ({ f, gone: true }))];
  // D-485: the answer bubble's text is read here, so an edited reply shows its new text
  const shownPair = pair.current;
  const post = shownPair && replies.find((r) => r.messageId === shownPair.messageId);
  const pairQuestion = shownPair && comments.find((c) => c.comment_id === shownPair.commentId);
  const pairView = post && pairQuestion
    ? { question: pairQuestion.text, answer: (shownPair.authorId === me && post.ownText) || post.text, kind: post.kind }
    : null;
  return (
    <div ref={root} className={styles.crowd} aria-hidden data-testid="viewer-crowd" data-paused={hidden || undefined}>
      {all.map(({ f, gone }, i) => {
        const paired = !gone && pairView !== null && shownPair!.authorId === f.authorId;
        const rank = gone || paired ? -1 : bubbles.current.findIndex((b) => b.authorId === f.authorId);
        return (
          <Walker
            key={f.authorId}
            authorId={f.authorId}
            name={f.name}
            species={f.species}
            own={f.authorId === me}
            bubble={rank >= 0 ? bubbles.current[rank]!.text : null}
            rank={paired ? BUBBLE_MAX + 1 : rank + 1}
            hand={!gone && hands.current.has(f.authorId)}
            happy={!gone && cheers.current.includes(f.authorId)}
            leaving={gone}
            still={still}
            spot={CROWD_MAX > 1 ? Math.min(i, CROWD_MAX - 1) / (CROWD_MAX - 1) : 0}
            width={width}
            lane={i % LANES}
            pair={paired ? pairView : null}
            brand={brand}
          />
        );
      })}
    </div>
  );
}

const crowdSig = (p: CrowdProps) =>
  `${p.me}|${p.serverOffsetMs}|${p.loaded}|${p.since}|${p.segmentSince}|${p.brand}|`
  + p.replies.map((r) => `${r.messageId}:${r.kind}:${r.text}:${r.ownText}:${r.askers.map((a) => a.commentId).join(",")}`).join(" ") + "|"
  + p.comments.map((c) => `${c.comment_id}:${c.kind}:${c.reply_status ?? ""}`).join(" ");

/** ViewerView re-renders every second; the crowd only when what it shows from could change. */
export const Crowd = memo(CrowdView, (a, b) => crowdSig(a) === crowdSig(b));
