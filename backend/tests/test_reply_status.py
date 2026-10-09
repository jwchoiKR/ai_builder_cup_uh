"""Every question gets an outcome its asker can see: `Comment.reply_status` follows the question's group, and a
viewer's snapshot and event stream carry it and nothing internal."""
from __future__ import annotations

import json

import pytest

from app.bus import VIEWER_COMMENT_FIELDS, VIEWER_EVENTS, for_role
from app.logic.reply_status import waiting_status
from app.models.session import Event, QuestionGroup
from app.pipelines import comments as ops

from .helpers import live_runtime, make_ctx, say

PRICE = "How much is the cream?"
PREGNANT = "Can I use it while pregnant?"


async def show(tmp_path, show_mode: str = "solo", **settings):
    ctx = make_ctx(tmp_path, **settings)
    return ctx, await live_runtime(ctx, show_mode)


def close(ctx) -> None:
    ctx.runtimes.shutdown()
    ctx.scheduler.shutdown()


async def status(rt, comment) -> str | None:
    return (await rt.get_comment(comment.comment_id)).reply_status


async def viewer_events(rt) -> list[Event]:
    events = [for_role(e, "viewer") for e in await rt.ctx.bus.events_after(rt.sid, 0)]
    return [e for e in events if e is not None]


async def statuses_sent(rt, comment) -> list[str | None]:
    """The statuses a viewer's stream carried for one comment, in order."""
    return [e.payload["reply_status"] for e in await viewer_events(rt)
            if e.type == "comment.status" and e.payload["comment_id"] == comment.comment_id]


def group(**over) -> QuestionGroup:
    base = dict(group_id="grp_1", intent="price", condition_slots={}, canonical_question="q", member_comment_ids=[],
                unique_author_ids=[], first_at=0, last_at=0, route="AUTO", route_reason="intent", status="new")
    return QuestionGroup(**{**base, **over})


@pytest.mark.parametrize("over, want", [
    (dict(status="new"), "checking"),
    (dict(status="composing", route="HOST"), "checking"),
    (dict(status="composing", host_slot="on_host"), "checking"),
    (dict(status="ready", route="HOST"), "host"),
    (dict(status="ready", route="OPERATOR"), "team"),  # the previous product's question, moved to the operator
    (dict(status="ready", route="OPERATOR", host_slot="on_host"), "host"),  # the operator pushed it to the host
    (dict(status="needs_review", route="OPERATOR", route_reason="no_verified_answer"), "team"),
    (dict(status="needs_review", route="HOST", route_reason="unresolved_product"), "team"),
    (dict(status="needs_review", route="HOST", route_reason="unresolved_product", host_slot="on_host"), "host"),
    (dict(status="auto_answered"), "checking"),  # only members the posted reply does not address yet
    (dict(status="rejected", route="OPERATOR"), None),
    (dict(status="closed", closed_reason="ttl"), None),
])
def test_waiting_status_of_a_group(over, want):
    assert waiting_status(group(**over)) == want


async def test_auto_answered_question_is_checked_then_answered(tmp_path):
    ctx, rt = await show(tmp_path)
    try:
        lee = await say(rt, "Lee", PRICE)
        [g] = await rt.groups()
        assert g.status == "auto_answered" and await status(rt, lee) == "answered"
        assert await statuses_sent(rt, lee) == ["checking", "answered"]  # composing, then the reply was posted

        await rt.ctx.scheduler.advance(3000)
        kumar = await say(rt, "Kumar", PRICE)  # joins the posted reply
        assert await statuses_sent(rt, kumar) == ["answered"]
        await rt.ctx.scheduler.advance(11_000)
        nur = await say(rt, "Nur", PRICE)  # past the coalescing window: the reply is posted again for this asker
        assert await statuses_sent(rt, nur) == ["answered"]
        assert await statuses_sent(rt, lee) == ["checking", "answered"]  # nothing repeated for earlier askers
    finally:
        close(ctx)


async def test_record_answer_ends_answered(tmp_path):
    ctx, rt = await show(tmp_path, RECORD_ANSWERS=True)
    try:
        lee = await say(rt, "Lee", PRICE)
        sent = await statuses_sent(rt, lee)
        assert sent[-1] == "answered" and set(sent[:-1]) <= {"checking"}  # with or without a drafting step
    finally:
        close(ctx)


async def test_host_question_waits_for_the_host(tmp_path):
    ctx, rt = await show(tmp_path, "solo", SENSITIVE_APPROVAL="both")
    try:
        jun = await say(rt, "Jun", PREGNANT)
        [g] = await rt.groups()
        assert (g.route, g.status) == ("HOST", "ready") and await status(rt, jun) == "host"
        assert await statuses_sent(rt, jun) == ["checking", "host"]

        await ops.post_suggested(rt, g.group_id)
        assert await statuses_sent(rt, jun) == ["checking", "host", "answered"]
    finally:
        close(ctx)


async def test_operator_question_is_with_the_team_until_approved(tmp_path):
    ctx, rt = await show(tmp_path, "team", SENSITIVE_APPROVAL="operator")
    try:
        jun = await say(rt, "Jun", PREGNANT)
        [g] = await rt.groups()
        assert (g.route, g.status) == ("OPERATOR", "needs_review") and await status(rt, jun) == "team"
        mina = await say(rt, "Mina", PREGNANT)  # a later asker of the same waiting question
        assert len((await rt.get_group(g.group_id)).member_comment_ids) == 2 and await status(rt, mina) == "team"

        await ops.approve(rt, g.group_id)
        assert (await rt.get_group(g.group_id)).status == "answered"
        assert await statuses_sent(rt, jun) == ["checking", "team", "answered"]
        assert await statuses_sent(rt, mina) == ["team", "answered"]
    finally:
        close(ctx)


async def test_pushed_to_the_host_and_recalled(tmp_path):
    ctx, rt = await show(tmp_path, "team", SENSITIVE_APPROVAL="operator")
    try:
        jun = await say(rt, "Jun", PREGNANT)
        [g] = await rt.groups()
        await ops.push_to_host(rt, g.group_id)
        assert await status(rt, jun) == "host"
        await ops.recall_from_host(rt, g.group_id)
        assert await status(rt, jun) == "team"
    finally:
        close(ctx)


async def test_rejected_question_loses_its_status_and_a_posted_reply_keeps_it(tmp_path):
    ctx, rt = await show(tmp_path, "team", SENSITIVE_APPROVAL="operator")
    try:
        jun = await say(rt, "Jun", PREGNANT)
        [waiting] = await rt.groups()
        await ops.reject(rt, waiting.group_id)
        assert await statuses_sent(rt, jun) == ["checking", "team", None]

        lee = await say(rt, "Lee", PRICE)
        answered = next(g for g in await rt.groups() if g.group_id != waiting.group_id)
        await rt.start_promo("promo_time_sale_10")  # closes the open price group; its reply stays in chat
        assert (await rt.get_group(answered.group_id)).status == "closed"
        assert await status(rt, lee) == "answered"
    finally:
        close(ctx)


async def test_reactions_and_hidden_comments_have_no_status(tmp_path):
    ctx, rt = await show(tmp_path)
    try:
        hidden = await say(rt, "Spam", "www.deal-cosmetics.example")
        reaction = await say(rt, "Amy", "So pretty! 💜")
        assert (hidden.visibility, reaction.kind) == ("hidden", "reaction")
        assert await status(rt, hidden) is None and await status(rt, reaction) is None
        assert [e for e in await viewer_events(rt) if e.type == "comment.status"] == []
    finally:
        close(ctx)


async def test_a_status_change_reads_only_the_comments_that_change(tmp_path):
    ctx, rt = await show(tmp_path, "team", SENSITIVE_APPROVAL="operator")
    try:
        await say(rt, "Jun", PREGNANT)
        [g] = await rt.groups()
        reads: list[str] = []
        get_comment = rt.get_comment

        async def counted(cid: str):
            reads.append(cid)
            return await get_comment(cid)

        rt.get_comment = counted
        await rt.emit("group.updated", g)  # the same state again: no comment is read, nothing is sent
        assert reads == []
    finally:
        close(ctx)


INTERNAL_KEYS = {"group_id", "analysis_id", "analysis", "answer", "answer_id", "intent", "route", "route_reason",
                 "hide_category", "kind_reason", "idempotency_key", "translation_en", "armor", "host_slots",
                 "pd_card", "cue", "settings_snapshot", "prompter_points", "canonical_question", "verify_errors"}


def keys_of(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in keys_of(v)}
    if isinstance(value, list):
        return {k for v in value for k in keys_of(v)}
    return set()


async def test_viewer_gets_the_status_and_nothing_internal(tmp_path):
    ctx, rt = await show(tmp_path, "team", SENSITIVE_APPROVAL="operator")
    try:
        lee = await say(rt, "Lee", PRICE)
        jun = await say(rt, "Jun", PREGNANT)
        hidden = await say(rt, "Spam", "www.deal-cosmetics.example")
        groups = await rt.groups()
        waiting = next(g for g in groups if jun.comment_id in g.member_comment_ids)
        await ops.push_to_host(rt, waiting.group_id)  # host queue, operator action and group events
        draft = await rt.get_answer(waiting.group_id and waiting.answer_id)
        assert draft is not None and draft.text

        snap = await rt.snapshot("viewer")
        assert set(snap) == {"last_seq", "server_time", "session", "segments", "comments", "messages"}
        by_id = {c["comment_id"]: c for c in snap["comments"]}
        assert set(by_id) == {lee.comment_id, jun.comment_id} and hidden.comment_id not in by_id
        assert by_id[lee.comment_id]["reply_status"] == "answered" and by_id[jun.comment_id]["reply_status"] == "host"
        assert all(set(c) <= set(VIEWER_COMMENT_FIELDS) for c in snap["comments"])
        [reply] = snap["messages"]
        assert reply["reply_to_comment_ids"] == [lee.comment_id] and "translations" in reply

        events = await viewer_events(rt)
        assert {e.type for e in events} <= VIEWER_EVENTS and "group.updated" not in {e.type for e in events}
        sent = [e.payload["reply_status"] for e in events
                if e.type == "comment.status" and e.payload["comment_id"] == jun.comment_id]
        assert sent == ["checking", "team", "host"]
        hidden_events = [e.payload for e in events
                         if (e.payload.get("comment") or e.payload).get("comment_id") == hidden.comment_id]
        assert hidden_events and all("text" not in (p.get("comment") or p) for p in hidden_events)

        # nothing about groups, drafts or triage in anything a viewer receives
        for seen in (snap, [e.payload for e in events]):
            assert not keys_of(seen) & INTERNAL_KEYS
            text = json.dumps(seen)
            assert all(g.group_id not in text for g in groups)
            assert draft.text not in text and "sensitive" not in text and "pregnancy" not in text

        # the operator still gets all of it
        op = await rt.snapshot("operator")
        assert {g["group_id"] for g in op["groups"]} == {g.group_id for g in groups}
        assert {c["comment_id"] for c in op["comments"]} == {lee.comment_id, jun.comment_id, hidden.comment_id}
        assert next(c for c in op["comments"] if c["comment_id"] == jun.comment_id)["reply_status"] == "host"
        host = await rt.snapshot("host")
        assert host["groups"] and "prompter" in host
    finally:
        close(ctx)


async def test_viewer_stream_drops_internal_events_and_unpublished_posts():
    def ev(type_: str, payload: dict) -> Event:
        return Event(seq=1, session_id="s", type=type_, at=1, payload=payload)

    for internal in ("group.updated", "hostqueue.updated", "pd.card", "cue.updated", "alert.created",
                     "transcript.final", "operator.action", "agent.call", "metrics.updated", "prompter.updated",
                     "message.pending", "message.cancelled", "an.event.added.later"):
        assert for_role(ev(internal, {"group_id": "grp_1"}), "viewer") is None
    message = {"message_id": "msg_1", "kind": "host_answer", "text": "Yes.", "group_id": "grp_1",
               "reply_to_comment_ids": ["cm_1"], "reply_to_author_names": ["Jun"], "citations": [], "created_at": 1,
               "publish_at": 5, "published_at": None, "idempotency_key": "host_answer:grp_1",
               "translations": {"ko": "네."}}
    assert for_role(ev("message.updated", {**message, "state": "pending"}), "viewer") is None
    out = for_role(ev("message.published", {**message, "state": "published"}), "viewer")
    assert out.payload["translations"] == {"ko": "네."} and not set(out.payload) & {"group_id", "idempotency_key"}
    comment = {"comment_id": "cm_1", "author_id": "u_1", "author_name": "Jun", "text": "임산부도 써도 되나요?",
               "received_at": 1, "source": "viewer", "visibility": "visible", "hide_category": None,
               "kind": "question", "analysis_id": "an_1", "group_id": "grp_1", "armor": None, "language": "ko",
               "translation_en": "Can pregnant women use it?", "reply_status": "team"}
    analyzed = ev("comment.analyzed", {"comment": comment, "analysis": {"route": "OPERATOR"}})
    assert for_role(analyzed, "viewer").payload == {"comment": {
        "comment_id": "cm_1", "author_id": "u_1", "author_name": "Jun", "text": "임산부도 써도 되나요?", "received_at": 1,
        "visibility": "visible", "language": "ko", "reply_status": "team"}}
    assert for_role(analyzed, "operator").payload["comment"]["translation_en"] == "Can pregnant women use it?"
    assert for_role(analyzed, "host").payload == {"comment": comment}  # the host stream is as before
    session = for_role(ev("session.started", {"session_id": "s", "status": "live", "pinned_notice": None,
                                              "host_slots": [{"group_id": "grp_1"}],
                                              "pd_card": {"ref_id": "grp_1", "say": "draft"}}), "viewer")
    assert session.payload == {"session_id": "s", "status": "live", "pinned_notice": None}
