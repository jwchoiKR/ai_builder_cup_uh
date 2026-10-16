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
# D-477: viewers watching, per process: a closed stream still counts this long (a refresh or a reconnect must not
# make the number flicker); ids are capped in length and in number per show
AUDIENCE_GRACE_MS = 10_000
AUDIENCE_MAX = 10_000
VIEWER_ID_MAX = 40


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
        # D-477: session -> viewer id -> (open streams, when the last one closed); memory only, never persisted
        self._audience: dict[str, dict[str, tuple[int, int]]] = {}

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

    def join_audience(self, session_id: str, viewer_id: str) -> bool:
        """D-477: a viewer's stream opened. Two tabs of one browser are one viewer. False when the show's id cap is
        reached (that stream is then not counted)."""
        seen = self._audience.setdefault(session_id, {})
        if viewer_id not in seen and len(seen) >= AUDIENCE_MAX:
            self._prune(session_id)
            if len(seen) >= AUDIENCE_MAX:
                return False
        seen[viewer_id] = (seen.get(viewer_id, (0, 0))[0] + 1, 0)
        return True

    def leave_audience(self, session_id: str, viewer_id: str) -> None:
        seen = self._audience.get(session_id, {})
        if viewer_id in seen:
            seen[viewer_id] = (max(0, seen[viewer_id][0] - 1), self._clock.now_ms())

    def _prune(self, session_id: str) -> None:
        seen = self._audience.get(session_id, {})
        now = self._clock.now_ms()
        for vid, (open_, closed) in list(seen.items()):
            if open_ == 0 and now - closed >= AUDIENCE_GRACE_MS:
                del seen[vid]

    def audience(self, session_id: str) -> set[str]:
        """D-477: the viewer ids with an open stream in this process, or one closed less than AUDIENCE_GRACE_MS ago."""
        self._prune(session_id)
        return set(self._audience.get(session_id, {}))

    def forget_session(self, session_id: str) -> None:
        """Drop counters after a session is deleted (demo reset); live subscribers are cut off."""
        self._seq.pop(session_id, None)
        self._audience.pop(session_id, None)
        for s in self._subs.pop(session_id, set()):
            s.dropped = True


def format_sse(ev: Event) -> str:
    data = json.dumps(ev.payload, ensure_ascii=False, separators=(",", ":"))
    return f"id: {ev.seq}\nevent: {ev.type}\ndata: {data}\n\n"


OPERATOR_ONLY_EVENTS = frozenset({"agent.call", "transcript.interim", "prompter.failed"})  # D-450: operator counts


# A viewer's browser gets the public chat and the show's public state, field by field. An event type or a field
# that is not listed here is not sent: question groups, drafts, analyses, alerts, the host's queue and cards,
# transcripts and metrics stay on the server for this role.
VIEWER_EVENTS = frozenset({
    "session.started", "session.ended", "segment.started", "segment.undone", "segment.extended",
    "comment.created", "comment.hidden", "comment.unhidden", "comment.analyzed", "comment.status",
    "message.published", "message.updated", "promo.started", "promo.ended", "notice.updated",
})
VIEWER_SESSION_FIELDS = (
    "session_id", "runsheet_id", "title", "status", "market", "lang", "started_at", "ended_at",
    "current_segment_id", "active_promo_id", "promo_started_at", "pinned_notice", "active_promos", "created_at",
)
# D-482: "kind" (triage's verdict: pending, reaction, question, hide) so the viewer's animals speak once it is in;
# never the signal, armor or hide category
VIEWER_COMMENT_FIELDS = (
    "comment_id", "author_id", "author_name", "text", "received_at", "visibility", "language", "reply_status", "kind",
)
VIEWER_MESSAGE_FIELDS = (
    "message_id", "kind", "text", "reply_to_comment_ids", "reply_to_author_names", "citations", "state",
    "created_at", "published_at", "translations",
)


def _only(doc: dict, fields: tuple[str, ...]) -> dict:
    return {k: doc[k] for k in fields if k in doc}


def viewer_session(doc: dict) -> dict:
    return _only(doc, VIEWER_SESSION_FIELDS)


# a hidden comment for a viewer: who wrote it and when, so the chat shows "hidden" in its place; never its text
VIEWER_HIDDEN_COMMENT_FIELDS = ("comment_id", "author_id", "author_name", "received_at", "visibility")


def viewer_comment(doc: dict) -> dict:
    if doc.get("visibility") == "hidden":
        return _only(doc, VIEWER_HIDDEN_COMMENT_FIELDS)
    return _only(doc, VIEWER_COMMENT_FIELDS)


def viewer_message(doc: dict) -> dict | None:
    """A reply or notice once it is posted; a post still in its cancel window is not public yet."""
    return _only(doc, VIEWER_MESSAGE_FIELDS) if doc.get("state") == "published" else None


def _for_viewer(ev: Event) -> Event | None:
    if ev.type not in VIEWER_EVENTS:
        return None
    p = ev.payload
    if ev.type.startswith("session."):
        out: dict | None = viewer_session(p)
    elif ev.type.startswith("comment."):
        comment = viewer_comment(p.get("comment", p))
        out = {"comment": comment} if "comment" in p else comment
    elif ev.type.startswith("message."):
        out = viewer_message(p)
    else:
        out = p
    return None if out is None else ev.model_copy(update={"payload": out})


def for_role(ev: Event, role: str) -> Event | None:
    """Host and viewer streams never carry hidden comment text or debug events; a viewer's stream carries only
    the public chat and show state."""
    if role == "operator":
        return ev
    if role == "viewer":
        return _for_viewer(ev)
    if ev.type in OPERATOR_ONLY_EVENTS:
        return None
    p = ev.payload
    if ev.type.startswith("alert.") and p.get("shown_at") is None:  # D-462: not shown to the host yet (ALERT_GRACE)
        return None
    if ev.type.startswith("comment."):
        comment = p.get("comment", p)
        if comment.get("visibility") == "hidden":
            redacted = {"comment_id": comment.get("comment_id"), "visibility": "hidden"}
            return ev.model_copy(update={"payload": {"comment": redacted} if "comment" in p else redacted})
        if "analysis" in p:
            return ev.model_copy(update={"payload": {"comment": comment}})
    return ev


async def sse_stream(
    bus: EventBus, session_id: str, after_seq: int, *, heartbeat_sec: float = HEARTBEAT_SEC, role: str = "operator",
    viewer_id: str | None = None,
) -> AsyncIterator[str]:
    """Replay persisted events after `after_seq`, then stream live ones, with heartbeats. D-477: a viewer stream with
    a `viewer_id` counts that viewer as watching while it is open."""
    # Subscribe before replaying so nothing emitted during the replay is lost; duplicates
    # are skipped by sequence number.
    s = bus.subscribe(session_id)
    counted = role == "viewer" and bool(viewer_id) and bus.join_audience(session_id, viewer_id)
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
        if counted:
            bus.leave_audience(session_id, viewer_id)
