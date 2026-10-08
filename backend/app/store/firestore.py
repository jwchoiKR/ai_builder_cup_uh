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
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from pydantic import BaseModel

from ..config import Settings
from .base import SESSIONS, SUBCOLLECTIONS, Filter, M
from .memory import MemoryStore, MemoryTransaction

log = logging.getLogger(__name__)

BATCH_MAX = 500  # Firestore's limit on writes in one batch
DOC_MAX_BYTES = 1_000_000  # under Firestore's 1 MiB document limit, with room for field names and overhead
JSON_FIELD = "_json"  # a document with nested arrays, stored as one JSON string
RETRY_FIRST_SEC = 0.5
RETRY_MAX_SEC = 30.0
READ_BACK_TRIES = 3  # D-361: a session is read back whole or not at all; after these tries the call fails
_DELETE_SESSION = object()  # queue marker: delete the session document and every subcollection under it


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


def _make_client(settings: Settings):
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
        self.failures = 0  # writes Firestore refused or that failed and were retried

    # ---- writes: memory now, Firestore behind -------------------------------------------------------------

    def _enqueue(self, path: str, doc_id: str, value: Any) -> None:
        if "/" in doc_id:
            raise ValueError(f"a Firestore document id cannot hold '/': {path}/{doc_id}")
        key = (path, doc_id)
        self._queue.pop(key, None)  # coalesce: the latest value, at the end of the order
        self._queue[key] = value
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
        for key in [k for k in self._queue if _session_of(*k) == session_id]:
            del self._queue[key]  # nothing of it needs writing any more
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
        staged = [(SESSIONS, sid, snap.to_dict())]
        for name in SUBCOLLECTIONS:
            path = f"{SESSIONS}/{sid}/{name}"
            async for d in self._client.collection(path).stream():
                staged.append((path, d.id, d.to_dict()))
        for path, doc_id, data in staged:
            self._fill(path, doc_id, data)
        log.info("firestore: session %s read back (%d events)", sid,
                 len(self._data.get(f"{SESSIONS}/{sid}/events", {})))

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
            except Exception:  # noqa: BLE001 - the queue keeps every write; retry with backoff
                self.failures += 1
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
                    log.error("firestore: %s/%s is %d bytes, over the 1 MiB document limit; NOT written", path,
                              doc_id, size)
                    sent.append(((path, doc_id), value))
                    continue
                batch.set(ref, fields)
            sent.append(((path, doc_id), value))
        try:
            await batch.commit()
        except Exception as e:  # noqa: BLE001
            if not _refused(e):
                raise  # transient: the whole batch stays queued and is retried
            await self._write_one_by_one(sent)  # a document Firestore refuses must not block the others
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
                    break
                except Exception as e:  # noqa: BLE001
                    if not _refused(e):
                        raise
                    if i == len(tries) - 1:
                        self.failures += 1
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

    async def aclose(self, timeout: float = 8.0) -> None:
        await self.flush(timeout)
        if self._flusher is not None:
            self._flusher.cancel()
