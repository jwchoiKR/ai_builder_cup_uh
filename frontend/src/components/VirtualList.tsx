// Windowed list for chats and streams (§12.10: virtualised beyond 200 rows). Rows have an estimated
// height; only the rows in view (plus overscan) are rendered. Lists of up to `threshold` rows render
// in full, so short lists keep natural row heights.
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

import styles from "./ui.module.css";

export function windowRange(
  count: number,
  scrollTop: number,
  viewportHeight: number,
  rowHeight: number,
  overscan = 8,
): [number, number] {
  if (count === 0) return [0, 0];
  const first = Math.min(count, Math.max(0, Math.floor(scrollTop / rowHeight) - overscan));
  const last = Math.min(count, Math.ceil((scrollTop + viewportHeight) / rowHeight) + overscan);
  return [first, Math.max(first, last)];
}

export function VirtualList<T>({
  items,
  rowHeight = 56,
  threshold = 200,
  stickToBottom = false,
  renderItem,
  getKey,
  className,
}: {
  items: T[];
  rowHeight?: number;
  threshold?: number;
  stickToBottom?: boolean;
  renderItem: (item: T, index: number) => ReactNode;
  getKey: (item: T, index: number) => string;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [height, setHeight] = useState(600);
  const pinned = useRef(true); // at the bottom: keep following new rows

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setHeight(el.clientHeight || 600);
    if (stickToBottom && pinned.current) el.scrollTop = el.scrollHeight;
  }, [items.length, stickToBottom]);

  const onScroll = () => {
    const el = ref.current;
    if (!el) return;
    setScrollTop(el.scrollTop);
    pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
  };

  const windowed = items.length > threshold;
  const [first, last] = windowed ? windowRange(items.length, scrollTop, height, rowHeight) : [0, items.length];
  return (
    <div ref={ref} className={[styles.virtualViewport, className].filter(Boolean).join(" ")} onScroll={onScroll}>
      {windowed && <div style={{ height: first * rowHeight }} aria-hidden />}
      {items.slice(first, last).map((item, i) => (
        <div key={getKey(item, first + i)}>{renderItem(item, first + i)}</div>
      ))}
      {windowed && <div style={{ height: (items.length - last) * rowHeight }} aria-hidden />}
    </div>
  );
}
