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


INTERNAL_KEYS = {"group_id", "analysis_id", "analysis", "answer", "answer_id", "intent", "route", "route_reason",
                 "hide_category", "kind_reason", "idempotency_key", "translation_en", "armor", "host_slots",
                 "pd_card", "cue", "settings_snapshot", "prompter_points", "canonical_question", "verify_errors"}


def keys_of(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in keys_of(v)}
    if isinstance(value, list):
        return {k for v in value for k in keys_of(v)}
    return set()


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
        "visibility": "visible", "language": "ko", "reply_status": "team", "kind": "question"}}  # D-482: kind
    assert for_role(analyzed, "operator").payload["comment"]["translation_en"] == "Can pregnant women use it?"
    assert for_role(analyzed, "host").payload == {"comment": comment}  # the host stream is as before
    session = for_role(ev("session.started", {"session_id": "s", "status": "live", "pinned_notice": None,
                                              "host_slots": [{"group_id": "grp_1"}],
                                              "pd_card": {"ref_id": "grp_1", "say": "draft"}}), "viewer")
    assert session.payload == {"session_id": "s", "status": "live", "pinned_notice": None}
