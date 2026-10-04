// Typed REST helpers (DEV_SPEC §11.1, §8.13). Errors arrive as {error: {code, message}}.
import type {
  Catalog,
  DemoStep,
  FeedState,
  Health,
  Metrics,
  Role,
  Session,
  StateSnapshot,
} from "./types";

export const API_BASE = "/api";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type Method = "GET" | "POST" | "DELETE";

export async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (e) {
    throw new ApiError(0, "network_error", e instanceof Error ? e.message : "Network error");
  }
  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!res.ok) {
    const err = (data as { error?: { code?: string; message?: string } } | null)?.error;
    throw new ApiError(res.status, err?.code ?? "http_error", err?.message ?? `HTTP ${res.status}`);
  }
  return data as T;
}

const get = <T>(path: string) => request<T>("GET", path);
const post = <T = { ok: boolean }>(path: string, body?: unknown) => request<T>("POST", path, body ?? {});
const del = <T = { ok: boolean }>(path: string) => request<T>("DELETE", path);
const s = (sid: string) => `/sessions/${encodeURIComponent(sid)}`;
const id = (v: string) => encodeURIComponent(v);

export type BurstResult = { burst_id: string; status: "fired" | "armed"; feed: FeedState };
export type AnswerOrigin = "operator_edit" | "operator_written";

export const api = {
  // meta
  health: () => get<Health>("/health"),
  catalog: () => get<Catalog>("/catalog"),

  // demo tools
  demoCurrent: () => get<Session>("/demo/current"),
  demoScript: () => get<{ steps: DemoStep[] }>("/demo/script"),
  demoReset: () => post<Session>("/demo/reset"),
  simulateOvertime: (sid: string) => post(`${s(sid)}/demo/simulate-overtime`),
  feedStart: (sid: string, opts: { pool?: boolean; bursts?: boolean } = { pool: true, bursts: false }) =>
    post<FeedState>(`${s(sid)}/feed/start`, opts),
  feedStop: (sid: string) => post<FeedState>(`${s(sid)}/feed/stop`),
  burst: (sid: string, burstId: string) => post<BurstResult>(`${s(sid)}/feed/burst/${id(burstId)}`),
  injectTranscript: (sid: string, text: string, scene?: string) =>
    post(`${s(sid)}/transcripts`, scene ? { text, scene } : { text }),

  // sessions
  createSession: (runsheetId?: string, showMode?: "solo" | "team") =>
    post<Session>("/sessions", {
      ...(runsheetId ? { runsheet_id: runsheetId } : {}),
      ...(showMode ? { show_mode: showMode } : {}),
    }),
  start: (sid: string) => post<Session>(`${s(sid)}/start`),
  end: (sid: string) => post<Session>(`${s(sid)}/end`),
  state: (sid: string, role: Role) => get<StateSnapshot>(`${s(sid)}/state?role=${role}`),
  metrics: (sid: string) => get<Metrics>(`${s(sid)}/metrics`),
  summary: (sid: string) => get<Record<string, unknown>>(`${s(sid)}/summary`),

  // viewer
  postComment: (sid: string, body: { author_id: string; author_name: string; text: string }) =>
    post(`${s(sid)}/comments`, body),

  // operator: question groups (§8.13)
  pushToHost: (sid: string, gid: string) => post(`${s(sid)}/groups/${id(gid)}/push`),
  recall: (sid: string, gid: string) => post(`${s(sid)}/groups/${id(gid)}/recall`),
  assignProduct: (sid: string, gid: string, productId: string) =>
    post(`${s(sid)}/groups/${id(gid)}/assign-product`, { product_id: productId }),
  approve: (sid: string, gid: string) => post(`${s(sid)}/groups/${id(gid)}/approve`),
  answer: (sid: string, gid: string, text: string, origin: AnswerOrigin, confirm = false) =>
    post(`${s(sid)}/groups/${id(gid)}/answer`, { text, origin, confirm }),
  postSuggested: (sid: string, gid: string) => post(`${s(sid)}/groups/${id(gid)}/post-suggested`),
  reject: (sid: string, gid: string) => post(`${s(sid)}/groups/${id(gid)}/reject`),
  cancelMessage: (sid: string, mid: string) => post(`${s(sid)}/messages/${id(mid)}/cancel`),
  unhide: (sid: string, cid: string) => post(`${s(sid)}/comments/${id(cid)}/unhide`),

  // operator: alerts
  dismissAlert: (sid: string, aid: string) => post(`${s(sid)}/alerts/${id(aid)}/dismiss`),
  alertCue: (sid: string, aid: string) => post(`${s(sid)}/alerts/${id(aid)}/cue`),
  resendFactNote: (sid: string, aid: string) => post(`${s(sid)}/alerts/${id(aid)}/resend`),
  noticeTemplate: (sid: string, aid: string) => get<{ text: string }>(`${s(sid)}/alerts/${id(aid)}/notice-template`),
  postNotice: (sid: string, aid: string, text: string) => post(`${s(sid)}/alerts/${id(aid)}/notice`, { text }),
  alertRendered: (sid: string, aid: string) => post(`${s(sid)}/alerts/${id(aid)}/rendered`),

  // operator: cues, promos, notices
  sendCue: (sid: string, cue: { text: string } | { preset_id: string }) => post(`${s(sid)}/cues`, cue),
  clearCue: (sid: string, cid: string) => del(`${s(sid)}/cues/${id(cid)}`),
  startPromo: (sid: string, pid: string) => post(`${s(sid)}/promos/${id(pid)}/start`),
  stopPromo: (sid: string, pid: string) => post(`${s(sid)}/promos/${id(pid)}/stop`),
  pinNotice: (sid: string, text: string) => post(`${s(sid)}/notices`, { text }),
  unpinNotice: (sid: string) => del(`${s(sid)}/notices`),

  // operator: product switch (§8.7.2)
  switchProduct: (sid: string, productId: string) => post(`${s(sid)}/segments/switch`, { product_id: productId }),
  undoSwitch: (sid: string) => post(`${s(sid)}/segments/undo`),
  cancelSwitch: (sid: string, by: "operator" | "host" = "operator") => post(`${s(sid)}/segments/cancel`, { by }),

  // host: AI PD card
  dismissPdCard: (sid: string, cardId: string) => post(`${s(sid)}/pd/dismiss`, { card_id: cardId }),
  pullQuestion: (sid: string) => post(`${s(sid)}/pd/pull`),
  extendSegment: (sid: string) => post(`${s(sid)}/segments/extend`),
};

export type Api = typeof api;
