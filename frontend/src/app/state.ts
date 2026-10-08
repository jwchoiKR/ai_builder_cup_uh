// Event-sourced client state (DEV_SPEC §12.1): state = reduce(snapshot, events).
// Reducers are pure and idempotent: events with seq <= lastSeq are skipped, and every collection is
// an upsert by id, because events after /state's last_seq may already be in the snapshot.
import type {
  AgentCall,
  SessionMarket,
  Alert,
  Answer,
  Comment,
  CommentAnalysis,
  FeedState,
  HostCue,
  HostSlot,
  Message,
  Metrics,
  PdCard,
  PrompterSnapshot,
  QuestionGroup,
  Role,
  Segment,
  Session,
  SessionEvent,
  StateSnapshot,
  SwitchState,
  Transcript,
  VerifyHealth,
} from "./types";

export interface OvertimeInfo {
  segment_id: string;
  product_id: string;
  overtime_sec?: number;
}

export interface MissingPoints {
  seq: number;
  segment_id: string;
  product_id: string;
  missing_point_ids: string[];
  missing_texts?: string[];
}

export interface JudgeFailure {
  seq: number;
  transcript_id: string;
  status?: string;
  alert_ids?: string[];
  /** D-412: "busy" (429), "timeout", "invalid" or "error", and when (server time); D-416: which judge */
  cause?: string;
  at?: number;
  agent?: string;
}

/** D-412: the lines no judge could check since the judges last answered a line normally */
export interface Unchecked {
  ids: string[];
  /** the most recent failure's cause and time (on a tie, the later event) */
  cause: string | null;
  at?: number | null;
}

export interface OperatorAction {
  seq: number;
  payload: Record<string, unknown>;
}

export interface ClientState {
  role: Role;
  loaded: boolean;
  lastSeq: number;
  /** server time minus client time at snapshot, for countdowns and timers */
  serverOffsetMs: number;
  session: Session | null;
  segments: Record<string, Segment>;
  groups: Record<string, QuestionGroup>;
  answers: Record<string, Answer>;
  hostSlots: HostSlot[];
  comments: Record<string, Comment>;
  analyses: Record<string, CommentAnalysis>;
  messages: Record<string, Message>;
  alerts: Record<string, Alert>;
  transcripts: Record<string, Transcript>;
  interim: Transcript | null;
  prompter: PrompterSnapshot | null;
  metrics: Metrics;
  feed: FeedState | null;
  agentCalls: AgentCall[]; // newest first, max 50
  actions: OperatorAction[]; // newest first, max 50
  overtime: Record<string, OvertimeInfo>;
  missingPoints: MissingPoints[];
  judgeFailures: JudgeFailure[];
  unchecked: Unchecked;
  /** D-137: judges that failed on the last finals in a row (empty: healthy) */
  judgeDegraded: string[];
  /** D-306: lines whose candidates the verifier is checking ("transcript id|kind" -> kind): the host's grey chip */
  verifying: Record<string, string>;
  /** D-306: verifier calls with no answer, by cause (operator only) */
  verifyHealth: VerifyHealth | null;
  /** D-335: questions waiting for their answer (transcript id -> the longest wait, ms): the operator's chip */
  holds: Record<string, number>;
  /** D-150: market and language of the session (null before the snapshot) */
  market: SessionMarket | null;
  summaryReady: boolean;
  /** D-320: the test drive's latest host line as speech (its audio is streaming into speech-to-text now) */
  voiceLine: VoiceLine | null;
  /** an event referenced data the client does not have yet (e.g. a new answer): refetch /state */
  needsResync: boolean;
}

export const MAX_LOG = 50;
const MAX_TRANSCRIPTS = 100;

const IDLE_SWITCH: SwitchState = { last_commit: null };

export function emptyState(role: Role): ClientState {
  return {
    role,
    loaded: false,
    lastSeq: 0,
    serverOffsetMs: 0,
    session: null,
    segments: {},
    groups: {},
    answers: {},
    hostSlots: [],
    comments: {},
    analyses: {},
    messages: {},
    alerts: {},
    transcripts: {},
    interim: null,
    prompter: null,
    metrics: {},
    feed: null,
    judgeDegraded: [],
    verifying: {},
    verifyHealth: null,
    holds: {},
    market: null,
    agentCalls: [],
    actions: [],
    overtime: {},
    missingPoints: [],
    judgeFailures: [],
    unchecked: { ids: [], cause: null },
    summaryReady: false,
    voiceLine: null,
    needsResync: false,
  };
}

export interface VoiceLine {
  url: string;
  text: string;
  seq: number;
}

function byId<T, K extends keyof T>(items: T[] | undefined, key: K): Record<string, T> {
  const out: Record<string, T> = {};
  for (const item of items ?? []) out[String(item[key])] = item;
  return out;
}

function keepComment(c: Partial<Comment>, role: Role): boolean {
  return role === "operator" || c.visibility !== "hidden";
}

export function reduceSnapshot(snap: StateSnapshot, role: Role, clientNow: number = Date.now()): ClientState {
  const comments = (snap.comments ?? []).filter((c) => keepComment(c, role));
  const transcripts = (snap.transcripts ?? []).slice(-MAX_TRANSCRIPTS);
  return {
    ...emptyState(role),
    loaded: true,
    lastSeq: snap.last_seq ?? 0,
    serverOffsetMs: snap.server_time ? snap.server_time - clientNow : 0,
    session: snap.session ?? null,
    segments: byId(snap.segments, "segment_id"),
    groups: byId(snap.groups, "group_id"),
    answers: { ...(snap.answers ?? {}) },
    hostSlots: snap.host_slots ?? snap.session?.host_slots ?? [],
    comments: byId(comments, "comment_id"),
    analyses: role === "operator" ? { ...(snap.analyses ?? {}) } : {},
    messages: byId(snap.messages, "message_id"),
    alerts: byId(snap.alerts, "alert_id"),
    transcripts: byId(transcripts, "transcript_id"),
    prompter: snap.prompter ?? null,
    metrics: snap.metrics ?? {},
    feed: snap.feed ?? null,
    judgeDegraded: snap.judge_health?.degraded ?? [],
    // D-412: kept on refresh: the last 5 minutes' failures and the lines unchecked now
    judgeFailures: (snap.check_failures?.recent ?? []).map((f) => ({ ...f, seq: 0 })),
    unchecked: snap.check_failures?.unchecked ?? { ids: [], cause: null },
    verifyHealth: snap.verify_health ?? null,
    market: snap.market ?? null,
    agentCalls: [...(snap.agent_calls ?? [])].reverse().slice(0, MAX_LOG),
  };
}

function withSession(state: ClientState, patch: (s: Session) => Session): ClientState {
  return state.session ? { ...state, session: patch(state.session) } : state;
}

function upsertComment(state: ClientState, c: Partial<Comment> | undefined): ClientState {
  if (!c || !c.comment_id) return state;
  const comments = { ...state.comments };
  if (!keepComment(c, state.role)) {
    delete comments[c.comment_id];
  } else {
    comments[c.comment_id] = { ...(comments[c.comment_id] ?? {}), ...c } as Comment;
  }
  return { ...state, comments };
}

function prune<T>(items: T[], max: number): T[] {
  return items.length > max ? items.slice(0, max) : items;
}

/** Apply one SSE event. Pure; `clientNow` only stamps client-side display times. */
export function reduceEvent(state: ClientState, ev: SessionEvent, clientNow: number = Date.now()): ClientState {
  if (ev.seq > 0 && ev.seq <= state.lastSeq) return state;
  let next = state;
  try {
    next = applyEvent(state, ev, clientNow);
  } catch (e) {
    // D-350: an event this client cannot apply (an odd payload) is skipped, never a crash of every screen
    console.error("[live] event skipped", ev.type, e);
  }
  return ev.seq > state.lastSeq ? { ...next, lastSeq: ev.seq } : next;
}

function applyEvent(state: ClientState, ev: SessionEvent, clientNow: number): ClientState {
  const p = ev.payload ?? {};
  switch (ev.type) {
    case "session.started":
    case "session.ended":
      return { ...state, session: { ...(state.session ?? {}), ...p } as Session };

    case "segment.started": {
      const seg = p as Segment;
      const known = Boolean(state.segments[seg.segment_id]);
      const segments: Record<string, Segment> = {};
      let closedId: string | null = null;
      for (const [id, s] of Object.entries(state.segments)) {
        if (id !== seg.segment_id && s.ended_at === null && s.started_at <= seg.started_at) {
          segments[id] = { ...s, ended_at: seg.started_at };
          closedId = id;
        } else {
          segments[id] = s;
        }
      }
      segments[seg.segment_id] = { ...(state.segments[seg.segment_id] ?? {}), ...seg };
      const switched = !known && (seg.start_reason === "auto_speech" || seg.start_reason === "operator");
      const out = { ...state, segments };
      return withSession(out, (s) => ({
        ...s,
        current_segment_id: seg.segment_id,
        switch: {
          ...IDLE_SWITCH,
          last_commit: switched
            ? { closed_segment_id: closedId ?? "", opened_segment_id: seg.segment_id, at: seg.started_at,
                ...(seg.start_reason === "auto_speech" && s.switch?.decided_target === seg.product_id
                  ? { immediate: true } : {}) }
            : null,
        },
      }));
    }

    case "segment.undone": {
      const segments = { ...state.segments };
      delete segments[p.segment_id];
      return withSession({ ...state, segments }, (s) => ({ ...s, switch: { ...IDLE_SWITCH } }));
    }

    case "segment.extended": {
      // D-138: the on-air segment got more time; an overtime badge for it no longer holds
      const seg = (p as { segment: Segment }).segment;
      const { [seg.segment_id]: _gone, ...overtime } = state.overtime;
      return { ...state, segments: { ...state.segments, [seg.segment_id]: seg }, overtime };
    }

    case "segment.overtime":
      return { ...state, overtime: { ...state.overtime, [p.segment_id]: p as OvertimeInfo } };

    case "segment.switch_decided":
      // D-349: an immediate switch verdict; its segment.started follows at once
      return p.switch ? withSession(state, (s) => ({ ...s, switch: { ...s.switch, decided_target: p.target_product_id } })) : state;

    case "segment.missing_points": {
      if (state.missingPoints.some((m) => m.segment_id === p.segment_id)) return state;
      return { ...state, missingPoints: [...state.missingPoints, { ...p, seq: ev.seq } as MissingPoints] };
    }

    case "prompter.updated": {
      const pr = p as PrompterSnapshot;
      let segments = state.segments;
      if (pr.segment_id && segments[pr.segment_id]) {
        segments = {
          ...segments,
          [pr.segment_id]: { ...segments[pr.segment_id], covered_point_ids: [...pr.covered_point_ids],
            ticked_item_ids: [...(pr.ticked_item_ids ?? segments[pr.segment_id].ticked_item_ids ?? [])] },
        };
      }
      return { ...state, prompter: pr, segments };
    }

    case "transcript.interim":
      return { ...state, interim: p as Transcript };

    case "transcript.final": {
      const t = p as Transcript;
      const transcripts = { ...state.transcripts, [t.transcript_id]: t };
      const ids = Object.values(transcripts).sort((a, b) => a.received_at - b.received_at);
      if (ids.length > MAX_TRANSCRIPTS) for (const old of ids.slice(0, ids.length - MAX_TRANSCRIPTS)) delete transcripts[old.transcript_id];
      return { ...state, transcripts, interim: null };
    }

    case "alert.created":
    case "alert.updated":
    case "alert.escalated": {
      const a = p as Alert;
      return { ...state, alerts: { ...state.alerts, [a.alert_id]: { ...(state.alerts[a.alert_id] ?? {}), ...a } } };
    }

    case "cue.updated": {
      const cue = p as HostCue | null;
      if (!cue) return withSession(state, (s) => ({ ...s, cue: null }));
      const prev = state.session?.cue;
      const doneAt =
        cue.status === "done" ? (prev?.cue_id === cue.cue_id && prev.done_at ? prev.done_at : clientNow) : undefined;
      // A cue update for an older cue never replaces the current active one.
      if (prev && prev.cue_id !== cue.cue_id && cue.created_at < prev.created_at) return state;
      return withSession(state, (s) => ({ ...s, cue: { ...cue, done_at: doneAt } }));
    }

    case "pd.card": {
      const card = ev.payload as PdCard | null; // not `p`: it turns a null payload into {}
      if (!card) return withSession(state, (s) => ({ ...s, pd_card: null }));
      const prev = state.session?.pd_card;
      const doneAt =
        card.status === "done" ? (prev?.card_id === card.card_id && prev.done_at ? prev.done_at : clientNow) : undefined;
      // An update for an older card never replaces the current active one.
      if (prev && prev.card_id !== card.card_id && card.created_at < prev.created_at) return state;
      return withSession(state, (s) => ({ ...s, pd_card: { ...card, done_at: doneAt } }));
    }

    case "comment.created":
    case "comment.hidden":
    case "comment.unhidden":
      return upsertComment(state, (p.comment ?? p) as Partial<Comment>);

    case "comment.analyzed": {
      let out = upsertComment(state, p.comment as Partial<Comment>);
      const analysis = p.analysis as CommentAnalysis | undefined;
      if (analysis && state.role === "operator") {
        out = { ...out, analyses: { ...out.analyses, [analysis.comment_id]: analysis } };
      }
      return out;
    }

    case "group.updated": {
      const g = (p.group ?? p) as QuestionGroup;
      let answers = state.answers;
      const answer = p.answer as Answer | undefined;
      if (answer?.answer_id) answers = { ...answers, [answer.answer_id]: answer };
      const missing = Boolean(g.answer_id && !answers[g.answer_id]);
      return {
        ...state,
        answers,
        groups: { ...state.groups, [g.group_id]: { ...(state.groups[g.group_id] ?? {}), ...g } },
        needsResync: state.needsResync || missing,
      };
    }

    case "hostqueue.updated": {
      const slots = (p.slots ?? []) as HostSlot[];
      return withSession({ ...state, hostSlots: slots }, (s) => ({ ...s, host_slots: slots }));
    }

    case "message.pending":
    case "message.published":
    case "message.updated":
    case "message.cancelled": {
      const m = p as Message;
      return { ...state, messages: { ...state.messages, [m.message_id]: { ...(state.messages[m.message_id] ?? {}), ...m } } };
    }

    case "promo.started":
      return withSession(state, (s) => ({
        ...s,
        active_promos: [
          ...s.active_promos.filter((x) => x.promo_id !== p.promo_id),
          { promo_id: p.promo_id, started_at: p.started_at, ends_at: p.ends_at },
        ],
        active_promo_id: p.changes_prices ? p.promo_id : s.active_promo_id,
        promo_started_at: p.changes_prices ? p.started_at : s.promo_started_at,
      }));

    case "promo.ended":
      return withSession(state, (s) => ({
        ...s,
        active_promos: s.active_promos.filter((x) => x.promo_id !== p.promo_id),
        active_promo_id: s.active_promo_id === p.promo_id ? null : s.active_promo_id,
        promo_started_at: s.active_promo_id === p.promo_id ? null : s.promo_started_at,
      }));

    case "notice.updated":
      return withSession(state, (s) => ({ ...s, pinned_notice: p.pinned_notice ?? null }));

    case "metrics.updated":
      return { ...state, metrics: p as Metrics };

    case "feed.updated":
      return { ...state, feed: p as FeedState };

    case "operator.action":
      if (state.actions.some((a) => a.seq === ev.seq && ev.seq > 0)) return state;
      return { ...state, actions: prune([{ seq: ev.seq, payload: p }, ...state.actions], MAX_LOG) };

    case "agent.call": {
      const call = p as AgentCall;
      return {
        ...state,
        agentCalls: prune([call, ...state.agentCalls.filter((c) => c.call_id !== call.call_id)], MAX_LOG),
      };
    }

    case "judge.failed": {
      // D-416: the server's rule: each failure event (line, judge) counts once; the line is unchecked, and the strip
      // names the latest failure's cause (on a tie, the later event), as the snapshot rebuilds it
      if (state.judgeFailures.some((j) => j.transcript_id === p.transcript_id && j.agent === p.agent)) return state;
      const failures = [...state.judgeFailures, { ...p, seq: ev.seq } as JudgeFailure];
      const id = p.transcript_id as string;
      const ids = state.unchecked.ids.includes(id) ? state.unchecked.ids : [...state.unchecked.ids, id];
      const later = p.at === undefined || state.unchecked.at == null || p.at >= state.unchecked.at;
      const unchecked = later ? { ids, cause: (p.cause as string | undefined) ?? state.unchecked.cause, at: p.at ?? null }
        : { ...state.unchecked, ids };
      return { ...state, judgeFailures: failures, unchecked };
    }

    case "line.check":
      return state;  // D-416: judge.failed carries the same line and cause

    case "checks.recovered": {
      // D-416: only the lines the server cleared (said at or before the line that was answered normally)
      const cleared = new Set((p.cleared as string[] | undefined) ?? state.unchecked.ids);
      const ids = state.unchecked.ids.filter((x) => !cleared.has(x));
      return { ...state, unchecked: ids.length ? { ...state.unchecked, ids } : { ids: [], cause: null, at: null } };
    }

    case "judge.health":
      return { ...state, judgeDegraded: (p.degraded as string[]) ?? [] };

    // D-322: keyed by line and kind, so a fact check finishing first does not clear the compliance check's chip
    case "verify.started":
      return { ...state, verifying: { ...state.verifying, [`${p.transcript_id}|${p.kind}`]: String(p.kind) } };

    case "verify.done": {
      const verifying = { ...state.verifying };
      delete verifying[`${p.transcript_id}|${p.kind}`];
      return { ...state, verifying };
    }

    case "verify.health":
      return { ...state, verifyHealth: p as unknown as VerifyHealth };

    case "hold.started":
      return { ...state, holds: { ...state.holds, [String(p.transcript_id)]: Number(p.max_ms) } };

    case "hold.ended": {
      const holds = { ...state.holds };
      delete holds[String(p.transcript_id)];
      return { ...state, holds };
    }

    case "summary.ready":
      return { ...state, summaryReady: true };

    case "testdrive.audio":
      return { ...state, voiceLine: { url: String(p.url), text: String(p.text), seq: ev.seq } };

    default:
      return state;
  }
}
