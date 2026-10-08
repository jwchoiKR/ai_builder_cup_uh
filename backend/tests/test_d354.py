"""D-354 STORE=firestore: memory is the read model and every write is mirrored to Firestore behind it (ordered,
coalesced, batches of at most 500). Runs on an in-process stand-in of the Firestore client; with
FIRESTORE_EMULATOR_HOST set, the store contract also runs on the Firestore emulator."""
from __future__ import annotations

import os

import pytest

from app.bus import EventBus
from app.models.session import Comment, Event, Session
from app.store.base import SESSIONS, sub
from app.store.firestore import JSON_FIELD, FirestoreStore

from . import test_store
from .fake_firestore import FakeFirestore


def _store(client=None) -> tuple[FirestoreStore, FakeFirestore]:
    client = client or FakeFirestore()
    return FirestoreStore(client=client), client


def _comment(i: int) -> Comment:
    return Comment(comment_id=f"cm_{i:06d}", author_id="u_a", author_name="A", text=f"c{i}", received_at=1000 + i,
                   source="script")


@pytest.mark.parametrize("case", [test_store.test_put_get_returns_copies, test_store.test_query_filters_orders_limits,
                                  test_store.test_transaction_commits_only_on_success,
                                  test_store.test_delete_session_removes_subcollections])
async def test_d354_the_store_contract_holds(case):
    store, client = _store()
    await case(store)
    assert await store.flush(5)
    # what Firestore holds equals what memory holds
    for path, docs in store._data.items():
        assert {k: v for k, v in client.data.get(path, {}).items()} == docs, path


async def test_d354_writes_do_not_wait_and_are_coalesced_and_batched():
    store, client = _store()
    path = sub("ses_1", "comments")
    await store.put(SESSIONS, "ses_1", _comment(0))  # any model: the session read-back has happened once
    reads = client.reads
    for i in range(1200):
        await store.put(path, f"cm_{i:06d}", _comment(i))
    for _ in range(3):  # three writes of one document are one write
        await store.put(path, "cm_000007", _comment(99))
    assert client.reads == reads  # no network read on the write path after the first touch
    assert await store.flush(5)
    assert client.count(path) == 1200 and client.data[path]["cm_000007"]["text"] == "c99"
    assert max(client.commits) <= 500


async def test_d354_an_outage_is_retried_and_nothing_is_lost(caplog):
    store, client = _store()
    client.fail_next_commits = 2
    await store.put(sub("ses_1", "comments"), "cm_000001", _comment(1))
    assert await store.flush(10)
    assert client.count(sub("ses_1", "comments")) == 1 and store.failures == 2
    assert "write failed" in caplog.text


async def test_d354_a_refused_document_is_logged_and_does_not_block_the_others(caplog):
    store, client = _store()
    client.refuse_ids = {"cm_000002"}
    path = sub("ses_1", "comments")
    for i in (1, 2, 3):
        await store.put(path, f"cm_{i:06d}", _comment(i))
    assert await store.flush(5)
    # refused as fields, then written as one JSON string field
    assert set(client.data[path]) == {"cm_000001", "cm_000002", "cm_000003"}
    assert JSON_FIELD in client.data[path]["cm_000002"]


async def test_d354_nested_arrays_are_written_as_json_and_read_back():
    store, client = _store()
    ev = Event(seq=1, session_id="ses_1", type="x", at=1, payload={"pairs": [["S1", "a"], ["S2", "b"]]})
    await store.put(SESSIONS, "ses_1", _comment(0))  # a session is read back from its document
    await store.put(sub("ses_1", "events"), "0000000001", ev)
    assert await store.flush(5)
    assert JSON_FIELD in client.data[sub("ses_1", "events")]["0000000001"]
    fresh, _ = _store(client)
    got = await fresh.get(sub("ses_1", "events"), "0000000001", Event)
    assert got.payload["pairs"] == [["S1", "a"], ["S2", "b"]]


async def test_d354_a_doc_id_with_a_slash_is_refused():
    store, _ = _store()
    with pytest.raises(ValueError):
        await store.put(sub("ses_1", "comments"), "a/b", _comment(1))


async def test_d354_a_too_large_document_is_logged_not_written(caplog):
    store, client = _store()
    big = Comment(comment_id="cm_big", author_id="u", author_name="A", text="x" * 1_100_000, received_at=1,
                  source="script")
    await store.put(sub("ses_1", "comments"), "cm_big", big)
    await store.put(sub("ses_1", "comments"), "cm_000001", _comment(1))
    assert await store.flush(5)
    assert "over the 1 MiB document limit" in caplog.text and store.failures == 1
    assert set(client.data[sub("ses_1", "comments")]) == {"cm_000001"}


async def test_d354_a_replayed_show_matches_memory_and_a_new_process_continues_it(monkeypatch):
    """A show through the real pipeline: Firestore's documents equal memory's, per collection; a new process (a
    new store on the same database) reads the session back and continues its event seq."""
    import app.store.firestore as fs

    from .helpers import live_runtime, make_ctx
    from .judge_fakes import ScriptedBackend, speak, violation

    client = FakeFirestore()
    monkeypatch.setattr(fs, "_make_client", lambda settings: client)
    llm = ScriptedBackend()
    llm.judge("It cures eczema, honestly.", violations=[violation("ASEAN-2D-DISEASE", "cures eczema")])
    ctx = make_ctx(backend=llm, STORE="firestore", GCP_PROJECT="demo-test")
    rt = await live_runtime(ctx)
    try:
        for line in ("Welcome everyone to the show.", "It cures eczema, honestly.", "Sorry, scratch that."):
            await speak(rt, line)
        await rt.utterances.drain()
        await rt.end()
        sid = rt.sid
        assert await ctx.store.flush(10)
        mem = ctx.store._data
        for path in [p for p in mem if p == SESSIONS or p.startswith(f"{SESSIONS}/{sid}/")]:
            assert set(client.data.get(path, {})) == set(mem[path]), path
        last = (await ctx.bus.events_after(sid, 0))[-1].seq
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()

    fresh = FirestoreStore(client=client)  # a new instance after a restart
    assert (await fresh.get(SESSIONS, sid, Session)).status == "ended"
    bus = EventBus(fresh, ctx.clock)
    assert await bus.last_seq(sid) == last
    ev = await bus.emit(sid, "summary.ready", {"ok": True})
    assert ev.seq == last + 1


async def test_d354_delete_session_deletes_it_in_firestore_too():
    store, client = _store()
    await store.put(SESSIONS, "ses_1", _comment(0))
    await store.put(sub("ses_1", "comments"), "cm_000001", _comment(1))
    assert await store.flush(5)
    await store.delete_session("ses_1")
    assert await store.flush(5)
    assert not client.data.get(SESSIONS) and not client.data.get(sub("ses_1", "comments"))


@pytest.mark.skipif(not os.environ.get("FIRESTORE_EMULATOR_HOST"), reason="needs the Firestore emulator")
@pytest.mark.parametrize("case", [test_store.test_put_get_returns_copies, test_store.test_query_filters_orders_limits,
                                  test_store.test_transaction_commits_only_on_success,
                                  test_store.test_delete_session_removes_subcollections])
async def test_d354_the_store_contract_on_the_emulator(case):
    from google.cloud import firestore

    client = firestore.AsyncClient(project="demo-live-studio", database="live-studio")
    store = FirestoreStore(client=client)
    await case(store)
    assert await store.flush(30)
    fresh = FirestoreStore(client=client)  # read back from the emulator
    for path, docs in store._data.items():
        if path.startswith(f"{SESSIONS}/"):
            sid = path.split("/")[1]
            got = await fresh.query(path, Comment)
            assert {c.comment_id for c in got} == set(docs), (sid, path)
