"""An in-memory fake of the `google.cloud.firestore.AsyncClient` surface the store uses: collections, document
references, write batches, `stream()` / `order_by().limit().stream()` and `list_documents()`. Commits and reads
can be made to fail. Nothing here talks to a network."""
from __future__ import annotations

import copy


class FakeRef:
    def __init__(self, path: str, doc_id: str) -> None:
        if "/" in doc_id or not doc_id:
            raise ValueError(f"bad document id {doc_id!r}")
        self.path, self.id = path, doc_id


class FakeSnapshot:
    def __init__(self, doc_id: str, data: dict) -> None:
        self.id, self._data = doc_id, data

    def to_dict(self) -> dict:
        return copy.deepcopy(self._data)


class FakeQuery:
    def __init__(self, client: "FakeFirestore", path: str, order: tuple[str, bool] | None = None,
                 count: int | None = None) -> None:
        self._client, self._path, self._order, self._count = client, path, order, count

    def order_by(self, field: str, direction: str = "ASCENDING") -> "FakeQuery":
        return FakeQuery(self._client, self._path, (field, direction == "DESCENDING"), self._count)

    def limit(self, count: int) -> "FakeQuery":
        return FakeQuery(self._client, self._path, self._order, count)

    async def stream(self):
        self._client.reads.append(self._path)
        if self._client.fail_reads:
            raise ConnectionError("fake: read failed")
        docs = list(self._client.docs.get(self._path, {}).items())
        if self._order is not None:
            field, descending = self._order
            docs = [d for d in docs if d[1].get(field) is not None]
            docs.sort(key=lambda d: d[1][field], reverse=descending)
        for doc_id, data in docs[:self._count]:
            yield FakeSnapshot(doc_id, data)


class FakeCollection(FakeQuery):
    def document(self, doc_id: str) -> FakeRef:
        return FakeRef(self._path, doc_id)

    async def list_documents(self, page_size: int | None = None):
        self._client.reads.append(self._path)
        if self._client.fail_reads:
            raise ConnectionError("fake: read failed")
        for doc_id in list(self._client.docs.get(self._path, {})):
            yield FakeRef(self._path, doc_id)


class FakeBatch:
    def __init__(self, client: "FakeFirestore") -> None:
        self._client = client
        self._ops: list[tuple[str, str, dict | None]] = []

    def set(self, ref: FakeRef, data: dict) -> None:
        self._ops.append((ref.path, ref.id, copy.deepcopy(data)))

    def delete(self, ref: FakeRef) -> None:
        self._ops.append((ref.path, ref.id, None))

    async def commit(self) -> None:
        c = self._client
        c.commit_attempts += 1
        if len(self._ops) > 500:
            raise ValueError("fake: more than 500 writes in one commit")
        if c.fail_commits > 0:
            c.fail_commits -= 1
            raise c.fail_with("fake: commit failed")
        if c.reject is not None and any(c.reject(*op) for op in self._ops):
            raise ValueError("fake: invalid document")
        for path, doc_id, data in self._ops:  # all or nothing, like a WriteBatch
            if data is None:
                c.docs.get(path, {}).pop(doc_id, None)
            else:
                c.docs.setdefault(path, {})[doc_id] = data
        c.commits.append(list(self._ops))


class FakeFirestore:
    def __init__(self) -> None:
        self.docs: dict[str, dict[str, dict]] = {}
        self.commits: list[list[tuple[str, str, dict | None]]] = []  # successful commits, in order
        self.commit_attempts = 0
        self.reads: list[str] = []
        self.fail_commits = 0  # the next N commits fail
        self.fail_with: type[Exception] = ConnectionError
        self.fail_reads = False
        self.reject = None  # (path, doc_id, data) -> True: a commit holding this write is refused for good
        self.closed = False

    def collection(self, path: str) -> FakeCollection:
        if len(path.split("/")) % 2 == 0:
            raise ValueError(f"not a collection path: {path!r}")
        return FakeCollection(self, path)

    def batch(self) -> FakeBatch:
        return FakeBatch(self)

    def close(self) -> None:
        self.closed = True

    def seed(self, path: str, doc_id: str, data: dict) -> None:
        self.docs.setdefault(path, {})[doc_id] = copy.deepcopy(data)

    def ops(self) -> list[tuple[str, str, dict | None]]:
        return [op for commit in self.commits for op in commit]
