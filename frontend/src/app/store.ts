// One event-sourced store per (session, role) (DEV_SPEC §12.1): load /state, then subscribe to SSE
// with after_seq = state.last_seq. Components read derived selectors (selectors.ts) and never poll.
import { useEffect, useState, useSyncExternalStore } from "react";

import { api, type Api } from "./api";
import { openEventStream, type ConnectionStatus, type EventStreamOptions } from "./sse";
import { emptyState, reduceEvent, reduceSnapshot, type ClientState } from "./state";
import type { Catalog, DemoStep, Health, Role, SessionEvent } from "./types";

export interface StoreDeps {
  api: Pick<Api, "state">;
  openEventStream: (opts: EventStreamOptions) => () => void;
  now: () => number;
}

const defaultDeps: StoreDeps = { api, openEventStream, now: () => Date.now() };

const RESYNC_DEBOUNCE_MS = 250;

export class SessionStore {
  private state: ClientState;
  private connection: ConnectionStatus = "connecting";
  private listeners = new Set<() => void>();
  private closeStream: (() => void) | null = null;
  private resyncTimer: ReturnType<typeof setTimeout> | null = null;
  private resyncBuffer: SessionEvent[] | null = null;
  private started = false;
  error: string | null = null;

  constructor(
    readonly sessionId: string,
    readonly role: Role,
    private deps: StoreDeps = defaultDeps,
  ) {
    this.state = emptyState(role);
  }

  getState = (): ClientState => this.state;
  getConnection = (): ConnectionStatus => this.connection;

  subscribe = (fn: () => void): (() => void) => {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  };

  private emit(): void {
    for (const fn of [...this.listeners]) fn();
  }

  private setState(next: ClientState): void {
    if (next === this.state) return;
    this.state = next;
    this.emit();
    if (next.needsResync) this.scheduleResync();
  }

  async start(): Promise<void> {
    if (this.started) return;
    this.started = true;
    try {
      const snap = await this.deps.api.state(this.sessionId, this.role);
      this.setState(reduceSnapshot(snap, this.role, this.deps.now()));
      this.error = null;
    } catch (e) {
      this.error = e instanceof Error ? e.message : String(e);
      this.started = false;
      this.emit();
      return;
    }
    this.closeStream = this.deps.openEventStream({
      sessionId: this.sessionId,
      role: this.role,
      afterSeq: this.state.lastSeq,
      onEvent: (ev) => this.dispatch(ev),
      onStatus: (st) => {
        this.connection = st;
        this.emit();
      },
    });
  }

  dispatch(ev: SessionEvent): void {
    this.resyncBuffer?.push(ev);
    this.setState(reduceEvent(this.state, ev, this.deps.now()));
  }

  private scheduleResync(): void {
    if (this.resyncTimer) return;
    this.resyncTimer = setTimeout(() => {
      this.resyncTimer = null;
      void this.resync();
    }, RESYNC_DEBOUNCE_MS);
  }

  /** Refetch /state; events that arrive meanwhile are replayed on top of the new snapshot. */
  async resync(): Promise<void> {
    if (this.resyncBuffer) return;
    this.resyncBuffer = [];
    try {
      const snap = await this.deps.api.state(this.sessionId, this.role);
      let next = reduceSnapshot(snap, this.role, this.deps.now());
      for (const ev of this.resyncBuffer) next = reduceEvent(next, ev, this.deps.now());
      next = { ...next, lastSeq: Math.max(next.lastSeq, this.state.lastSeq), needsResync: false };
      this.resyncBuffer = null;
      this.setState(next);
    } catch {
      this.resyncBuffer = null;
      this.setState({ ...this.state, needsResync: false });
    }
  }

  stop(): void {
    this.closeStream?.();
    this.closeStream = null;
    if (this.resyncTimer) clearTimeout(this.resyncTimer);
    this.resyncTimer = null;
    this.started = false;
  }
}

// ---- registry: one shared store per (session, role), ref-counted ----------------------------------

const registry = new Map<string, { store: SessionStore; refs: number; closeTimer: ReturnType<typeof setTimeout> | null }>();
const RELEASE_DELAY_MS = 3000; // survives StrictMode remounts and quick pane switches

export function acquireStore(sessionId: string, role: Role): SessionStore {
  const key = `${sessionId}:${role}`;
  let entry = registry.get(key);
  if (!entry) {
    entry = { store: new SessionStore(sessionId, role), refs: 0, closeTimer: null };
    registry.set(key, entry);
  }
  if (entry.closeTimer) {
    clearTimeout(entry.closeTimer);
    entry.closeTimer = null;
  }
  entry.refs += 1;
  void entry.store.start();
  return entry.store;
}

export function releaseStore(store: SessionStore): void {
  const key = `${store.sessionId}:${store.role}`;
  const entry = registry.get(key);
  if (!entry) return;
  entry.refs -= 1;
  if (entry.refs <= 0) {
    entry.closeTimer = setTimeout(() => {
      store.stop();
      registry.delete(key);
    }, RELEASE_DELAY_MS);
  }
}

export interface SessionView {
  state: ClientState;
  connection: ConnectionStatus;
  store: SessionStore | null;
  error: string | null;
}

/** Live client state for one session and role. */
export function useSession(sessionId: string | null, role: Role): SessionView {
  const [store, setStore] = useState<SessionStore | null>(null);
  useEffect(() => {
    if (!sessionId) return;
    const s = acquireStore(sessionId, role);
    setStore(s);
    return () => releaseStore(s);
  }, [sessionId, role]);
  const fallback = useState(() => emptyState(role))[0];
  const state = useSyncExternalStore(
    store?.subscribe ?? noopSubscribe,
    store?.getState ?? (() => fallback),
  );
  const connection = useSyncExternalStore(
    store?.subscribe ?? noopSubscribe,
    store?.getConnection ?? (() => "connecting" as ConnectionStatus),
  );
  return { state, connection, store, error: store?.error ?? null };
}

const noopSubscribe = () => () => undefined;

// ---- cached one-shot resources ---------------------------------------------------------------------

function cachedResource<T>(load: () => Promise<T>) {
  let value: T | null = null;
  let promise: Promise<T> | null = null;
  const listeners = new Set<() => void>();
  const fetchOnce = () => {
    if (!promise) {
      promise = load().then(
        (v) => {
          value = v;
          for (const fn of [...listeners]) fn();
          return v;
        },
        (e) => {
          promise = null; // allow a retry
          throw e;
        },
      );
    }
    return promise;
  };
  return function useResource(): T | null {
    const v = useSyncExternalStore(
      (fn) => {
        listeners.add(fn);
        return () => listeners.delete(fn);
      },
      () => value,
    );
    // D-332: keyed by the resource, so a screen whose session id arrives later (no ?session) loads that catalog
    useEffect(() => {
      if (value === null) void fetchOnce().catch(() => undefined);
    }, [fetchOnce]);
    return v;
  };
}

const catalogs = new Map<string, () => Catalog | null>();

/** D-230: the catalog of this session (an onboarded release has its own product, brand and prices). */
export function useCatalog(sessionId?: string | null): Catalog | null {
  const key = sessionId ?? "";
  let hook = catalogs.get(key);
  if (!hook) {
    hook = cachedResource<Catalog>(() => api.catalog(sessionId));
    catalogs.set(key, hook);
  }
  return hook();
}
export const useHealth = cachedResource<Health>(() => api.health());
export const useDemoScript = cachedResource<DemoStep[]>(() =>
  api.demoScript().then(
    (r) => r.steps,
    () => [],
  ),
);

/** Re-render every `intervalMs` (timers, countdowns, relative times). */
export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return now;
}

/** Server-clock now, using the offset captured from the /state snapshot. */
export function useServerNow(state: ClientState, intervalMs = 1000): number {
  return useNow(intervalMs) + state.serverOffsetMs;
}
