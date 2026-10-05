// D-181: a splitter between two panels of a grid. It is a grid item in its own track between them, as wide as the
// gap it replaces, so nothing else moves and it stays between the panels even when one keeps a minimum size. Drag
// it, use the arrow keys (5%) or Home/End, double-click to go back to the default.
import { useRef } from "react";

import { SPLIT_MAX, SPLIT_MIN, splitAt, stepSplit } from "../app/prefs";
import styles from "./ui.module.css";

export function Splitter({
  orientation,
  value,
  onChange,
  onReset,
  label,
  testId,
  min = SPLIT_MIN,
  max = SPLIT_MAX,
}: {
  /** "vertical": a line between two columns; "horizontal": between two rows */
  orientation: "vertical" | "horizontal";
  value: number;
  onChange: (v: number) => void;
  onReset: () => void;
  label: string;
  testId?: string;
  /** the limits of this split (default 25% to 75%) */
  min?: number;
  max?: number;
}) {
  const dragging = useRef(false);
  const vertical = orientation === "vertical";

  const at = (e: React.PointerEvent<HTMLDivElement>) => {
    const box = e.currentTarget.parentElement;
    if (!box) return value;
    const r = box.getBoundingClientRect();
    const own = e.currentTarget.getBoundingClientRect();
    const gap = vertical ? own.width : own.height;
    return vertical ? splitAt(e.clientX, r.left, r.width, gap, min, max) : splitAt(e.clientY, r.top, r.height, gap, min, max);
  };

  return (
    <div
      role="separator"
      tabIndex={0}
      aria-orientation={orientation}
      aria-label={label}
      aria-valuenow={Math.round(value * 100)}
      aria-valuemin={Math.round(min * 100)}
      aria-valuemax={Math.round(max * 100)}
      data-testid={testId}
      className={`${styles.splitter} ${vertical ? styles.splitterV : styles.splitterH}`}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        dragging.current = true;
        e.currentTarget.setPointerCapture?.(e.pointerId);
        e.currentTarget.dataset.dragging = "true";
        e.preventDefault();
      }}
      onPointerMove={(e) => dragging.current && onChange(at(e))}
      onPointerUp={(e) => {
        dragging.current = false;
        delete e.currentTarget.dataset.dragging;
        e.currentTarget.releasePointerCapture?.(e.pointerId);
      }}
      onDoubleClick={onReset}
      onKeyDown={(e) => {
        const next = stepSplit(value, e.key, min, max);
        if (next === null) return;
        e.preventDefault();
        onChange(next);
      }}
    />
  );
}
