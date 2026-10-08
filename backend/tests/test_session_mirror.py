"""SESSIONS_FIRESTORE: every session is written to Firestore, memory holds only the shows being worked on."""
from __future__ import annotations

import pytest

from app.models.session import Comment, Event, QuestionGroup, Session
from app.pipelines.summary import get_summary, run_summary
from app.store.base import SESSIONS, SETUP, SUBCOLLECTIONS, sub
from app.store.memory import MemoryStore
from app.store.session_mirror import MirrorWriter, SessionMirrorStore, decode, encode, session_of

from .firestore_fake import FakeFirestore
from .helpers import live_runtime, make_ctx, say

SID = "ses_1"


def comment(cid: str, text: str = "hi") -> Comment:
    return Comment(comment_id=cid, author_id="u1", author_name="Lee", text=text, received_at=1, source="viewer")


def session(sid: str = SID) -> Session:
    return Session(session_id=sid, runsheet_id="r", title="t", status="live", created_at=1)


def mirror(fake: FakeFirestore | None = None, **kw) -> tuple[SessionMirrorStore, FakeFirestore]:
    fake = fake or FakeFirestore()
    return SessionMirrorStore(MemoryStore(), MirrorWriter("p", "live-studio", fake, flush_interval_sec=0, **kw)), fake


def close(ctx):
    ctx.runtimes.shutdown()
    ctx.scheduler.shutdown()


def test_session_documents_are_mirrored_and_nothing_else():
    assert session_of(SESSIONS, SID) == SID
    assert all(session_of(sub(SID, name)) == SID for name in SUBCOLLECTIONS)
    assert [session_of(p, "x") for p in (SETUP, "agent_calls", "sessions/a/b/c")] == [None] * 3


def test_a_document_with_an_array_in_an_array_is_stored_as_one_json_string():
    flat, nested = {"a": [1, 2], "b": [{"c": [3]}]}, {"a": [[1, 2], [3]]}
    assert encode(flat) is flat
    assert set(encode(nested)) == {"_json"} and decode(encode(nested)) == nested


async def test_writes_reach_firestore_at_their_paths_and_interim_transcripts_do_not():
    store, fake = mirror()
    await store.put(SESSIONS, SID, session())
    await store.put(sub(SID, "comments"), "cm_1", comment("cm_1", "how much?"))
    await store.put(sub(SID, "events"), "0000000001", Event(seq=1, session_id=SID, type="comment.created", at=1, payload={}))
    await store.put(sub(SID, "events"), "0000000002", Event(seq=2, session_id=SID, type="transcript.interim", at=1, payload={}))
    await store.put(SETUP, "glossary", session("not_a_session"))  # setup state is not a session's
    assert await store.flush()
    assert {(p, d) for p, d, _ in fake.ops()} == {(SESSIONS, SID), (sub(SID, "comments"), "cm_1"),
                                                  (sub(SID, "events"), "0000000001")}
    assert (await store.get(sub(SID, "events"), "0000000002", Event)) is not None  # memory has it for the live page
    await store.aclose()


async def test_a_transaction_is_one_commit_and_the_latest_write_to_a_document_wins():
    store, fake = mirror()
    async with store.transaction() as txn:
        txn.put(sub(SID, "comments"), "cm_1", comment("cm_1", "first"))
        txn.put(sub(SID, "comments"), "cm_1", comment("cm_1", "second"))
        txn.put(SESSIONS, SID, session())
    assert await store.flush()
    assert fake.docs[sub(SID, "comments")]["cm_1"]["text"] == "second" and SID in fake.docs[SESSIONS]
    assert store.status()["comments"]["commits"] == 1
    await store.aclose()


async def test_deleting_a_session_leaves_other_sessions_in_the_shared_database_alone():
    store, fake = mirror()
    fake.seed(SESSIONS, "ses_other", {"session_id": "ses_other"})
    fake.seed(sub("ses_other", "comments"), "cm_9", {"text": "someone else's"})
    await store.put(SESSIONS, SID, session())
    await store.put(sub(SID, "comments"), "cm_1", comment("cm_1"))
    await store.delete_session(SID)
    await store.delete_session("ses_other")  # never written or loaded by this process
    assert await store.flush()
    assert {(p, d) for p, docs in fake.docs.items() for d in docs} == {(SESSIONS, "ses_other"),
                                                                    (sub("ses_other", "comments"), "cm_9")}
    await store.aclose()


async def test_a_failing_commit_is_retried_and_then_counted_as_lost():
    fake = FakeFirestore()
    store, _ = mirror(fake, attempts=2, retry_base_sec=0)
    fake.fail_commits = 5
    await store.put(sub(SID, "comments"), "cm_1", comment("cm_1"))
    assert await store.flush()
    status = store.status()["comments"]
    assert status["lost_writes"] == 1 and status["retries"] == 1 and status["last_error"]
    await store.put(SESSIONS, SID, session())
    assert not await store.evict(SID)  # a lost write: the copy in memory is the only complete one, so it stays
    assert await store.get(SESSIONS, SID, Session) is not None
    await store.aclose()


def test_no_real_client_under_pytest():
    with pytest.raises(RuntimeError):
        MirrorWriter("p", "live-studio")


async def test_an_unknown_session_is_looked_up_once_and_not_again_at_once():
    store, fake = mirror()
    assert await store.get(SESSIONS, "ses_nope", Session) is None
    assert await store.get(SESSIONS, "ses_nope", Session) is None
    assert fake.reads.count(SESSIONS + "/ses_nope") <= 1 and len(fake.reads) <= 1
    await store.aclose()


async def show(tmp_path, fake, **settings):
    ctx = make_ctx(SESSIONS_FIRESTORE=True, GCP_PROJECT="p", RECORD_ANSWERS=True, firestore_client=fake, **settings)
    return ctx, await live_runtime(ctx)


async def test_a_show_in_firestore_survives_a_restart(tmp_path):
    fake = FakeFirestore()
    ctx, rt = await show(tmp_path, fake)
    sid = rt.sid
    await say(rt, "Lee", "How much is the cream?")
    assert ctx.store.name == "memory+firestore" and await ctx.store.flush()
    written = {p.split("/")[2] for p in fake.docs if p != SESSIONS}
    assert {"comments", "analyses", "groups", "answers", "messages", "events", "segments"} <= written
    last = (await ctx.bus.last_seq(sid))
    close(ctx)
    await ctx.store.aclose()

    # a new process: nothing in memory, the same database
    ctx2 = make_ctx(SESSIONS_FIRESTORE=True, GCP_PROJECT="p", RECORD_ANSWERS=True, firestore_client=fake)
    try:
        rt2 = await ctx2.runtimes.get(sid)
        s = await rt2.load_session()
        assert s.status == "live" and ctx2.store.status()["sessions_loaded"] == 1
        [g] = await rt2.groups()
        assert g.status == "auto_answered" and len(await ctx2.store.query(sub(sid, "comments"), Comment)) == 1
        assert await ctx2.bus.last_seq(sid) >= last + 10_000  # browsers skip numbers they have already seen
        await say(rt2, "Mei", "cream price?")  # the show goes on in the new process
        assert len(await rt2.groups()) == 2 and await ctx2.store.flush()
        assert len(fake.docs[sub(sid, "groups")]) == 2
    finally:
        close(ctx2)
        await ctx2.store.aclose()


async def test_an_ended_show_leaves_memory_and_comes_back_when_it_is_opened(tmp_path):
    fake = FakeFirestore()
    ctx, rt = await show(tmp_path, fake, SESSION_EVICT_AFTER_SEC=60)
    sid = rt.sid
    try:
        await say(rt, "Lee", "How much is the cream?")
        assert not await ctx.runtimes.evict(sid)  # a live show never leaves memory
        await rt.end()
        await ctx.scheduler.idle()
        if (await get_summary(rt))["status"] == "computing":
            await run_summary(rt)
        inner = ctx.store._inner
        assert inner.has_document(SESSIONS, sid)
        await ctx.scheduler.advance(61_000)  # SESSION_EVICT_AFTER_SEC after the summary
        assert not inner.has_document(SESSIONS, sid) and sub(sid, "comments") not in inner._data
        assert ctx.store.status()["sessions_evicted"] == 1 and sid in fake.docs[SESSIONS]  # Firestore keeps it

        got = await get_summary(await ctx.runtimes.get(sid))  # someone opens the summary later
        assert got["status"] in ("ready", "failed") and got["stats"]["totals"]["comments"] == 1
        assert inner.has_document(SESSIONS, sid) and ctx.store.status()["sessions_loaded"] == 1
        assert len(await ctx.store.query(sub(sid, "groups"), QuestionGroup)) == 1
    finally:
        close(ctx)
        await ctx.store.aclose()
