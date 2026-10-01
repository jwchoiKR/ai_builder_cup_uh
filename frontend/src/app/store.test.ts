import { describe, expect, it, vi } from "vitest";

import { T0, answer, group, snapshot } from "../test/fixtures";
import type { EventStreamOptions } from "./sse";
import { SessionStore } from "./store";
import type { StateSnapshot } from "./types";

function setup(snaps: StateSnapshot[]) {
  let opts: EventStreamOptions | null = null;
  const close = vi.fn();
  const state = vi.fn(async () => snaps.shift()!);
  const store = new SessionStore("ses_000001", "operator", {
    api: { state },
    openEventStream: (o) => {
      opts = o;
      return close;
    },
    now: () => T0 + 10_000,
  });
  return { store, state, close, opts: () => opts! };
}

describe("SessionStore", () => {
  it("loads /state then subscribes with after_seq = last_seq", async () => {
    const { store, opts } = setup([snapshot({ last_seq: 42 })]);
    await store.start();
    expect(store.getState().loaded).toBe(true);
    expect(opts().afterSeq).toBe(42);
    expect(opts().role).toBe("operator");
    opts().onStatus?.("connected");
    expect(store.getConnection()).toBe("connected");
  });

  it("notifies subscribers on events and ignores replays", async () => {
    const { store, opts } = setup([snapshot({ last_seq: 5 })]);
    await store.start();
    const fn = vi.fn();
    store.subscribe(fn);
    opts().onEvent({ seq: 5, type: "group.updated", payload: group() });
    expect(fn).not.toHaveBeenCalled();
    opts().onEvent({ seq: 6, type: "group.updated", payload: group() });
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("resync replays events that arrived during the refetch on top of the new snapshot", async () => {
    let release: (s: StateSnapshot) => void = () => undefined;
    const pending = new Promise<StateSnapshot>((r) => (release = r));
    const snaps = [snapshot({ last_seq: 5 })];
    const state = vi.fn(async () => (snaps.length ? snaps.shift()! : pending));
    let opts: EventStreamOptions | null = null;
    const store = new SessionStore("ses_000001", "operator", {
      api: { state },
      openEventStream: (o) => {
        opts = o;
        return () => undefined;
      },
      now: () => T0,
    });
    await store.start();
    const resync = store.resync();
    opts!.onEvent({ seq: 9, type: "group.updated", payload: group({ group_id: "g_late", score: 3 }) });
    release(snapshot({ last_seq: 8, groups: [group()], answers: { ans_000001: answer() } }));
    await resync;
    const s = store.getState();
    expect(s.lastSeq).toBe(9);
    expect(Object.keys(s.groups).sort()).toEqual(["g_late", "grp_000001"]);
    expect(s.answers.ans_000001).toBeDefined();
    expect(s.needsResync).toBe(false);
  });

  it("stop closes the stream", async () => {
    const { store, close } = setup([snapshot()]);
    await store.start();
    store.stop();
    expect(close).toHaveBeenCalled();
  });
});
