"""Viewer-comment documents in Firestore (COMMENTS_FIRESTORE=true). Contract: docs/comments-firestore.md.

The comment path owns five collections of a session: `comments`, `analyses`, `groups`, `answers`, `messages`. This
module is the only code that writes them to Firestore, and it writes nothing else, so it works next to any main store
(STORE=memory, or the show's own Firestore store for sessions, transcripts, alerts and events).

`CommentMirrorStore` wraps the app's store. Every call goes to the wrapped store unchanged, so the runtime reads and
writes exactly as before and never waits on the network. A write to one of the five collections is also queued, and
one background writer sends the queue to Firestore in order, in batches: `sessions/{sid}/<collection>/{id}`, the
document being the model's JSON. Firestore is a durable copy for after the show, behind by the flush interval; this
the only read is `CommentWriter.read`, used once after a show for the summary's comment analysis.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from collections import deque
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from typing import Any

from pydantic import BaseModel

from .base import SESSIONS, Store, Transaction, sub

log = logging.getLogger(__name__)

COMMENT_COLLECTIONS = ("comments", "analyses", "groups", "answers", "messages")

Write = tuple[str, str, dict | None]  # (collection path, document id, data or None for a delete)

FLUSH_INTERVAL_SEC = 0.25  # writes wait this long so repeats of one document become one write
BATCH_MAX_OPS = 400  # documents per commit (the service's limit is 500)
BATCH_MAX_BYTES = 6 * 1024 * 1024  # a commit request may be 10 MiB; stay well under it
MAX_DOC_BYTES = 900_000  # a larger document is not sent (Firestore's limit is 1 MiB)
COMMIT_ATTEMPTS = 5  # then the batch is counted as lost and the queue moves on
COMMIT_TIMEOUT_SEC = 5
RETRY_BASE_SEC = 0.5  # doubles per attempt
RETRY_MAX_SEC = 8
MAX_QUEUE = 50_000  # writes waiting; beyond it the oldest are dropped and counted
CLOSE_TIMEOUT_SEC = 8  # shutdown waits this long for the queue (Cloud Run gives 10 s)


def session_of(path: str) -> str | None:
    """The session of a comment collection path (`sessions/{sid}/comments`), None for every other path."""
    parts = path.split("/")
    return parts[1] if len(parts) == 3 and parts[0] == SESSIONS and parts[2] in COMMENT_COLLECTIONS else None


def under_pytest() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules


def _size(data: dict | None) -> int:
    # Close enough to Firestore's own document size for a limit with a margin.
    return 0 if data is None else len(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _permanent(e: BaseException) -> bool:
    """An error the same request will always get (bad value, bad path): retrying only delays the queue."""
    return isinstance(e, (ValueError, TypeError)) or getattr(e, "code", None) == 400


class _Purge:
    """Queue marker: delete one session's comment collections in Firestore."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id


class CommentWriter:
    """The ordered write-behind queue to Firestore. Groups of writes (one put, or the writes of one transaction) are
    committed together; writes to the same document within a batch are coalesced, the latest wins. A batch that
    keeps failing is retried before anything later is sent, so the order of writes never changes."""

    def __init__(self, project: str, database: str, client: Any | None = None, *,
                 flush_interval_sec: float = FLUSH_INTERVAL_SEC, attempts: int = COMMIT_ATTEMPTS,
                 retry_base_sec: float = RETRY_BASE_SEC, max_queue: int = MAX_QUEUE) -> None:
        if client is None and under_pytest():
            # A test run must never reach the real database: tests inject a fake client.
            raise RuntimeError("CommentWriter: no real Firestore client under pytest; inject a fake client")
        self._project, self.database, self._client = project, database, client
        self._linger, self._attempts, self._retry_base, self._max_queue = (
            flush_interval_sec, max(1, attempts), retry_base_sec, max(1, max_queue))
        self._queue: deque[list[Write] | _Purge] = deque()
        self._depth = 0  # writes waiting in the queue
        self._in_flight = 0  # writes of the batch being committed
        self._task: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self._hurry = asyncio.Event()  # flush(): do not wait for the flush interval
        self._idle = asyncio.Event()
        self._idle.set()
        self._closed = False
        self._written: set[str] = set()  # sessions this process wrote comment documents for
        self._commits = self._committed = self._retries = self._lost = self._oversize = self._failed_purges = 0
        self._last_commit_at: int | None = None
        self._last_error: str | None = None

    def _db(self) -> Any:
        if self._client is None:
            from google.cloud.firestore import AsyncClient  # lazy: only COMMENTS_FIRESTORE=true needs the library

            self._client = AsyncClient(project=self._project, database=self.database)
        return self._client

    # ---- queue ---------------------------------------------------------------------------------------------

    def enqueue(self, writes: list[Write]) -> None:
        if not writes:
            return
        if self._closed:
            self._lost += len(writes)
            log.error("comment mirror: %d write(s) after close are not persisted", len(writes))
            return
        self._written.update(sid for path, _, _ in writes if (sid := session_of(path)) is not None)
        # A group larger than one commit cannot be atomic; it goes as consecutive commits.
        for i in range(0, len(writes), BATCH_MAX_OPS):
            group = writes[i:i + BATCH_MAX_OPS]
            self._queue.append(group)
            self._depth += len(group)
        while self._depth > self._max_queue and len(self._queue) > 1:
            self._drop(self._queue.popleft())  # Firestore unreachable for long: memory must not grow without bound
        self._kick()

    def purge(self, session_id: str) -> None:
        """Delete the session's comment documents in Firestore, if this process wrote any (the database is shared:
        documents of a session written by another process are left alone)."""
        if session_id not in self._written:
            return
        if self._closed:
            self._failed_purges += 1
            return
        self._queue.append(_Purge(session_id))
        self._depth += 1
        self._kick()

    def _drop(self, item: list[Write] | _Purge) -> None:
        if isinstance(item, _Purge):
            self._depth -= 1
            self._failed_purges += 1
            log.error("comment mirror: LOST delete of session %s (queue full)", item.session_id)
        else:
            self._depth -= len(item)
            self._lost += len(item)
            log.error("comment mirror: LOST %d write(s) (queue full), first %s/%s", len(item), item[0][0], item[0][1])

    def _kick(self) -> None:
        self._idle.clear()
        self._wake.set()
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(self._run(), name="comment-mirror-writer")

    # ---- writer --------------------------------------------------------------------------------------------

    async def _run(self) -> None:
        while True:
            await self._wake.wait()
            if self._linger and not self._hurry.is_set():
                try:
                    await asyncio.wait_for(self._hurry.wait(), self._linger)
                except TimeoutError:
                    pass
            self._wake.clear()
            while self._queue:
                try:
                    await self._step()
                except asyncio.CancelledError:
                    raise
                except Exception:  # the show goes on; the durable copy is behind
                    log.exception("comment mirror: writer step failed")
            self._hurry.clear()
            self._idle.set()

    async def _step(self) -> None:
        head = self._queue[0]
        if isinstance(head, _Purge):
            self._queue.popleft()
            self._depth -= 1
            self._in_flight = 1
            try:
                await self._purge(head.session_id)
            finally:
                self._in_flight = 0
            return
        groups = self._take_batch()
        if not groups:
            return
        self._in_flight = sum(len(g) for g in groups)
        try:
            await self._commit_groups(groups)
        finally:
            self._in_flight = 0

    def _take_batch(self) -> list[list[Write]]:
        """Whole groups from the head of the queue, up to one commit's worth of documents and bytes."""
        groups: list[list[Write]] = []
        keys: set[tuple[str, str]] = set()
        size = 0
        while self._queue and not isinstance(self._queue[0], _Purge):
            group = self._queue[0]
            sizes = [_size(data) for _, _, data in group]
            new = {(p, d) for p, d, _ in group} - keys
            if groups and (len(keys) + len(new) > BATCH_MAX_OPS or size + sum(sizes) > BATCH_MAX_BYTES):
                break
            self._queue.popleft()
            self._depth -= len(group)
            fits: list[Write] = []
            for w, n in zip(group, sizes):
                if n > MAX_DOC_BYTES:
                    # Firestore refuses a document over 1 MiB, and with it the whole commit: leave it out.
                    self._oversize += 1
                    log.error("comment mirror: %s/%s is %d bytes, too large for Firestore; not persisted", w[0], w[1], n)
                    continue
                fits.append(w)
                size += n
            if fits:
                groups.append(fits)
                keys |= {(p, d) for p, d, _ in fits}
        return groups

    @staticmethod
    def _coalesce(groups: Iterable[list[Write]]) -> dict[tuple[str, str], dict | None]:
        """The last write to each document wins (a delete after a put stays a delete)."""
        out: dict[tuple[str, str], dict | None] = {}
        for group in groups:
            for path, doc_id, data in group:
                out[(path, doc_id)] = data
        return out

    async def _commit_groups(self, groups: list[list[Write]]) -> None:
        writes = self._coalesce(groups)
        result = await self._commit_with_retry(writes)
        if result == "ok":
            return
        if result == "permanent" and len(groups) > 1:
            # One bad document must not take the rest of the batch with it: each group once, in order.
            for group in groups:
                one = self._coalesce([group])
                try:
                    await self._commit(one)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    self._last_error = f"{type(e).__name__}: {e}"
                    self._lose(one)
            return
        self._lose(writes)

    def _lose(self, writes: dict[tuple[str, str], dict | None]) -> None:
        self._lost += len(writes)
        first = next(iter(writes))
        log.error("comment mirror: LOST %d write(s), first %s/%s, lost so far %d: %s",
                  len(writes), first[0], first[1], self._lost, self._last_error)

    async def _backoff(self, attempt: int) -> None:
        self._retries += 1
        await asyncio.sleep(min(self._retry_base * 2 ** (attempt - 1), RETRY_MAX_SEC))

    async def _commit_with_retry(self, writes: dict[tuple[str, str], dict | None]) -> str:
        """`ok`, `permanent` (the request itself is refused) or `failed` (still failing after every attempt)."""
        for attempt in range(1, self._attempts + 1):
            try:
                await self._commit(writes)
                return "ok"
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._last_error = f"{type(e).__name__}: {e}"
                if _permanent(e):
                    log.error("comment mirror: commit of %d write(s) refused: %s", len(writes), self._last_error)
                    return "permanent"
                log.warning("comment mirror: commit of %d write(s) failed (attempt %d of %d): %s",
                            len(writes), attempt, self._attempts, self._last_error)
                if attempt < self._attempts:
                    await self._backoff(attempt)
        return "failed"

    async def _commit(self, writes: dict[tuple[str, str], dict | None]) -> None:
        db = self._db()
        batch = db.batch()
        for (path, doc_id), data in writes.items():
            ref = db.collection(path).document(doc_id)
            if data is None:
                batch.delete(ref)
            else:
                batch.set(ref, data)
        await asyncio.wait_for(batch.commit(), COMMIT_TIMEOUT_SEC)
        self._commits += 1
        self._committed += len(writes)
        self._last_commit_at = time.time_ns() // 1_000_000

    async def _purge(self, session_id: str) -> None:
        for attempt in range(1, self._attempts + 1):
            try:
                await self._purge_once(session_id)
                return
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._last_error = f"{type(e).__name__}: {e}"
                log.warning("comment mirror: delete of session %s failed (attempt %d of %d): %s",
                            session_id, attempt, self._attempts, self._last_error)
                if _permanent(e):
                    break
                if attempt < self._attempts:
                    await self._backoff(attempt)
        self._failed_purges += 1
        log.error("comment mirror: comment documents of session %s were NOT fully deleted in Firestore", session_id)

    async def _purge_once(self, session_id: str) -> None:
        db = self._db()
        for name in COMMENT_COLLECTIONS:  # the session document and every other collection are not this module's
            refs: list[Any] = []
            async for ref in db.collection(sub(session_id, name)).list_documents(page_size=BATCH_MAX_OPS):
                refs.append(ref)
                if len(refs) >= BATCH_MAX_OPS:
                    await self._delete_refs(refs)
                    refs = []
            if refs:
                await self._delete_refs(refs)

    async def _delete_refs(self, refs: list[Any]) -> None:
        batch = self._db().batch()
        for ref in refs:
            batch.delete(ref)
        await asyncio.wait_for(batch.commit(), COMMIT_TIMEOUT_SEC)
        self._commits += 1
        self._last_commit_at = time.time_ns() // 1_000_000

    async def read(self, session_id: str, names: Iterable[str] = COMMENT_COLLECTIONS,
                   timeout: float = 20) -> dict[str, list[dict]]:
        """The stored documents of a session's comment collections (read only), for analysis after the show."""
        db = self._db()

        async def one(name: str) -> list[dict]:
            return [snap.to_dict() async for snap in db.collection(sub(session_id, name)).stream()]

        names = [n for n in names if n in COMMENT_COLLECTIONS]
        docs = await asyncio.wait_for(asyncio.gather(*(one(n) for n in names)), timeout)
        return dict(zip(names, docs))

    # ---- flush, close, status ------------------------------------------------------------------------------

    async def flush(self, timeout: float | None = None) -> bool:
        """Wait until everything queued so far is committed (or given up). False when the time ran out."""
        if self._idle.is_set():
            return True
        self._hurry.set()
        self._wake.set()
        try:
            await asyncio.wait_for(self._idle.wait(), timeout)
            return True
        except TimeoutError:
            return False

    async def aclose(self) -> None:
        """Shutdown: send what is queued, within CLOSE_TIMEOUT_SEC."""
        if not await self.flush(CLOSE_TIMEOUT_SEC):
            left = self._depth + self._in_flight
            self._lost += left
            log.error("comment mirror: closing with %d write(s) not persisted", left)
        self._closed = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        close = getattr(self._client, "close", None)
        if close is not None:
            try:
                result = close()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                log.warning("comment mirror: closing the client failed", exc_info=True)

    def status(self) -> dict[str, Any]:
        return {
            "database": self.database,
            "queue_depth": self._depth + self._in_flight,
            "last_commit_at": self._last_commit_at,  # epoch ms; None until the first commit
            "commits": self._commits,
            "writes_committed": self._committed,
            "retries": self._retries,
            "lost_writes": self._lost,
            "oversize_skipped": self._oversize,
            "failed_session_deletes": self._failed_purges,
            "last_error": self._last_error,
        }


class CommentMirrorStore:
    """The app's store, with the comment collections also written to Firestore."""

    def __init__(self, inner: Store, writer: CommentWriter) -> None:
        self._inner, self.writer = inner, writer
        self.name = f"{inner.name}+comments"

    def __getattr__(self, attr: str) -> Any:  # get, query and whatever else the wrapped store offers
        return getattr(self._inner, attr)

    async def put(self, path: str, doc_id: str, doc: BaseModel) -> None:
        await self._inner.put(path, doc_id, doc)
        if session_of(path) is not None:
            self.writer.enqueue([(path, doc_id, doc.model_dump(mode="json"))])

    async def delete(self, path: str, doc_id: str) -> None:
        await self._inner.delete(path, doc_id)
        if session_of(path) is not None:
            self.writer.enqueue([(path, doc_id, None)])

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Transaction]:
        async with self._inner.transaction() as txn:
            yield txn
        # Reached only when the block succeeded and the wrapped store has the writes: one group, one commit.
        self.writer.enqueue([w for w in getattr(txn, "_writes", ()) if session_of(w[0]) is not None])

    async def delete_session(self, session_id: str) -> None:
        await self._inner.delete_session(session_id)
        self.writer.purge(session_id)

    async def flush(self, *args: Any, **kwargs: Any) -> Any:
        """The wrapped store's own flush, if it has one, with its arguments; the comment queue first."""
        ok = await self.writer.flush(CLOSE_TIMEOUT_SEC)
        if (inner := getattr(self._inner, "flush", None)) is not None:
            return await inner(*args, **kwargs)
        return ok

    async def aclose(self) -> None:
        await self.writer.aclose()
        if (inner := getattr(self._inner, "aclose", None)) is not None:
            await inner()

    def status(self) -> dict[str, Any]:
        inner = getattr(self._inner, "status", None)
        return {**(inner() if inner is not None else {}), "comments": self.writer.status()}
