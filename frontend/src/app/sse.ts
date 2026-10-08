// SSE client for /api/sessions/{sid}/events (DEV_SPEC §11.2).
// Every message carries `id: <seq>`, `event: <type>`, `data: <json payload>`. The browser resends
// Last-Event-ID on its own reconnects; when the stream is closed for good (e.g. an HTTP error) we
// reopen it with after_seq = last seen seq.
import { API_BASE } from "./api";
import type { Role, SessionEvent } from "./types";

export type ConnectionStatus = "connecting" | "connected" | "reconnecting" | "closed";

export const EVENT_TYPES = [
  "session.started",
  "session.ended",
  "segment.started",
  "segment.overtime",
  "segment.undone",
  "segment.missing_points",
  "prompter.updated",
  "transcript.interim",
  "transcript.final",
  "alert.created",
  "alert.updated",
  "alert.escalated",
  "cue.updated",
  "pd.card",
  "comment.created",
  "comment.hidden",
  "comment.unhidden",
  "comment.analyzed",
  "group.updated",
  "hostqueue.updated",
  "message.pending",
  "message.published",
  "message.updated",
  "message.cancelled",
  "promo.started",
  "promo.ended",
  "notice.updated",
  "metrics.updated",
  "operator.action",
  "agent.call",
  "judge.failed",
  "judge.health",
  "segment.extended",
  "summary.ready",
  // D-320: emitted but never subscribed before (D-298 line.check, D-306 verify.*), and the test drive's voice
  "feed.updated",
  "line.check",
  "checks.recovered",  // D-412: the judges answered a line normally again
  "verify.started",
  "verify.done",
  "verify.health",
  "testdrive.audio",
  "hold.started",  // D-335: a question waits for its answer (the operator's "collecting context")
  "hold.ended",
  "segment.switch_decided", // D-349 SWITCH_MODE=immediate: each transition verdict (switch or not)
] as const;

export type EventType = (typeof EVENT_TYPES)[number];

let lastType: string | null = null;

/** D-350: the type of the last live event received, for a panel's error report. */
export function lastEventType(): string | null {
  return lastType;
}

export function eventsUrl(sessionId: string, role: Role, afterSeq: number): string {
  return `${API_BASE}/sessions/${encodeURIComponent(sessionId)}/events?after_seq=${afterSeq}&role=${role}`;
}

export interface EventStreamOptions {
  sessionId: string;
  role: Role;
  afterSeq: number;
  onEvent: (ev: SessionEvent) => void;
  onStatus?: (status: ConnectionStatus) => void;
  /** injectable for tests */
  EventSourceImpl?: typeof EventSource;
  reopenDelayMs?: number;
}

/** Opens the stream and returns a close function. */
export function openEventStream(opts: EventStreamOptions): () => void {
  const ES = opts.EventSourceImpl ?? EventSource;
  let lastSeq = opts.afterSeq;
  let source: EventSource | null = null;
  let closed = false;
  let reopenTimer: ReturnType<typeof setTimeout> | null = null;
  const setStatus = (st: ConnectionStatus) => opts.onStatus?.(st);

  const handle = (type: string) => (e: MessageEvent) => {
    lastType = type;
    const seq = Number(e.lastEventId);
    if (Number.isFinite(seq) && seq > 0) {
      if (seq <= lastSeq) return; // already applied
      lastSeq = seq;
    }
    let payload: unknown = null;
    try {
      payload = e.data ? JSON.parse(e.data) : null;
    } catch {
      return;
    }
    opts.onEvent({ seq: Number.isFinite(seq) ? seq : 0, type, payload });
  };

  const open = () => {
    if (closed) return;
    setStatus(lastSeq === opts.afterSeq ? "connecting" : "reconnecting");
    const es = new ES(eventsUrl(opts.sessionId, opts.role, lastSeq));
    source = es;
    es.onopen = () => setStatus("connected");
    es.onerror = () => {
      if (closed) return;
      if (es.readyState === ES.CLOSED) {
        // The browser gave up (HTTP error): reopen ourselves from the last seen seq.
        setStatus("reconnecting");
        es.close();
        reopenTimer = setTimeout(open, opts.reopenDelayMs ?? 2000);
      } else {
        setStatus("reconnecting"); // the browser retries with Last-Event-ID
      }
    };
    for (const t of EVENT_TYPES) es.addEventListener(t, handle(t) as EventListener);
  };

  open();
  return () => {
    closed = true;
    if (reopenTimer) clearTimeout(reopenTimer);
    source?.close();
    setStatus("closed");
  };
}
