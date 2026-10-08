"""A small in-process stand-in for google.cloud.firestore.AsyncClient: the calls FirestoreStore makes (collection,
document get/set/delete, collection stream, batch, recursive_delete), with counters and injectable failures."""
from __future__ import annotations

import copy


class _Snap:
    def __init__(self, doc_id: str, data: dict | None) -> None:
        self.id = doc_id
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict | None:
        return copy.deepcopy(self._data)


class _DocRef:
    def __init__(self, client: "FakeFirestore", path: str, doc_id: str) -> None:
        self._client, self.path, self.id = client, path, doc_id

    @property
    def full(self) -> str:
        return f"{self.path}/{self.id}"

    async def get(self) -> _Snap:
        self._client.reads += 1
        return _Snap(self.id, self._client.data.get(self.path, {}).get(self.id))

    async def set(self, fields: dict) -> None:
        self._client.check(self.path, self.id, fields)
        self._client.data.setdefault(self.path, {})[self.id] = copy.deepcopy(fields)
        self._client.writes += 1

    async def delete(self) -> None:
        self._client.data.get(self.path, {}).pop(self.id, None)
        self._client.writes += 1


class _Collection:
    def __init__(self, client: "FakeFirestore", path: str) -> None:
        self._client, self.path = client, path

    def document(self, doc_id: str) -> _DocRef:
        return _DocRef(self._client, self.path, doc_id)

    async def stream(self):
        self._client.reads += 1
        for doc_id, data in list(self._client.data.get(self.path, {}).items()):
            yield _Snap(doc_id, data)


class _Batch:
    def __init__(self, client: "FakeFirestore") -> None:
        self._client = client
        self._ops: list[tuple[_DocRef, dict | None]] = []

    def set(self, ref: _DocRef, fields: dict) -> None:
        self._ops.append((ref, fields))

    def delete(self, ref: _DocRef) -> None:
        self._ops.append((ref, None))

    async def commit(self) -> None:
        c = self._client
        if c.fail_next_commits > 0:
            c.fail_next_commits -= 1
            from google.api_core.exceptions import ServiceUnavailable

            raise ServiceUnavailable("scripted outage")
        assert len(self._ops) <= 500, "Firestore allows at most 500 writes in one batch"
        for ref, fields in self._ops:  # all or nothing, like Firestore
            if fields is not None:
                c.check(ref.path, ref.id, fields)
        for ref, fields in self._ops:
            if fields is None:
                c.data.get(ref.path, {}).pop(ref.id, None)
            else:
                c.data.setdefault(ref.path, {})[ref.id] = copy.deepcopy(fields)
        c.writes += len(self._ops)
        c.commits.append(len(self._ops))


class FakeFirestore:
    def __init__(self) -> None:
        self.data: dict[str, dict[str, dict]] = {}
        self.reads = 0
        self.writes = 0
        self.commits: list[int] = []
        self.fail_next_commits = 0
        self.refuse_ids: set[str] = set()  # documents this "Firestore" refuses (InvalidArgument)

    def check(self, path: str, doc_id: str, fields: dict) -> None:
        if doc_id in self.refuse_ids and "_json" not in fields:
            from google.api_core.exceptions import InvalidArgument

            raise InvalidArgument(f"scripted: {path}/{doc_id} refused")
        _no_nested_arrays(fields)

    def collection(self, path: str) -> _Collection:
        return _Collection(self, path)

    def batch(self) -> _Batch:
        return _Batch(self)

    async def recursive_delete(self, ref: _DocRef) -> None:
        self.data.get(ref.path, {}).pop(ref.id, None)
        for path in [p for p in self.data if p.startswith(ref.full + "/")]:
            del self.data[path]

    def count(self, path: str) -> int:
        return len(self.data.get(path, {}))


def _no_nested_arrays(x, in_array: bool = False) -> None:
    if isinstance(x, list):
        if in_array:
            from google.api_core.exceptions import InvalidArgument

            raise InvalidArgument("Cannot convert an array value in an array value")
        for v in x:
            _no_nested_arrays(v, True)
    elif isinstance(x, dict):
        for v in x.values():
            _no_nested_arrays(v)
