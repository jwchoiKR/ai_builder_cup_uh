from __future__ import annotations

import asyncio
import json

from app.bus import EventBus, format_sse, sse_stream
from app.models.session import Event, HostCue
from app.store.base import sub


async def test_emit_assigns_per_session_seq_and_persists(bus, store, clock):
    a1 = await bus.emit("ses_a", "cue.updated", {"x": 1})
    clock.advance(5)
    a2 = await bus.emit("ses_a", "cue.updated", HostCue(cue_id="cue_1", text="t", created_at=1, status="active"))
    b1 = await bus.emit("ses_b", "cue.updated", {"x": 3})
    assert (a1.seq, a2.seq, b1.seq) == (1, 2, 1)
    assert a2.at == a1.at + 5 and a2.payload["cue_id"] == "cue_1"
    stored = await store.query(sub("ses_a", "events"), Event, order_by="seq")
    assert [e.seq for e in stored] == [1, 2]
    assert [e.seq for e in await bus.events_after("ses_a", 1)] == [2]
    assert await bus.last_seq("ses_a") == 2


async def test_seq_continues_from_store_after_restart(store, clock):
    await EventBus(store, clock).emit("ses_a", "t", {})
    restarted = EventBus(store, clock)
    assert (await restarted.emit("ses_a", "t", {})).seq == 2


async def test_concurrent_emits_are_gapless_and_ordered(bus):
    s = bus.subscribe("ses_a")
    await asyncio.gather(*(bus.emit("ses_a", "t", {"i": i}) for i in range(50)))
    received = [s.queue.get_nowait().seq for _ in range(50)]
    assert received == list(range(1, 51))


def test_format_sse():
    ev = Event(seq=7, session_id="s", type="comment.created", at=1, payload={"text": "hi\nthere"})
    out = format_sse(ev)
    assert out == 'id: 7\nevent: comment.created\ndata: {"text":"hi\\nthere"}\n\n'


async def _next_event(gen):
    while True:
        chunk = await gen.__anext__()
        if chunk.startswith("id: "):
            return chunk


async def test_sse_replays_then_streams_live_without_duplicates(bus):
    await bus.emit("ses_a", "one", {"n": 1})
    await bus.emit("ses_a", "two", {"n": 2})
    gen = sse_stream(bus, "ses_a", after_seq=1, heartbeat_sec=0.05)
    assert await gen.__anext__() == "retry: 1000\n\n"
    assert (await _next_event(gen)).startswith("id: 2\nevent: two\n")
    await bus.emit("ses_a", "three", {"n": 3})
    third = await _next_event(gen)
    assert third.startswith("id: 3\nevent: three\n") and json.loads(third.split("data: ")[1]) == {"n": 3}
    assert await gen.__anext__() == ": heartbeat\n\n"
    await gen.aclose()
    assert bus.subscriber_count("ses_a") == 0


async def test_slow_subscriber_is_dropped_and_stream_ends(store, clock):
    bus = EventBus(store, clock, subscriber_queue_max=2)
    await bus.emit("ses_a", "t", {"i": 0})
    gen = sse_stream(bus, "ses_a", after_seq=0, heartbeat_sec=10)
    await gen.__anext__()  # retry line
    assert (await gen.__anext__()).startswith("id: 1\n")  # replayed; generator paused here
    for i in range(1, 4):  # 3 live events into a queue of 2: the subscriber overflows
        await bus.emit("ses_a", "t", {"i": i})
    assert [c async for c in gen] == []  # stream ends; the client reconnects with Last-Event-ID
    assert bus.subscriber_count("ses_a") == 0
    assert [e.seq for e in await bus.events_after("ses_a", 1)] == [2, 3, 4]  # nothing lost in the store
