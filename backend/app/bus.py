"""In-process event bus (DEV_SPEC §3.6, §11.2, §11.3).

Every state change is emitted here: the event gets the next per-session sequence number, is
persisted to the store, then fanned out to live subscribers (SSE clients). Late or reconnecting
clients replay from the store with `after_seq`.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from collections.abc import AsyncIterator

from pydantic import BaseModel

from .clock import Clock
from .models.session import Event
from .store.base import Store, event_doc_id, sub

log = logging.getLogger(__name__)

HEARTBEAT_SEC = 15.0
SUBSCRIBER_QUEUE_MAX = 5000


class Subscriber:
    def __init__(self, session_id: str, maxsize: int) -> None:
        self.session_id = session_id
        self.queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=maxsize)
        self.dropped = False  # set when the client falls too far behind; it must reconnect

    def offer(self, ev: Event) -> None:
        if self.dropped:
            return
        try:
            self.queue.put_nowait(ev)
        except asyncio.QueueFull:
            self.dropped = True


class EventBus:
    def __init__(self, store: Store, clock: Clock, *, subscriber_queue_max: int = SUBSCRIBER_QUEUE_MAX) -> None:
        self._store = store
        self._clock = clock
        self._queue_max = subscriber_queue_max
        self._seq: dict[str, int] = {}
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._subs: defaultdict[str, set[Subscriber]] = defaultdict(set)

    async def _load_seq(self, session_id: str) -> int:
        if session_id not in self._seq:
            last = await self._store.query(
                sub(session_id, "events"), Event, order_by="seq", descending=True, limit=1
            )
            # D-380: a store that keeps only some events (Firestore without the comment events) gives a floor
            floor = getattr(self._store, "seq_floor", None)
            self._seq[session_id] = max(last[0].seq if last else 0, await floor(session_id) if floor else 0)
        return self._seq[session_id]

    async def last_seq(self, session_id: str) -> int:
        async with self._locks[session_id]:
            return await self._load_seq(session_id)

    async def emit(self, session_id: str, type: str, payload: BaseModel | dict) -> Event:
        data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
        # One lock per session: sequence numbers, persistence order and fan-out order agree.
        async with self._locks[session_id]:
            seq = await self._load_seq(session_id) + 1
            ev = Event(seq=seq, session_id=session_id, type=type, at=self._clock.now_ms(), payload=data)
            await self._store.put(sub(session_id, "events"), event_doc_id(seq), ev)
            self._seq[session_id] = seq
            for s in list(self._subs[session_id]):
                s.offer(ev)
        log.debug("event %s #%d %s", session_id, seq, type)
        return ev

    async def events_after(self, session_id: str, after_seq: int) -> list[Event]:
        return await self._store.query(
            sub(session_id, "events"), Event, where=[("seq", ">", after_seq)], order_by="seq"
        )

    def subscribe(self, session_id: str) -> Subscriber:
        s = Subscriber(session_id, self._queue_max)
        self._subs[session_id].add(s)
        return s

    def unsubscribe(self, s: Subscriber) -> None:
        self._subs[s.session_id].discard(s)

    def subscriber_count(self, session_id: str) -> int:
        return len(self._subs[session_id])

    def forget_session(self, session_id: str) -> None:
        """Drop counters after a session is deleted (demo reset); live subscribers are cut off."""
        self._seq.pop(session_id, None)
        for s in self._subs.pop(session_id, set()):
            s.dropped = True


def format_sse(ev: Event) -> str:
    data = json.dumps(ev.payload, ensure_ascii=False, separators=(",", ":"))
    return f"id: {ev.seq}\nevent: {ev.type}\ndata: {data}\n\n"


OPERATOR_ONLY_EVENTS = frozenset({"agent.call", "transcript.interim"})


def for_role(ev: Event, role: str) -> Event | None:
    """Host and viewer streams never carry hidden comment text or debug events."""
    if role == "operator":
        return ev
    if ev.type in OPERATOR_ONLY_EVENTS:
        return None
    p = ev.payload
    if ev.type.startswith("comment."):
        comment = p.get("comment", p)
        if comment.get("visibility") == "hidden":
            redacted = {"comment_id": comment.get("comment_id"), "visibility": "hidden"}
            return ev.model_copy(update={"payload": {"comment": redacted} if "comment" in p else redacted})
        if "analysis" in p:
            return ev.model_copy(update={"payload": {"comment": comment}})
    return ev


async def sse_stream(
    bus: EventBus, session_id: str, after_seq: int, *, heartbeat_sec: float = HEARTBEAT_SEC, role: str = "operator"
) -> AsyncIterator[str]:
    """Replay persisted events after `after_seq`, then stream live ones, with heartbeats."""
    # Subscribe before replaying so nothing emitted during the replay is lost; duplicates
    # are skipped by sequence number.
    s = bus.subscribe(session_id)
    try:
        yield "retry: 1000\n\n"
        last = after_seq
        for ev in await bus.events_after(session_id, after_seq):
            last = ev.seq
            if (out := for_role(ev, role)) is not None:
                yield format_sse(out)
        while not s.dropped:
            try:
                ev = await asyncio.wait_for(s.queue.get(), timeout=heartbeat_sec)
            except TimeoutError:
                yield ": heartbeat\n\n"
                continue
            if ev.seq <= last:
                continue
            last = ev.seq
            if (out := for_role(ev, role)) is not None:
                yield format_sse(out)
        # Fell behind: end the stream; the browser reconnects with Last-Event-ID and replays.
    finally:
        bus.unsubscribe(s)
