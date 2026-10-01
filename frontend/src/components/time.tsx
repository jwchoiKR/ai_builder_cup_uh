import { formatClock, formatMmSs, relativeTime } from "../app/selectors";
import { useNow } from "../app/store";

/** Countdown to a server-time target: mm:ss (tabular numbers). */
export function Countdown({ until, serverOffsetMs, className }: { until: number; serverOffsetMs: number; className?: string }) {
  const now = useNow(250) + serverOffsetMs;
  return <span className={["tabular", className].filter(Boolean).join(" ")}>{formatMmSs(until - now)}</span>;
}

/** Elapsed time since a server-time start: HH:MM:SS or mm:ss. */
export function Elapsed({
  since,
  serverOffsetMs,
  format = "clock",
  className,
}: {
  since: number;
  serverOffsetMs: number;
  format?: "clock" | "mmss";
  className?: string;
}) {
  const now = useNow(1000) + serverOffsetMs;
  const ms = now - since;
  return (
    <span className={["tabular", className].filter(Boolean).join(" ")}>{format === "clock" ? formatClock(ms) : formatMmSs(ms)}</span>
  );
}

/** "now", "12s", "3m" (§12.3.8). */
export function RelativeTime({ at, serverOffsetMs }: { at: number; serverOffsetMs: number }) {
  const now = useNow(5000) + serverOffsetMs;
  return <span className="tabular">{relativeTime(at, now)}</span>;
}
