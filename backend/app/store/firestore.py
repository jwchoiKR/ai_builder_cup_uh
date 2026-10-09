"""Firestore store (STORE=firestore, D-354).

Memory stays the read model: every get and query is served from memory, so the live path (an alert under the
session lock, `bus.emit` awaiting `store.put`) never waits on the network. Every put and delete is mirrored to
Firestore through one ordered write-behind queue: writes to the same document are coalesced (the latest wins), and
the queue is written in batches of at most 500. It is flushed when a session ends and when the app shuts down
(SIGTERM). A session, its subcollections and so its event seq are read back from Firestore the first time this
process touches it (a new instance continues a show). Write failures are logged loudly and retried; a document that
Firestore refuses is logged as an error, never dropped silently.

Documents are written as their JSON fields with set() (no dotted updates). A document holding an array inside an
array (Firestore has no nested arrays) is written as one JSON string field instead.

D-428 (main merge): this store is the one Firestore writer, for the comment collections too (comments, analyses,
groups, answers, messages: their contract is docs/comments-firestore.md); D-378's memory-only comment data is gone. Ported
from the comments team's session mirror: `read`/`read_session` (the post-show comment analysis reads the durable copy),
`status()` in its shape, `evict` (an ended session leaves memory and is read back when it is opened, `on_loaded` is
called then) and the queue cap with a lost counter.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from collections.abc import AsyncIterator, Iterable, Sequence
from contextlib import asynccontextmanager
from typing import Any

from pydantic import BaseModel

from ..config import Settings
from .base import SESSIONS, SUBCOLLECTIONS, Filter, M, sub
from .memory import MemoryStore, MemoryTransaction

log = logging.getLogger(__name__)

BATCH_MAX = 500  # Firestore's limit on writes in one batch
DOC_MAX_BYTES = 1_000_000  # under Firestore's 1 MiB document limit, with room for field names and overhead
JSON_FIELD = "_json"  # a document with nested arrays, stored as one JSON string
RETRY_FIRST_SEC = 0.5
RETRY_MAX_SEC = 30.0
READ_BACK_TRIES = 3  # D-361: a session is read back whole or not at all; after these tries the call fails
_DELETE_SESSION = object()  # queue marker: delete the session document and every subcollection under it
# D-428: the comment collections the post-show comment analysis reads (docs/comments-firestore.md)
COMMENT_COLLECTIONS = ("comments", "analyses", "groups", "answers", "messages")
MAX_QUEUE = 50_000  # D-428: writes waiting; beyond it the oldest are dropped and counted (Firestore unreachable long)
READ_TIMEOUT_SEC = 20
SEQ_HW = "_event_seq_hw"  # D-380: the highest event seq emitted, on the session document
# D-381: the mark is a reserved ceiling, written once per block of events (not once per event); a new process
# continues after it, so it never reuses a seq a client saw (gaps of up to a block are fine)
HW_BLOCK = 1000


def _nested_array(x: Any, in_array: bool = False) -> bool:
    if isinstance(x, list):
        return in_array or any(_nested_array(v, True) for v in x)
    if isinstance(x, dict):
        return any(_nested_array(v, False) for v in x.values())
    return False


def encode(data: dict) -> dict:
    """The fields written to Firestore for one document."""
    return {JSON_FIELD: json.dumps(data, ensure_ascii=False)} if _nested_array(data) else data


def decode(data: dict) -> dict:
    return json.loads(data[JSON_FIELD]) if JSON_FIELD in data else data


def _refused(e: Exception) -> bool:
    """Firestore refused the request itself (a bad document); retrying it unchanged cannot help."""
    from google.api_core import exceptions as gexc

    return isinstance(e, (gexc.InvalidArgument, gexc.FailedPrecondition, gexc.BadRequest))


def _session_of(path: str, doc_id: str | None = None) -> str | None:
    """The session a path belongs to: `sessions` + its doc id, or `sessions/{sid}/<collection>`."""
    parts = path.split("/")
    if parts[0] != SESSIONS:
        return None
    return parts[1] if len(parts) >= 3 else doc_id


def _under_pytest() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules


def _make_client(settings: Settings):
    if _under_pytest():  # D-428 (from the session mirror): a test run never reaches the real database
        raise RuntimeError("FirestoreStore: no real Firestore client under pytest; inject a fake client")
    from google.cloud import firestore

    return firestore.AsyncClient(project=settings.GCP_PROJECT or None, database=settings.FIRESTORE_DATABASE)


class FirestoreStore(MemoryStore):
    name = "firestore"

    def __init__(self, settings: Settings | None = None, client: Any = None) -> None:
        super().__init__()
        self._client = client if client is not None else _make_client(settings)
        # (path, doc_id) -> fields to set, None to delete, or _DELETE_SESSION; insertion order is write order
        self._queue: dict[tuple[str, str], Any] = {}
        self._wake = asyncio.Event()
        self._idle = asyncio.Event()
        self._idle.set()
        self._flusher: asyncio.Task | None = None
        self._loaded: set[str] = set()  # sessions (and other top-level collections) read back from Firestore
        self._load_locks: dict[str, asyncio.Lock] = {}
        self._retry_now = asyncio.Event()  # D-361: a flush wakes a write retry that is waiting
        self._seq_hw: dict[str, int] = {}  # D-380: session -> the highest event seq emitted (or read back)
        self.failures = 0  # writes Firestore refused or that failed and were retried
        self.database = settings.FIRESTORE_DATABASE if settings is not None else ""
        self.on_loaded = None  # D-428: set by the app; called with a session id after it is read back from Firestore
        # D-428: the session mirror's counters, for status()
        self.commits = self.committed = self.retries = self.lost = self.oversize = self.failed_purges = 0
        self.loaded = self.evicted = 0
        self._written: set[str] = set()  # D-428: sessions this process wrote or read back; only these are deleted
        self.last_commit_at: int | None = None
        self.last_error: str | None = None

    # ---- writes: memory now, Firestore behind -------------------------------------------------------------

    def _enqueue(self, path: str, doc_id: str, value: Any) -> None:
        if "/" in doc_id:
            raise ValueError(f"a Firestore document id cannot hold '/': {path}/{doc_id}")
        if path == SESSIONS and isinstance(value, dict) and doc_id in self._seq_hw:  # D-380: the seq high-water mark
            value = {**value, SEQ_HW: self._seq_hw[doc_id]}
        if value is not _DELETE_SESSION and (sid := _session_of(path, doc_id)) is not None:
            self._written.add(sid)
        key = (path, doc_id)
        self._queue.pop(key, None)  # coalesce: the latest value, at the end of the order
        self._queue[key] = value
        while len(self._queue) > MAX_QUEUE:  # D-428: memory must not grow without bound; the oldest go, counted
            (lost_path, lost_id), lost_value = next(iter(self._queue.items()))
            del self._queue[(lost_path, lost_id)]
            if lost_value is _DELETE_SESSION:
                self.failed_purges += 1
                log.error("firestore: LOST delete of session %s (queue full)", lost_id)
            else:
                self.lost += 1
                log.error("firestore: LOST write of %s/%s (queue full), lost so far %d", lost_path, lost_id, self.lost)
        self._idle.clear()
        self._wake.set()
        if self._flusher is None or self._flusher.done():
            try:
                self._flusher = asyncio.get_running_loop().create_task(self._run(), name="firestore-flusher")
            except RuntimeError:  # no running loop (a sync caller): flush() writes it later
                pass

    async def put(self, path: str, doc_id: str, doc: BaseModel) -> None:
        await self._ensure_loaded(path, doc_id)
        await super().put(path, doc_id, doc)
        self._enqueue(path, doc_id, doc.model_dump(mode="json"))
        sid = _session_of(path, doc_id)
        if path.endswith("/events") and sid is not None and getattr(doc, "seq", 0) > self._seq_hw.get(sid, 0):
            # D-380/381: an event past the reserved ceiling reserves the next block, one session write per HW_BLOCK
            # events
            self._seq_hw[sid] = doc.seq + HW_BLOCK
            session = self._data.get(SESSIONS, {}).get(sid)
            if session is not None:
                self._enqueue(SESSIONS, sid, dict(session))

    async def seq_floor(self, session_id: str) -> int:
        """D-380: the lowest seq the next event may follow: the high-water mark read back with the session."""
        await self._ensure_loaded(sub(session_id, "events"), None)
        return self._seq_hw.get(session_id, 0)

    async def delete(self, path: str, doc_id: str) -> None:
        await self._ensure_loaded(path, doc_id)
        await super().delete(path, doc_id)
        self._enqueue(path, doc_id, None)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[MemoryTransaction]:
        txn: MemoryTransaction
        async with super().transaction() as txn:
            yield txn
        for path, doc_id, data in txn._writes:  # committed in memory: mirror in the same order
            self._enqueue(path, doc_id, data)

    async def delete_session(self, session_id: str) -> None:
        await super().delete_session(session_id)
        self._seq_hw.pop(session_id, None)
        for key in [k for k in self._queue if _session_of(*k) == session_id]:
            del self._queue[key]  # nothing of it needs writing any more
        if session_id in self._written:  # D-428: the database is shared; another process's session is left alone
            self._enqueue(SESSIONS, session_id, _DELETE_SESSION)
        self._loaded.add(session_id)  # an empty session is known; do not read the deleted one back

    # ---- reads: memory, after one read-back per session -----------------------------------------------------

    async def get(self, path: str, doc_id: str, model: type[M]) -> M | None:
        await self._ensure_loaded(path, doc_id)
        return await super().get(path, doc_id, model)

    async def query(self, path: str, model: type[M], *, where: Sequence[Filter] = (), order_by: str | None = None,
                    descending: bool = False, limit: int | None = None) -> list[M]:
        await self._ensure_loaded(path, None)
        return await super().query(path, model, where=where, order_by=order_by, descending=descending, limit=limit)

    async def _ensure_loaded(self, path: str, doc_id: str | None) -> None:
        sid = _session_of(path, doc_id)
        key = sid if sid is not None else path.split("/")[0]
        if key in self._loaded:
            return
        lock = self._load_locks.setdefault(key, asyncio.Lock())
        async with lock:
            if key in self._loaded:
                return
            # D-361: all or nothing. A partial read-back (the session but not its events) would restart the event seq
            # and overwrite stored events, so the read is tried again and, failing that, the call fails loudly.
            for attempt in range(1, READ_BACK_TRIES + 1):
                try:
                    if sid is not None:
                        await self._load_session(sid)
                    else:  # a top-level collection; for `sessions`, the session documents only (each session's
                        await self._load_collection(key)  # subcollections load on its first touch)
                    break
                except Exception as e:  # noqa: BLE001 - said loudly; never served partially
                    log.exception("firestore: read-back of %s failed (try %d of %d)", key, attempt, READ_BACK_TRIES)
                    if attempt == READ_BACK_TRIES:
                        raise RuntimeError(f"firestore: could not read back {key}; not serving it partially") from e
                    await asyncio.sleep(0.2 * attempt)
            self._loaded.add(key)

    def _fill(self, path: str, doc_id: str, data: dict) -> None:
        """A document read back from Firestore, unless memory (or the queue) already holds a newer one."""
        if (path, doc_id) in self._queue:
            return
        self._data.setdefault(path, {}).setdefault(doc_id, decode(data))

    async def _load_session(self, sid: str) -> None:
        """Every document of the session is read first; memory is filled only when all reads succeeded."""
        snap = await self._client.collection(SESSIONS).document(sid).get()
        if not snap.exists:
            return
        self._written.add(sid)
        doc = decode(snap.to_dict())  # D-381: a session stored as one JSON field holds the mark inside it
        hw = doc.pop(SEQ_HW, None)  # D-380: the high-water mark is the store's, not a session field
        staged = [(SESSIONS, sid, doc)]
        for name in SUBCOLLECTIONS:  # D-428: the comment collections too
            path = f"{SESSIONS}/{sid}/{name}"
            async for d in self._client.collection(path).stream():
                staged.append((path, d.id, d.to_dict()))
        for path, doc_id, data in staged:
            self._fill(path, doc_id, data)
        if hw is None:
            # D-430: a session the comments team's mirror wrote (before D-428) has no mark; its last events may not
            # have reached Firestore, so the next seq starts a block past the highest stored one (the mirror jumped
            # ahead on read-back for the same reason). With no stored event no browser saw a seq: no jump.
            last = max((decode(d).get("seq", 0) for p, _, d in staged if p == f"{SESSIONS}/{sid}/events"), default=0)
            hw = last + HW_BLOCK if last else None
        if hw is not None:
            self._seq_hw[sid] = max(self._seq_hw.get(sid, 0), int(hw))
        self.loaded += 1
        log.info("firestore: session %s read back (%d events)", sid,
                 len(self._data.get(f"{SESSIONS}/{sid}/events", {})))
        if self.on_loaded is not None:  # D-428: counter ids continue (Runtimes.session_loaded)
            await self.on_loaded(sid)

    async def _load_collection(self, path: str) -> None:
        staged = [(d.id, d.to_dict()) async for d in self._client.collection(path).stream()]
        for doc_id, data in staged:
            self._fill(path, doc_id, data)

    # ---- the writer ---------------------------------------------------------------------------------------

    async def _run(self) -> None:
        delay = RETRY_FIRST_SEC
        while True:
            if not self._queue:
                self._idle.set()
                self._wake.clear()
                await self._wake.wait()
                continue
            try:
                await self._write_some()
                delay = RETRY_FIRST_SEC
            except Exception as e:  # noqa: BLE001 - the queue keeps every write; retry with backoff
                self.failures += 1
                self.retries += 1
                self.last_error = f"{type(e).__name__}: {e}"
                log.exception("firestore: write failed; %d writes queued, retry in %.1f s", len(self._queue), delay)
                self._retry_now.clear()
                try:  # D-361: a flush (show end, SIGTERM) cuts the wait short and tries again at once
                    await asyncio.wait_for(self._retry_now.wait(), delay)
                except TimeoutError:
                    pass
                delay = min(delay * 2, RETRY_MAX_SEC)

    async def _write_some(self) -> None:
        """One batch (up to BATCH_MAX writes, in queue order) or one session delete. A write stays queued until it
        is committed; a newer write of the same document queued meanwhile is kept."""
        items = []
        for key, value in self._queue.items():
            if value is _DELETE_SESSION:
                if not items:
                    await self._client.recursive_delete(self._client.collection(SESSIONS).document(key[1]))
                    self.commits += 1
                    self.last_commit_at = time.time_ns() // 1_000_000
                    if self._queue.get(key) is _DELETE_SESSION:
                        del self._queue[key]
                break
            items.append((key, value))
            if len(items) >= BATCH_MAX:
                break
        if not items:
            return
        batch = self._client.batch()
        sent = []
        for (path, doc_id), value in items:
            ref = self._client.collection(path).document(doc_id)
            if value is None:
                batch.delete(ref)
            else:
                fields = encode(value)
                size = len(json.dumps(fields, ensure_ascii=False).encode())
                if size > DOC_MAX_BYTES:
                    self.failures += 1
                    self.oversize += 1
                    log.error("firestore: %s/%s is %d bytes, over the 1 MiB document limit; NOT written", path,
                              doc_id, size)
                    sent.append(((path, doc_id), value))
                    continue
                batch.set(ref, fields)
            sent.append(((path, doc_id), value))
        try:
            await batch.commit()
            self.commits += 1
            self.committed += len(sent)
            self.last_commit_at = time.time_ns() // 1_000_000
        except Exception as e:  # noqa: BLE001
            if not _refused(e):
                raise  # transient: the whole batch stays queued and is retried
            self.last_error = f"{type(e).__name__}: {e}"
            await self._write_one_by_one(sent)  # a document Firestore refused must not block the others
        for key, value in sent:
            if self._queue.get(key) is value:  # not rewritten while the batch was in flight
                del self._queue[key]

    async def _write_one_by_one(self, items) -> None:
        for (path, doc_id), value in items:
            ref = self._client.collection(path).document(doc_id)
            tries = [None] if value is None else [encode(value), {JSON_FIELD: json.dumps(value, ensure_ascii=False)}]
            for i, fields in enumerate(tries):
                try:
                    await (ref.delete() if fields is None else ref.set(fields))
                    self.committed += 1
                    break
                except Exception as e:  # noqa: BLE001
                    if not _refused(e):
                        raise
                    if i == len(tries) - 1:
                        self.failures += 1
                        self.lost += 1
                        log.error("firestore: %s/%s refused (%s); NOT written", path, doc_id, e)

    async def flush(self, timeout: float | None = None) -> bool:
        """Wait until every queued write is in Firestore (session end, shutdown). False when it timed out."""
        if self._queue and (self._flusher is None or self._flusher.done()):
            self._flusher = asyncio.get_running_loop().create_task(self._run(), name="firestore-flusher")
        self._wake.set()
        self._retry_now.set()  # D-361: a retry waiting on its backoff tries once more now
        try:
            await asyncio.wait_for(self._idle.wait(), timeout)
            return True
        except TimeoutError:
            log.error("firestore: flush timed out with %d writes still queued", len(self._queue))
            return False

    @property
    def queued(self) -> int:
        return len(self._queue)

    def pending(self, session_id: str) -> int:
        """D-428: writes of this session still waiting in the queue."""
        return sum(1 for key in self._queue if _session_of(*key) == session_id)

    # ---- D-428: ported from the comments team's session mirror ---------------------------------------------

    async def read(self, session_id: str, names: Iterable[str] = COMMENT_COLLECTIONS,
                   timeout: float = READ_TIMEOUT_SEC) -> dict[str, list[dict]]:
        """The stored documents of a session's comment collections (read only), for the analysis after the show."""

        async def one(name: str) -> list[dict]:
            return [decode(snap.to_dict()) async for snap in self._client.collection(sub(session_id, name)).stream()]

        names = [n for n in names if n in SUBCOLLECTIONS]
        docs = await asyncio.wait_for(asyncio.gather(*(one(n) for n in names)), timeout)
        return dict(zip(names, docs))

    async def read_session(self, session_id: str, timeout: float = 30) -> dict[str, dict[str, dict]] | None:
        """A whole stored session as {collection path: {document id: document}}, the session document under
        `sessions`; None when Firestore has no such session. Read only."""
        snap = await asyncio.wait_for(self._client.collection(SESSIONS).document(session_id).get(), timeout)
        if not snap.exists:
            return None

        async def one(name: str) -> tuple[str, dict[str, dict]]:
            path = sub(session_id, name)
            return path, {s.id: decode(s.to_dict()) async for s in self._client.collection(path).stream()}

        session = decode(snap.to_dict())
        session.pop(SEQ_HW, None)
        out: dict[str, dict[str, dict]] = {SESSIONS: {session_id: session}}
        for path, docs in await asyncio.wait_for(asyncio.gather(*(one(n) for n in SUBCOLLECTIONS)), timeout):
            if docs:
                out[path] = docs
        return out

    async def evict(self, session_id: str) -> bool:
        """Drop a session from memory; Firestore keeps it and it is read back when it is opened again. Only when
        nothing of it is still waiting to be written and no write was lost, so the copy that stays is complete.
        False when it was kept in memory."""
        await self.flush(8)
        if self.pending(session_id) or self.lost or self.oversize:  # D-431: a skipped oversized write too
            log.warning("firestore: session %s stays in memory (writes pending or lost)", session_id)
            return False
        await MemoryStore.delete_session(self, session_id)  # memory's copy only: nothing is queued
        self._loaded.discard(session_id)
        self._seq_hw.pop(session_id, None)  # read back with the session document
        self.evicted += 1
        return True

    def status(self) -> dict[str, Any]:
        """The session mirror's shape: "comments" is the key the health page already reads."""
        return {"comments": {
            "database": self.database,
            "queue_depth": len(self._queue),
            "last_commit_at": self.last_commit_at,  # epoch ms; None until the first commit
            "commits": self.commits,
            "writes_committed": self.committed,
            "retries": self.retries,
            "lost_writes": self.lost,
            "oversize_skipped": self.oversize,
            "failed_session_deletes": self.failed_purges,
            "last_error": self.last_error,
        }, "sessions_loaded": self.loaded, "sessions_evicted": self.evicted}

    async def aclose(self, timeout: float = 8.0) -> None:
        await self.flush(timeout)
        if self._flusher is not None:
            self._flusher.cancel()
