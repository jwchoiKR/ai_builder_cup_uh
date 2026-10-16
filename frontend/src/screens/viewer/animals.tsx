// D-476 (user): cute chibi animals for the viewer crowd, drawn in code. One shared body, legs and head; each animal
// swaps its ears, snout, tail and markings. The colours belong to the animals, so they are the same in both themes;
// a light halo keeps dark animals readable on a dark video and a thin ink line keeps light ones readable on a light one.
import type { ReactNode } from "react";

import styles from "./viewer.module.css";

export const SPECIES = ["cat", "dog", "rabbit", "bear", "fox", "panda", "penguin", "hamster"] as const;
export type Species = (typeof SPECIES)[number];

const INK = "#2b2522";
const BLUSH = "#f29a9a";

interface Parts {
  /** side view: the tail, drawn with the body (D-480: the body stands under the head) */
  tail?: ReactNode;
  /** side view: markings on the body or tail, moved with it */
  bodyMarks?: ReactNode;
  /** silhouette, drawn before the body (far ear) */
  under?: ReactNode;
  /** silhouette, drawn after the head (near ear, snout) */
  over?: ReactNode;
  /** markings: no halo */
  marks?: ReactNode;
}

interface Look {
  body: string;
  legs: string;
  head: string;
  /** eye colour (white on a panda's patch) */
  eye?: string;
  side: Parts;
  front: Parts;
}

// mirrored copy of a front-view part around the head's centre line (x = 22)
const mirror = (node: ReactNode) => <g transform="matrix(-1 0 0 1 44 0)">{node}</g>;

const LOOKS: Record<Species, Look> = {
  cat: {
    body: "#f0a254", legs: "#f0a254", head: "#f0a254",
    side: {
      tail: <path d="M11 30C5 29 4 22 6.5 18C7.3 17 8.7 17.6 8.2 19C6.6 23 7.8 26.6 12 27.2Z" fill="#f0a254" />,
      under: <path d="M16.5 11L17.5 2.5L23.5 8Z" fill="#f0a254" />,
      over: <path d="M23 7.5L28.5 2L30.5 9.5Z" fill="#f0a254" />,
      marks: <>
        <path d="M24.6 7.6L28.1 4.2L29.3 8.8Z" fill="#f7c9b5" />
        <path d="M20 8.2q1.4 2 1 4.2M23.4 7.4q1.2 2.2 0.6 4.4" stroke="#c9772f" strokeWidth="1.3" fill="none" strokeLinecap="round" />
        <circle cx="35" cy="19.2" r="1.1" fill="#e47a8a" />
        <path d="M33.5 21.3l5 -1.2M33.5 22.3l5 0.6" stroke={INK} strokeWidth="0.6" strokeLinecap="round" />
      </>,
    },
    front: {
      under: <>
        <path d="M12.5 12L13 3L19.5 8Z" fill="#f0a254" />
        {mirror(<path d="M12.5 12L13 3L19.5 8Z" fill="#f0a254" />)}
      </>,
      marks: <>
        <path d="M14 10L14.3 5.4L17.6 8Z" fill="#f7c9b5" />
        {mirror(<path d="M14 10L14.3 5.4L17.6 8Z" fill="#f7c9b5" />)}
        <path d="M20 7.5v3.2M22 7v3.6M24 7.5v3.2" stroke="#c9772f" strokeWidth="1.3" strokeLinecap="round" />
        <path d="M21 21h2l-1 1.2z" fill="#e47a8a" />
        <path d="M17 22.5l-5 -0.8M17 23.6l-5 0.8" stroke={INK} strokeWidth="0.6" strokeLinecap="round" />
        {mirror(<path d="M17 22.5l-5 -0.8M17 23.6l-5 0.8" stroke={INK} strokeWidth="0.6" strokeLinecap="round" />)}
      </>,
    },
  },
  dog: {
    body: "#d39b62", legs: "#d39b62", head: "#d39b62",
    side: {
      tail: <path d="M11 28C7.5 26.5 6.8 22.5 8.5 20.5C9.6 19.6 10.8 20.6 10.2 22C9.5 24 10.5 25.5 12.5 26Z" fill="#d39b62" />,
      over: <>
        <ellipse cx="33" cy="21.5" rx="4.6" ry="3.6" fill="#f3dcc0" />
        <ellipse cx="20.5" cy="15" rx="3.6" ry="7" transform="rotate(18 20.5 15)" fill="#8b5a33" />
      </>,
      marks: <>
        <ellipse cx="37" cy="20" rx="1.6" ry="1.2" fill={INK} />
        <path d="M33 23.6q1.6 1.2 3 0" stroke={INK} strokeWidth="0.7" fill="none" strokeLinecap="round" />
      </>,
    },
    front: {
      over: <>
        <ellipse cx="22" cy="22.6" rx="4.6" ry="3.4" fill="#f3dcc0" />
        <ellipse cx="11.5" cy="17" rx="3.6" ry="7" transform="rotate(20 11.5 17)" fill="#8b5a33" />
        {mirror(<ellipse cx="11.5" cy="17" rx="3.6" ry="7" transform="rotate(20 11.5 17)" fill="#8b5a33" />)}
      </>,
      marks: <ellipse cx="22" cy="21" rx="1.6" ry="1.2" fill={INK} />,
    },
  },
  rabbit: {
    body: "#eee7de", legs: "#eee7de", head: "#eee7de",
    side: {
      tail: <circle cx="10.5" cy="29" r="3.4" fill="#ffffff" />,
      under: <ellipse cx="20.5" cy="4.5" rx="2.6" ry="7.5" transform="rotate(-14 20.5 4.5)" fill="#eee7de" />,
      over: <ellipse cx="25.5" cy="4" rx="2.8" ry="8" transform="rotate(10 25.5 4)" fill="#eee7de" />,
      marks: <>
        <ellipse cx="25.6" cy="4.5" rx="1.2" ry="5.6" transform="rotate(10 25.6 4.5)" fill="#f4b8c4" />
        <circle cx="35" cy="19.5" r="1" fill="#e57d93" />
        <path d="M34 21q0.8 1 1.6 0" stroke={INK} strokeWidth="0.6" fill="none" strokeLinecap="round" />
      </>,
    },
    front: {
      under: <>
        <ellipse cx="17.5" cy="2.5" rx="2.8" ry="8" transform="rotate(-8 17.5 2.5)" fill="#eee7de" />
        {mirror(<ellipse cx="17.5" cy="2.5" rx="2.8" ry="8" transform="rotate(-8 17.5 2.5)" fill="#eee7de" />)}
      </>,
      marks: <>
        <ellipse cx="17.5" cy="3" rx="1.2" ry="5.6" transform="rotate(-8 17.5 3)" fill="#f4b8c4" />
        {mirror(<ellipse cx="17.5" cy="3" rx="1.2" ry="5.6" transform="rotate(-8 17.5 3)" fill="#f4b8c4" />)}
        <path d="M21 21.2h2l-1 1.1z" fill="#e57d93" />
      </>,
    },
  },
  bear: {
    body: "#9b6b47", legs: "#9b6b47", head: "#9b6b47",
    side: {
      tail: <circle cx="10.5" cy="28" r="2.2" fill="#9b6b47" />,
      under: <circle cx="17.5" cy="9" r="4" fill="#9b6b47" />,
      over: <>
        <circle cx="27" cy="7.8" r="4.2" fill="#9b6b47" />
        <ellipse cx="33" cy="21" rx="4.2" ry="3.4" fill="#d9b48f" />
      </>,
      marks: <>
        <circle cx="27" cy="7.8" r="2.2" fill="#c8946b" />
        <ellipse cx="36.2" cy="19.8" rx="1.5" ry="1.1" fill={INK} />
      </>,
    },
    front: {
      under: <>
        <circle cx="13.5" cy="9" r="4.2" fill="#9b6b47" />
        {mirror(<circle cx="13.5" cy="9" r="4.2" fill="#9b6b47" />)}
      </>,
      over: <ellipse cx="22" cy="22.6" rx="4.2" ry="3.3" fill="#d9b48f" />,
      marks: <>
        <circle cx="13.5" cy="9" r="2.2" fill="#c8946b" />
        {mirror(<circle cx="13.5" cy="9" r="2.2" fill="#c8946b" />)}
        <ellipse cx="22" cy="21.3" rx="1.5" ry="1.1" fill={INK} />
      </>,
    },
  },
  fox: {
    body: "#e8733a", legs: "#5a3a2a", head: "#e8733a",
    side: {
      tail: <path d="M11.5 29C4 30 1 24 3 17.5C4.5 21 7 23.5 12 25.5Z" fill="#e8733a" />,
      under: <path d="M16 11L17 1.5L23 8Z" fill="#e8733a" />,
      bodyMarks: <>
        <path d="M3 17.5C2.4 20 3 22 4.6 23.6C4.2 21.2 4 19.2 3 17.5Z" fill="#fbf3ea" />
        <ellipse cx="24" cy="31" rx="4" ry="4.5" fill="#fbf3ea" />
      </>,
      over: <>
        <path d="M23.5 7.5L29.5 0.5L31 9.5Z" fill="#e8733a" />
        <path d="M30 16.5C33 17 36 18.5 39 20.5C36 22.6 32.5 23.5 29.5 23Z" fill="#fbf3ea" />
      </>,
      marks: <>
        <path d="M27.6 2.8L29.5 0.5L30 3.6Z" fill="#5a3a2a" />
        <circle cx="38.6" cy="20.4" r="1.1" fill={INK} />
      </>,
    },
    front: {
      under: <>
        <path d="M12 13L12.5 1.5L19.5 8Z" fill="#e8733a" />
        {mirror(<path d="M12 13L12.5 1.5L19.5 8Z" fill="#e8733a" />)}
      </>,
      marks: <>
        <path d="M12.4 4.5L12.5 1.5L14.6 3.6Z" fill="#5a3a2a" />
        {mirror(<path d="M12.4 4.5L12.5 1.5L14.6 3.6Z" fill="#5a3a2a" />)}
        <path d="M11.5 19C13.5 24.5 18 27.5 22 28C26 27.5 30.5 24.5 32.5 19C28.5 21 25 21.5 22 23C19 21.5 15.5 21 11.5 19Z" fill="#fbf3ea" />
        <ellipse cx="22" cy="31.5" rx="4" ry="4.2" fill="#fbf3ea" />
        <circle cx="22" cy="22.6" r="1.1" fill={INK} />
      </>,
    },
  },
  panda: {
    body: "#2c2c2e", legs: "#2c2c2e", head: "#f6f5f1", eye: "#ffffff",
    side: {
      tail: <circle cx="10.5" cy="28" r="2.2" fill="#f6f5f1" />,
      under: <circle cx="17.5" cy="8.8" r="4" fill="#2c2c2e" />,
      over: <circle cx="27" cy="7.6" r="4.2" fill="#2c2c2e" />,
      marks: <>
        <ellipse cx="29" cy="17.8" rx="3.2" ry="3.9" transform="rotate(-20 29 17.8)" fill="#2c2c2e" />
        <ellipse cx="35" cy="20.5" rx="1.3" ry="1" fill="#2c2c2e" />
      </>,
    },
    front: {
      under: <>
        <circle cx="13.5" cy="9" r="4.2" fill="#2c2c2e" />
        {mirror(<circle cx="13.5" cy="9" r="4.2" fill="#2c2c2e" />)}
      </>,
      marks: <>
        <ellipse cx="17.6" cy="18.4" rx="3" ry="3.9" transform="rotate(25 17.6 18.4)" fill="#2c2c2e" />
        {mirror(<ellipse cx="17.6" cy="18.4" rx="3" ry="3.9" transform="rotate(25 17.6 18.4)" fill="#2c2c2e" />)}
        <ellipse cx="22" cy="21.6" rx="1.4" ry="1" fill="#2c2c2e" />
      </>,
    },
  },
  penguin: {
    body: "#2f3d55", legs: "#f2a33a", head: "#2f3d55",
    side: {
      over: <path d="M34 17.5L40 20L34 22.5Z" fill="#f2a33a" />,
      marks: <ellipse cx="28" cy="19.5" rx="5.6" ry="6.6" fill="#f7f7f4" />,
      bodyMarks: <>
        <ellipse cx="22" cy="31.5" rx="5.5" ry="5" fill="#f7f7f4" />
        <path d="M15 27C12 30 12.5 34 14.5 35.5C15.5 32.5 16.5 30 17.5 27.5Z" fill="#24304a" />
      </>,
    },
    front: {
      over: <path d="M19.8 21.2H24.2L22 24.4Z" fill="#f2a33a" />,
      marks: <>
        <ellipse cx="18.6" cy="19.5" rx="4.6" ry="5.6" fill="#f7f7f4" />
        {mirror(<ellipse cx="18.6" cy="19.5" rx="4.6" ry="5.6" fill="#f7f7f4" />)}
        <ellipse cx="22" cy="32.5" rx="5.6" ry="5" fill="#f7f7f4" />
      </>,
    },
  },
  hamster: {
    body: "#e8b56f", legs: "#e8b56f", head: "#e8b56f",
    side: {
      under: <circle cx="18.5" cy="8.5" r="3" fill="#e8b56f" />,
      over: <circle cx="26.5" cy="7.6" r="3.2" fill="#e8b56f" />,
      marks: <>
        <circle cx="26.5" cy="7.6" r="1.6" fill="#f2b7a8" />
        <ellipse cx="29" cy="22.5" rx="5" ry="4.2" fill="#fbf1e2" />
        <circle cx="35.3" cy="19.4" r="0.9" fill="#d97a7a" />
      </>,
      bodyMarks: <ellipse cx="22" cy="32" rx="5" ry="4.5" fill="#fbf1e2" />,
    },
    front: {
      under: <>
        <circle cx="14.5" cy="9" r="3.2" fill="#e8b56f" />
        {mirror(<circle cx="14.5" cy="9" r="3.2" fill="#e8b56f" />)}
      </>,
      marks: <>
        <circle cx="14.5" cy="9" r="1.6" fill="#f2b7a8" />
        {mirror(<circle cx="14.5" cy="9" r="1.6" fill="#f2b7a8" />)}
        <ellipse cx="15.8" cy="22.8" rx="4.4" ry="3.6" fill="#fbf1e2" />
        {mirror(<ellipse cx="15.8" cy="22.8" rx="4.4" ry="3.6" fill="#fbf1e2" />)}
        <ellipse cx="22" cy="32.5" rx="5" ry="4.5" fill="#fbf1e2" />
        <path d="M21.2 21h1.6l-0.8 1z" fill="#d97a7a" />
      </>,
    },
  },
};

export interface AnimalProps {
  species: Species;
  view: "side" | "front";
  /** leg step frame; the walking animation alternates them in CSS */
  frame?: 0 | 1 | "both";
  happy?: boolean;
  /** front view only: a raised paw (a question) */
  paw?: boolean;
  className?: string;
}

/** One animal, facing right in the side view (the caller mirrors it to walk left). viewBox -2 -6 48 50. */
export function Animal({ species, view, frame = 0, happy = false, paw = false, className }: AnimalProps) {
  const look = LOOKS[species];
  const parts = view === "side" ? look.side : look.front;
  const side = view === "side";
  const legs = (f: 0 | 1) => {
    const xs = side ? (f === 0 ? [13, 22] : [15.5, 19.5]) : f === 0 ? [16.5, 23.5] : [17, 23];
    return (
      <g className={frame === "both" ? (f === 0 ? styles.legA : styles.legB) : undefined}>
        {xs.map((x) => <rect key={x} x={x} y="34" width="4" height="6.5" rx="2" fill={look.legs} />)}
      </g>
    );
  };
  // the raised paw goes up beside the head, outside it, so it reads at 22-34 px
  const arm = !side && paw && (
    <>
      <path d="M27.5 27.5C31 24 34 18 35.5 11.5L39 12.5C37.8 19.5 34.5 26 30 30.5Z" fill={look.body} />
      <circle cx="37.4" cy="10" r="3" fill={look.body} />
    </>
  );
  // D-480 (user: the walk leaned forward): in the side view the body, legs and tail move under the head, so the
  // animal stands upright; the head and its parts stay where they were
  const under = side ? "translate(4 0)" : undefined;
  const silhouette = (
    <>
      {parts.under}
      <g transform={under}>
        {parts.tail}
        <ellipse cx={side ? 19 : 22} cy={side ? 31 : 32} rx={side ? 9 : 8.5} ry="6.5" fill={look.body} />
        {frame === "both" ? <>{legs(0)}{legs(1)}</> : legs(frame)}
      </g>
      <circle cx={side ? 24 : 22} cy="18" r="11.5" fill={look.head} />
      {parts.over}
      {arm}
    </>
  );
  const eye = look.eye ?? INK;
  const eyes = side ? [29] : [18, 26];
  return (
    <svg className={className} viewBox="-2 -6 48 50" data-species={species} data-view={view}>
      <g className={styles.halo}>{silhouette}</g>
      <g className={styles.ink}>{silhouette}</g>
      {parts.bodyMarks && <g transform={under}>{parts.bodyMarks}</g>}
      {parts.marks}
      {eyes.map((x) =>
        happy ? (
          <path key={x} d={`M${x - 1.9} ${side ? 18.3 : 19} q1.9 -2.4 3.8 0`} stroke={eye} strokeWidth="1.2" fill="none" strokeLinecap="round" />
        ) : (
          <circle key={x} cx={x} cy={side ? 17.6 : 18.4} r="1.7" fill={eye} />
        ),
      )}
      {(side ? [28.5] : [15.5, 28.5]).map((x) => <circle key={x} cx={x} cy="22.6" r="1.8" fill={BLUSH} opacity="0.5" />)}
      {!side && (happy
        ? <path d="M19.8 24.2q2.2 3 4.4 0Z" fill="#c4554f" />
        : <path d="M20.6 24.3q1.4 1.1 2.8 0" stroke={INK} strokeWidth="0.7" fill="none" strokeLinecap="round" />)}
    </svg>
  );
}
