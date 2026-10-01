"""In-memory store (STORE=memory, default). Documents are stored as JSON dicts and returned as
fresh model copies, like Firestore, so callers never share mutable state with the store."""
from __future__ import annotations

import asyncio
import copy
import operator
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from pydantic import BaseModel

from .base import SESSIONS, SUBCOLLECTIONS, Filter, M

_OPS = {
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "in": lambda a, b: a in b,
}


def _match(doc: dict, where: Sequence[Filter]) -> bool:
    for field, op, value in where:
        actual = doc.get(field)
        if actual is None and op not in ("==", "!=", "in"):
            return False
        if not _OPS[op](actual, value):
            return False
    return True


class MemoryTransaction:
    def __init__(self, store: "MemoryStore") -> None:
        self._store = store
        self._writes: list[tuple[str, str, dict | None]] = []

    async def get(self, path: str, doc_id: str, model: type[M]) -> M | None:
        return self._store._get(path, doc_id, model)

    def put(self, path: str, doc_id: str, doc: BaseModel) -> None:
        self._writes.append((path, doc_id, doc.model_dump(mode="json")))

    def delete(self, path: str, doc_id: str) -> None:
        self._writes.append((path, doc_id, None))

    def _commit(self) -> None:
        for path, doc_id, data in self._writes:
            if data is None:
                self._store._data.get(path, {}).pop(doc_id, None)
            else:
                self._store._data.setdefault(path, {})[doc_id] = data


class MemoryStore:
    name = "memory"

    def __init__(self) -> None:
        self._data: dict[str, dict[str, dict[str, Any]]] = {}
        self._txn_lock = asyncio.Lock()

    def _get(self, path: str, doc_id: str, model: type[M]) -> M | None:
        data = self._data.get(path, {}).get(doc_id)
        return None if data is None else model.model_validate(copy.deepcopy(data))

    async def get(self, path: str, doc_id: str, model: type[M]) -> M | None:
        return self._get(path, doc_id, model)

    async def put(self, path: str, doc_id: str, doc: BaseModel) -> None:
        self._data.setdefault(path, {})[doc_id] = doc.model_dump(mode="json")

    async def delete(self, path: str, doc_id: str) -> None:
        self._data.get(path, {}).pop(doc_id, None)

    async def query(
        self,
        path: str,
        model: type[M],
        *,
        where: Sequence[Filter] = (),
        order_by: str | None = None,
        descending: bool = False,
        limit: int | None = None,
    ) -> list[M]:
        docs = [d for d in self._data.get(path, {}).values() if _match(d, where)]
        if order_by is not None:
            # Like Firestore, documents without the order field are left out.
            docs = [d for d in docs if d.get(order_by) is not None]
            docs.sort(key=lambda d: d[order_by], reverse=descending)
        if limit is not None:
            docs = docs[:limit]
        return [model.model_validate(copy.deepcopy(d)) for d in docs]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[MemoryTransaction]:
        # Memory transactions run one at a time; writes apply only if the block succeeds.
        async with self._txn_lock:
            txn = MemoryTransaction(self)
            yield txn
            txn._commit()

    async def delete_session(self, session_id: str) -> None:
        self._data.get(SESSIONS, {}).pop(session_id, None)
        for name in SUBCOLLECTIONS:
            self._data.pop(f"{SESSIONS}/{session_id}/{name}", None)
