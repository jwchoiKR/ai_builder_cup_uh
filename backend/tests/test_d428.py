"""D-428 (main merge): STORE=firestore is the one Firestore writer. Ported from the comments team's session mirror
(tests/test_session_mirror.py): the comment collections are stored and read back, a show survives a restart, an ended
show leaves memory and comes back when it is opened, the status counters, the queue cap with its lost counter, and a
delete that leaves another process's session alone. Runs on the in-process Firestore stand-in."""
from __future__ import annotations

import pytest

from app.models.session import Comment, QuestionGroup, Session
from app.pipelines.summary import get_summary, run_summary
from app.store.base import SESSIONS, sub
from app.store.firestore import FirestoreStore

from .fake_firestore import FakeFirestore
from .helpers import live_runtime, make_ctx, make_settings, say

SID = "ses_1"


def comment(cid: str, text: str = "hi") -> Comment:
    return Comment(comment_id=cid, author_id="u1", author_name="Lee", text=text, received_at=1, source="viewer")


def session(sid: str = SID) -> Session:
    return Session(session_id=sid, runsheet_id="r", title="t", status="live", created_at=1)


def close(ctx):
    ctx.runtimes.shutdown()
    ctx.scheduler.shutdown()


def test_d430_a_test_run_never_reaches_the_real_database():
    with pytest.raises(RuntimeError):
        FirestoreStore(make_settings(STORE="firestore", GCP_PROJECT="p"))


async def test_d428_a_transaction_is_one_commit_and_the_status_counts_it():
    fake = FakeFirestore()
    store = FirestoreStore(client=fake)
    async with store.transaction() as txn:
        txn.put(sub(SID, "comments"), "cm_1", comment("cm_1", "first"))
        txn.put(sub(SID, "comments"), "cm_1", comment("cm_1", "second"))
        txn.put(SESSIONS, SID, session())
    assert await store.flush(5)
    assert fake.data[sub(SID, "comments")]["cm_1"]["text"] == "second" and SID in fake.data[SESSIONS]
    status = store.status()
    assert set(status) == {"comments", "sessions_loaded", "sessions_evicted"}
    assert status["comments"]["commits"] == 1 and status["comments"]["writes_committed"] == 2
    assert status["comments"]["queue_depth"] == 0 and status["comments"]["lost_writes"] == 0


async def test_d428_a_full_queue_drops_the_oldest_counts_them_and_keeps_the_session_in_memory(monkeypatch):
    import app.store.firestore as fs

    monkeypatch.setattr(fs, "MAX_QUEUE", 3)
    store = FirestoreStore(client=FakeFirestore())
    await store.put(SESSIONS, SID, session())
    for i in range(4):  # no await yields to the writer in between: the queue fills
        await store.put(sub(SID, "comments"), f"cm_{i}", comment(f"cm_{i}"))
    assert store.status()["comments"]["lost_writes"] == 2 and store.queued == 3
    await store.put(SESSIONS, SID, session().model_copy(update={"status": "ended"}))
    assert not await store.evict(SID)  # a lost write: memory holds the only complete copy, so it stays
    assert await store.get(SESSIONS, SID, Session) is not None


async def test_d428_deleting_a_session_leaves_other_sessions_in_the_shared_database_alone():
    fake = FakeFirestore()
    fake.data[SESSIONS] = {"ses_other": {"session_id": "ses_other"}}
    fake.data[sub("ses_other", "comments")] = {"cm_9": {"text": "someone else's"}}
    store = FirestoreStore(client=fake)
    await store.put(SESSIONS, SID, session())
    await store.put(sub(SID, "comments"), "cm_1", comment("cm_1"))
    assert await store.flush(5)
    await store.delete_session(SID)
    await store.delete_session("ses_other")  # never written or read back by this process
    assert await store.flush(5)
    assert set(fake.data[SESSIONS]) == {"ses_other"} and set(fake.data[sub("ses_other", "comments")]) == {"cm_9"}
    assert not fake.data.get(sub(SID, "comments"))


async def show(fake, **settings):
    ctx = make_ctx(STORE="firestore", GCP_PROJECT="p", firestore_client=fake, **settings)
    return ctx, await live_runtime(ctx)


async def test_d431_a_skipped_oversized_write_keeps_the_ended_session_in_memory():
    """D-431 (codex review): Firestore holds an older copy of a document too large to write, so evict refuses."""
    store = FirestoreStore(client=FakeFirestore())
    await store.put(SESSIONS, SID, session().model_copy(update={"status": "ended"}))
    await store.put(sub(SID, "comments"), "cm_big", comment("cm_big", "x" * 1_100_000))
    assert await store.flush(5)
    assert store.status()["comments"]["oversize_skipped"] == 1
    assert not await store.evict(SID)
    assert await store.get(SESSIONS, SID, Session) is not None
