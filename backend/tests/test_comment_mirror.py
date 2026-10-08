"""COMMENTS_FIRESTORE: the comment path's five collections are written to Firestore, and nothing else is."""
from __future__ import annotations

import pytest

from app.models.session import Comment, Session
from app.store.base import SESSIONS, sub
from app.store.comment_mirror import COMMENT_COLLECTIONS, CommentMirrorStore, CommentWriter, session_of
from app.store.memory import MemoryStore

from .firestore_fake import FakeFirestore
from .helpers import live_runtime, make_ctx, say

SID = "ses_1"


def comment(cid: str, text: str = "hi") -> Comment:
    return Comment(comment_id=cid, author_id="u1", author_name="Lee", text=text, received_at=1, source="viewer")


def mirror(fake: FakeFirestore | None = None, **kw) -> tuple[CommentMirrorStore, FakeFirestore]:
    fake = fake or FakeFirestore()
    return CommentMirrorStore(MemoryStore(), CommentWriter("p", "live-studio", fake, flush_interval_sec=0, **kw)), fake


def test_only_the_five_comment_collections_are_mirrored():
    assert all(session_of(sub(SID, name)) == SID for name in COMMENT_COLLECTIONS)
    assert [session_of(p) for p in (SESSIONS, sub(SID, "events"), sub(SID, "transcripts"), sub(SID, "alerts"),
                                    "setup", "agent_calls")] == [None] * 6


async def test_a_comment_is_written_at_its_path_and_other_documents_are_not():
    store, fake = mirror()
    await store.put(SESSIONS, SID, Session(session_id=SID, runsheet_id="r", title="t", status="live", created_at=1))
    await store.put(sub(SID, "comments"), "cm_1", comment("cm_1", "how much?"))
    assert await store.flush()
    assert [(p, d) for p, d, _ in fake.ops()] == [(sub(SID, "comments"), "cm_1")]
    assert fake.ops()[0][2]["text"] == "how much?"
    assert (await store.get(sub(SID, "comments"), "cm_1", Comment)).text == "how much?"  # reads: the wrapped store
    assert await store.get(SESSIONS, SID, Session) is not None
    await store.aclose()


async def test_writes_to_one_document_are_coalesced_and_a_transaction_is_one_commit():
    store, fake = mirror()
    async with store.transaction() as txn:
        txn.put(sub(SID, "comments"), "cm_1", comment("cm_1", "first"))
        txn.put(sub(SID, "comments"), "cm_1", comment("cm_1", "second"))
        txn.put(sub(SID, "comments"), "cm_2", comment("cm_2"))
        txn.put(SESSIONS, SID, Session(session_id=SID, runsheet_id="r", title="t", status="live", created_at=1))
    assert await store.flush()
    assert {d: data["text"] for _, d, data in fake.ops()} == {"cm_1": "second", "cm_2": "hi"}
    assert store.status()["comments"]["commits"] == 1
    await store.aclose()


async def test_deleting_a_session_removes_only_its_comment_documents():
    store, fake = mirror()
    fake.seed(sub(SID, "events"), "0000000001", {"type": "x"})  # another writer's document in the shared database
    fake.seed(sub("ses_other", "comments"), "cm_9", {"text": "someone else's session"})
    await store.put(sub(SID, "comments"), "cm_1", comment("cm_1"))
    await store.delete_session(SID)
    await store.delete_session("ses_other")  # never written by this process: left alone
    assert await store.flush()
    left = {(p, d) for p, docs in fake.docs.items() for d in docs}
    assert left == {(sub(SID, "events"), "0000000001"), (sub("ses_other", "comments"), "cm_9")}
    await store.aclose()


async def test_a_failing_commit_is_retried_and_then_counted_as_lost():
    fake = FakeFirestore()
    store, _ = mirror(fake, attempts=2, retry_base_sec=0)
    fake.fail_commits = 5
    await store.put(sub(SID, "comments"), "cm_1", comment("cm_1"))
    assert await store.flush()
    status = store.status()["comments"]
    assert status["lost_writes"] == 1 and status["retries"] == 1 and status["last_error"]
    assert (await store.get(sub(SID, "comments"), "cm_1", Comment)) is not None  # the show's own copy is unaffected
    await store.aclose()


def test_no_real_client_under_pytest():
    with pytest.raises(RuntimeError):
        CommentWriter("p", "live-studio")


async def test_a_question_through_the_pipeline_leaves_its_documents_in_firestore(tmp_path):
    fake = FakeFirestore()
    ctx = make_ctx(COMMENTS_FIRESTORE=True, GCP_PROJECT="p", RECORD_ANSWERS=True, comments_client=fake)
    rt = await live_runtime(ctx)
    try:
        await say(rt, "Lee", "How much is the cream?")
        assert ctx.store.name == "memory+comments" and await ctx.store.flush()
        written = {p.split("/")[2] for p, _, data in fake.ops() if data is not None}
        assert written == set(COMMENT_COLLECTIONS)  # comment, analysis, group, answer, message; no event, no session
        [g] = [data for p, _, data in fake.ops() if p.endswith("/groups")]
        assert g["status"] == "auto_answered" and g["published_message_id"]
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
        await ctx.store.aclose()
