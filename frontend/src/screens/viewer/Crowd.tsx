// D-474 (user, like SOOP): viewers on the bottom edge of the video, with a one-line chat bubble over the ones who just
// wrote. D-475 (user): a raised paw when the comment is a question, hearts when the host answers it on air. D-476
// (user): cute animals that walk about and face front only for a question. Display only: built from what the chat
// already shows.
import { memo, useEffect, useLayoutEffect, useReducer, useRef, useState, type CSSProperties } from "react";

import type { Comment } from "../../app/types";
import { Animal, SPECIES, type Species } from "./animals";
import styles from "./viewer.module.css";

export const CROWD_MAX = 6; // D-476: 6 on a 390 px phone (was 10)
export const BUBBLE_MAX = 3;
export const BUBBLE_MS = 4000; // the same as the time-sale pop-up (POPUP_MS)
/** a comment first seen older than this (page load, a reconnect replay) adds its animal but no bubble or paw */
export const BUBBLE_STALE_MS = 10_000;
export const HAND_MS = 4000;
export const CHEER_MS = 2000;
export const CHEER_MAX = 3;
/** D-475: animals with a pending question keep their place in the roster, up to this many */
const PROTECT_MAX = 4;
const PENDING = new Set(["checking", "host", "team"]);
const LEAVE_MS = 400;
const HEARTS = 6;

/** one asker of a published host answer: `key` is message_id:comment_id */
export interface HostAnswered {
  key: string;
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

/** A new commenter joins, or takes the place of the longest-silent animal that is neither the viewer's own nor
 *  waiting for an answer (D-475); if every other animal waits, the longest-silent of them. Returns the one that left. */
function place(roster: Figure[], c: Comment, me: string | null, waiting: Set<string>): Figure | null {
  const known = roster.find((f) => f.authorId === c.author_id);
  if (known) {
    known.lastAt = c.received_at;
    known.name = c.author_name;
    return null;
  }
  const join = (others: Figure[]) =>
    ({ authorId: c.author_id, name: c.author_name, lastAt: c.received_at, species: pickSpecies(c.author_id, others) });
  if (roster.length < CROWD_MAX) {
    roster.push(join(roster));
    return null;
  }
  const oldest = (skip: (f: Figure) => boolean) => {
    let i = -1;
    roster.forEach((f, j) => {
      if (!skip(f) && (i < 0 || f.lastAt < roster[i]!.lastAt)) i = j;
    });
    return i;
  };
  let i = oldest((f) => f.authorId === me || waiting.has(f.authorId));
  if (i < 0) i = oldest((f) => f.authorId === me);
  if (i < 0) return null;
  const gone = roster[i]!;
  roster[i] = join(roster.filter((_, j) => j !== i));
  return gone;
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
}) {
  const stopped = bubble !== null || hand || happy;
  const style: CSSProperties = still
    ? ({ "--spot": spot } as CSSProperties)
    : walkStyle(authorId, width);
  // a speaking animal is in front of the walkers, the newest bubble on top
  style.zIndex = stopped ? 10 + rank : 1;
  const front = hand; // the user: face front only for a question
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
        {bubble !== null && (
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
        <span className={styles.personName}>{name}</span>
        <div className={styles.facing}>
          <Animal
            species={species}
            view={front ? "front" : "side"}
            frame={front || still || stopped ? 0 : "both"}
            happy={happy}
            paw={hand}
            className={styles.animal}
          />
        </div>
      </div>
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
  const roster = useRef<Figure[]>([]);
  const leaving = useRef<Figure[]>([]);
  const seen = useRef(new Set<string>());
  const bubbles = useRef<Bubble[]>([]);
  const hands = useRef(new Map<string, string>()); // author id -> the question's comment id
  const asked = useRef(new Set<string>()); // comment ids whose question status this client has handled
  const cheers = useRef<string[]>([]); // author ids, oldest first
  const cheered = useRef<Set<string> | null>(null); // answer keys already handled; null until the first snapshot
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
      const gone = place(roster.current, c, me, waiting);
      if (gone) {
        // a replaced animal fades out
        leaving.current = [...leaving.current.filter((f) => f.authorId !== gone.authorId), gone];
        arm(`l:${gone.authorId}`, LEAVE_MS, () => {
          leaving.current = leaving.current.filter((f) => f.authorId !== gone.authorId);
        });
      }
      if (now - c.received_at > BUBBLE_STALE_MS) continue;
      // one bubble per animal; at most BUBBLE_MAX, a newer one closes the oldest (bursts are sampled, not queued)
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

    // D-475 paw: the comment pipeline marked it a question (any reply status); only a young comment raises it,
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

    // D-475 hearts: each asker of a host answer published after the first snapshot, if their animal is shown
    if (loaded && cheered.current === null) {
      cheered.current = new Set(answered.map((a) => a.key)); // page load: nothing to celebrate
    } else if (cheered.current) {
      for (const a of answered) {
        if (cheered.current.has(a.key)) continue;
        cheered.current.add(a.key);
        if (!roster.current.some((f) => f.authorId === a.authorId)) continue;
        lower(a.authorId); // happy beats the raised paw
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
  // side of the screen, and an older bubble that overlaps another moves up a row (D-475; the newest on the bottom row)
  useLayoutEffect(() => {
    const box = root.current?.getBoundingClientRect();
    const els = Array.from(root.current?.querySelectorAll<HTMLElement>("[data-testid^='viewer-bubble-']") ?? []);
    for (const el of els) {
      const walker = el.closest<HTMLElement>("[data-testid^='viewer-figure-']")?.getBoundingClientRect();
      const at = box && walker && box.width > 0 ? (walker.left + walker.width / 2 - box.left) / box.width : 0.5;
      el.dataset.edge = at < 0.3 ? "start" : at > 0.7 ? "end" : "mid";
    }
    const newest = els.sort((a, b) =>
      Number(b.closest<HTMLElement>("[data-testid^='viewer-figure-']")?.style.zIndex)
      - Number(a.closest<HTMLElement>("[data-testid^='viewer-figure-']")?.style.zIndex));
    const placed: { left: number; right: number; row: number }[] = [];
    for (const el of newest) {
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
    leaving.current = [];
  }, []);

  if (!shown && leaving.current.length === 0) return null;
  const still = reducedMotion();
  const all = [...roster.current.map((f) => ({ f, gone: false })), ...leaving.current.map((f) => ({ f, gone: true }))];
  return (
    <div ref={root} className={styles.crowd} aria-hidden data-testid="viewer-crowd" data-paused={hidden || undefined}>
      {all.map(({ f, gone }, i) => {
        const rank = gone ? -1 : bubbles.current.findIndex((b) => b.authorId === f.authorId);
        return (
          <Walker
            key={f.authorId}
            authorId={f.authorId}
            name={f.name}
            species={f.species}
            own={f.authorId === me}
            bubble={rank >= 0 ? bubbles.current[rank]!.text : null}
            rank={rank + 1}
            hand={!gone && hands.current.has(f.authorId)}
            happy={!gone && cheers.current.includes(f.authorId)}
            leaving={gone}
            still={still}
            spot={CROWD_MAX > 1 ? Math.min(i, CROWD_MAX - 1) / (CROWD_MAX - 1) : 0}
            width={width}
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
