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


def test_d430_sessions_firestore_true_runs_as_store_firestore_with_one_warning(caplog):
    """D-430 (user): the old switch never stops the server; there is still one writer."""
    import logging

    with caplog.at_level(logging.WARNING):
        on = make_settings(SESSIONS_FIRESTORE=True, STORE="memory", GCP_PROJECT="p")
    assert on.STORE == "firestore"
    assert [r.getMessage() for r in caplog.records if "SESSIONS_FIRESTORE" in r.getMessage()] == [
        "SESSIONS_FIRESTORE is merged into STORE=firestore (D-428); using STORE=firestore"]
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        off = make_settings(SESSIONS_FIRESTORE=False, STORE="memory")
    assert off.STORE == "memory" and not caplog.records
    with pytest.raises(RuntimeError):  # and a test run never reaches the real database
        FirestoreStore(make_settings(STORE="firestore", GCP_PROJECT="p"))


async def test_d430_a_session_the_comments_mirror_wrote_loads_back_through_our_store():
    """D-430: a show as the comments team's session mirror (origin/main 6dc6698) wrote it: every session document
    and subcollection document as model_dump(mode="json"), a nested array as one "_json" string, no
    transcript.interim events and no seq mark on the session document. Our store reads it back whole, and the next
    event seq starts a block past the highest stored one."""
    import json

    from app.store.base import SUBCOLLECTIONS
    from app.store.firestore import HW_BLOCK

    def mirror_encode(data: dict) -> dict:  # the mirror's encode, as it was
        def nested(x, in_array=False):
            if isinstance(x, list):
                return in_array or any(nested(v, True) for v in x)
            if isinstance(x, dict):
                return any(nested(v, False) for v in x.values())
            return False
        return {"_json": json.dumps(data, ensure_ascii=False)} if nested(data) else data

    ctx = make_ctx(RECORD_ANSWERS=True)  # memory: the show the mirror copied
    rt = await live_runtime(ctx)
    try:
        sid = rt.sid
        await say(rt, "Lee", "How much is the cream?")
        await ctx.bus.emit(sid, "x.pairs", {"pairs": [["S1", "a"], ["S2", "b"]]})  # an array in an array
        mem = ctx.store._data
        fake = FakeFirestore()
        paths = [SESSIONS, *(sub(sid, n) for n in SUBCOLLECTIONS)]
        for path in paths:
            for doc_id, data in mem.get(path, {}).items():
                if path == SESSIONS and doc_id != sid:
                    continue
                if path.endswith("/events") and data.get("type") == "transcript.interim":
                    continue  # the mirror kept these in memory only
                fake.data.setdefault(path, {})[doc_id] = mirror_encode(json.loads(json.dumps(data)))
        written = {p.split("/")[2] for p in fake.data if p != SESSIONS}
        assert {"comments", "analyses", "groups", "answers", "messages", "events", "agent_calls"} <= written
        assert any("_json" in d for d in fake.data[sub(sid, "events")].values())
        last = max(e["seq"] for e in mem[sub(sid, "events")].values())
    finally:
        close(ctx)

    store = FirestoreStore(client=fake)
    assert (await store.get(SESSIONS, sid, Session)).session_id == sid  # reads the whole session back
    for path in paths[1:]:
        if path in fake.data:
            assert set(store._data.get(path, {})) == set(fake.data[path]), path
            for doc_id, data in store._data[path].items():
                stored = fake.data[path][doc_id]
                assert data == (json.loads(stored["_json"]) if "_json" in stored else stored), (path, doc_id)
    [c] = await store.query(sub(sid, "comments"), Comment)
    assert c.text == "How much is the cream?" and len(await store.query(sub(sid, "groups"), QuestionGroup)) == 1
    from app.bus import EventBus
    from app.clock import ManualClock

    bus = EventBus(store, ManualClock())
    assert await bus.last_seq(sid) == last + HW_BLOCK  # no seq a browser may have seen is used again


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
    ctx = make_ctx(STORE="firestore", GCP_PROJECT="p", RECORD_ANSWERS=True, firestore_client=fake, **settings)
    return ctx, await live_runtime(ctx)


async def test_d428_a_show_in_firestore_survives_a_restart():
    fake = FakeFirestore()
    ctx, rt = await show(fake)
    sid = rt.sid
    await say(rt, "Lee", "How much is the cream?")
    assert ctx.store.name == "firestore" and await ctx.store.flush(5)
    written = {p.split("/")[2] for p in fake.data if p != SESSIONS}
    assert {"comments", "analyses", "groups", "answers", "messages", "events", "segments"} <= written
    last = await ctx.bus.last_seq(sid)
    close(ctx)
    await ctx.store.aclose()

    # a new process: nothing in memory, the same database
    ctx2 = make_ctx(STORE="firestore", GCP_PROJECT="p", RECORD_ANSWERS=True, firestore_client=fake)
    try:
        rt2 = await ctx2.runtimes.get(sid)
        s = await rt2.load_session()
        assert s.status == "live" and ctx2.store.status()["sessions_loaded"] == 1
        [g] = await rt2.groups()
        assert g.status == "auto_answered" and len(await ctx2.store.query(sub(sid, "comments"), Comment)) == 1
        assert await ctx2.bus.last_seq(sid) > last  # D-381: past the reserved ceiling, never a seq a browser saw
        await say(rt2, "Mei", "cream price?")  # the show goes on in the new process
        assert len(await rt2.groups()) == 2 and await ctx2.store.flush(5)
        assert len(fake.data[sub(sid, "groups")]) == 2
    finally:
        close(ctx2)
        await ctx2.store.aclose()


async def test_d428_an_ended_show_leaves_memory_and_comes_back_when_it_is_opened():
    fake = FakeFirestore()
    ctx, rt = await show(fake, SESSION_EVICT_AFTER_SEC=60)
    sid = rt.sid
    store = ctx.store
    try:
        await say(rt, "Lee", "How much is the cream?")
        assert not await ctx.runtimes.evict(sid)  # a live show never leaves memory
        await rt.end()
        await ctx.scheduler.idle()
        if (await get_summary(rt))["status"] == "computing":
            await run_summary(rt)
        assert sid in store._data[SESSIONS]
        await ctx.scheduler.advance(61_000)  # SESSION_EVICT_AFTER_SEC after the summary
        assert sid not in store._data.get(SESSIONS, {}) and sub(sid, "comments") not in store._data
        assert store.status()["sessions_evicted"] == 1 and sid in fake.data[SESSIONS]  # Firestore keeps it

        got = await get_summary(await ctx.runtimes.get(sid))  # someone opens the summary later
        assert got["status"] in ("ready", "failed") and got["stats"]["totals"]["comments"] == 1
        assert sid in store._data[SESSIONS] and store.status()["sessions_loaded"] == 1
        assert len(await store.query(sub(sid, "groups"), QuestionGroup)) == 1
    finally:
        close(ctx)
        await store.aclose()
