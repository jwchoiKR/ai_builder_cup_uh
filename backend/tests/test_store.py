from __future__ import annotations

import pytest

from app.models.session import Comment
from app.store.base import SESSIONS, sub


def _comment(i: int, author: str = "u_a") -> Comment:
    return Comment(comment_id=f"cm_{i:06d}", author_id=author, author_name="A", text=f"c{i}",
                   received_at=1000 + i, source="script")


async def test_put_get_returns_copies(store):
    path = sub("ses_1", "comments")
    c = _comment(1)
    await store.put(path, c.comment_id, c)
    got = await store.get(path, c.comment_id, Comment)
    assert got == c and got is not c
    got.text = "changed"
    assert (await store.get(path, c.comment_id, Comment)).text == "c1"
    assert await store.get(path, "missing", Comment) is None


async def test_query_filters_orders_limits(store):
    path = sub("ses_1", "comments")
    for i in range(5):
        await store.put(path, f"cm_{i:06d}", _comment(i, author="u_a" if i % 2 else "u_b"))
    res = await store.query(path, Comment, where=[("author_id", "==", "u_b")], order_by="received_at", descending=True)
    assert [c.comment_id for c in res] == ["cm_000004", "cm_000002", "cm_000000"]
    res = await store.query(path, Comment, where=[("received_at", ">", 1001)], order_by="received_at", limit=2)
    assert [c.received_at for c in res] == [1002, 1003]
    res = await store.query(path, Comment, where=[("comment_id", "in", ["cm_000001", "cm_000003"])])
    assert {c.comment_id for c in res} == {"cm_000001", "cm_000003"}


async def test_transaction_commits_only_on_success(store):
    path = sub("ses_1", "comments")
    async with store.transaction() as txn:
        assert await txn.get(path, "cm_000001", Comment) is None
        txn.put(path, "cm_000001", _comment(1))
    assert await store.get(path, "cm_000001", Comment) is not None

    with pytest.raises(RuntimeError):
        async with store.transaction() as txn:
            txn.put(path, "cm_000002", _comment(2))
            txn.delete(path, "cm_000001")
            raise RuntimeError("abort")
    assert await store.get(path, "cm_000002", Comment) is None
    assert await store.get(path, "cm_000001", Comment) is not None


async def test_delete_session_removes_subcollections(store):
    await store.put(sub("ses_1", "comments"), "cm_000001", _comment(1))
    await store.put(sub("ses_2", "comments"), "cm_000001", _comment(1))
    await store.delete_session("ses_1")
    assert await store.query(sub("ses_1", "comments"), Comment) == []
    assert len(await store.query(sub("ses_2", "comments"), Comment)) == 1
    assert SESSIONS == "sessions"


def test_unknown_collection_rejected():
    with pytest.raises(ValueError):
        sub("ses_1", "nope")
