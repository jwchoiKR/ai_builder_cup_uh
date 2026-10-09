"""SENSITIVE_APPROVAL: a sensitive question goes to the host, to the operator, or to both at once."""
from __future__ import annotations

import pytest

from app.models.session import Message
from app.pipelines import comments as ops

from .helpers import live_runtime, make_ctx, say


async def show(tmp_path, show_mode: str, mode: str = "operator", **settings):
    ctx = make_ctx(tmp_path, SENSITIVE_APPROVAL=mode, **settings)
    return ctx, await live_runtime(ctx, show_mode)


def close(ctx) -> None:
    ctx.runtimes.shutdown()
    ctx.scheduler.shutdown()


async def messages(rt) -> list[Message]:
    return await rt.ctx.store.query(rt.path("messages"), Message, order_by="created_at")


async def test_team_show_sensitive_question_waits_for_the_operator(tmp_path):
    ctx, rt = await show(tmp_path, "team")
    try:
        await say(rt, "Jun", "Can I use it while pregnant?")
        [g] = await rt.groups()
        assert (g.route, g.route_reason, g.status) == ("OPERATOR", "sensitive", "needs_review")
        draft = await rt.get_answer(g.answer_id)
        assert draft is not None and draft.verified  # the suggested reply the operator sees
        assert await messages(rt) == []
        assert g.group_id not in [slot.group_id for slot in (await rt.load_session()).host_slots]  # no host card

        await ops.approve(rt, g.group_id)
        [m] = await messages(rt)
        assert m.kind == "brand_answer" and m.text == draft.text
        assert (await rt.get_group(g.group_id)).status == "answered"
    finally:
        close(ctx)


async def test_team_show_operator_can_edit_the_suggested_reply(tmp_path):
    ctx, rt = await show(tmp_path, "team")
    try:
        await say(rt, "Jun", "Can I use it while pregnant?")
        [g] = await rt.groups()
        await ops.write_answer(rt, g.group_id, "Please check with your doctor before use.", "operator_written", False)
        [m] = await messages(rt)
        assert m.kind == "brand_answer" and m.text == "Please check with your doctor before use."
    finally:
        close(ctx)


async def test_solo_show_keeps_the_question_with_the_host(tmp_path):
    ctx, rt = await show(tmp_path, "solo")
    try:
        await say(rt, "Jun", "Can I use it while pregnant?")
        [g] = await rt.groups()
        assert (g.route, g.route_reason, g.status) == ("HOST", "sensitive", "ready")
    finally:
        close(ctx)


async def test_switched_off_a_team_show_routes_to_the_host_as_before(tmp_path):
    ctx = make_ctx(tmp_path, SENSITIVE_APPROVAL="host")
    rt = await live_runtime(ctx, "team")
    try:
        await say(rt, "Jun", "Can I use it while pregnant?")
        [g] = await rt.groups()
        assert (g.route, g.route_reason) == ("HOST", "sensitive")
    finally:
        close(ctx)


@pytest.mark.parametrize("text,intent", [("How much is the cream?", "price")])
async def test_team_show_easy_questions_are_still_posted_at_once(tmp_path, text, intent):
    ctx, rt = await show(tmp_path, "team", RECORD_ANSWERS=True)
    try:
        await say(rt, "Lee", text)
        [g] = await rt.groups()
        assert (g.intent, g.route, g.status) == (intent, "AUTO", "auto_answered")
    finally:
        close(ctx)


async def test_both_the_host_card_and_the_operator_approval(tmp_path):
    """The default: the question is the host's card with its suggested reply, and the operator can approve the same
    reply from the desk; the first of the two posts it, once."""
    ctx, rt = await show(tmp_path, "team", "both")
    try:
        await say(rt, "Jun", "Can I use it while pregnant?")
        [g] = await rt.groups()
        assert (g.route, g.route_reason, g.status) == ("HOST", "sensitive", "ready")
        draft = await rt.get_answer(g.answer_id)
        assert draft is not None and draft.verified
        assert g.group_id in [slot.group_id for slot in (await rt.load_session()).host_slots]  # the host's card
        assert await messages(rt) == []  # nothing is posted by itself

        await ops.approve(rt, g.group_id)  # the operator approves before the host says it
        [m] = await messages(rt)
        assert m.kind == "brand_answer" and m.text == draft.text
        g = await rt.get_group(g.group_id)
        assert g.status == "answered"
        assert g.group_id not in [slot.group_id for slot in (await rt.load_session()).host_slots]  # the card is gone
        with pytest.raises(ops.ActionError):
            await ops.approve(rt, g.group_id)  # never twice
        assert len(await messages(rt)) == 1
    finally:
        close(ctx)


def test_both_is_the_shipped_default():
    from app.config import Settings

    assert Settings.model_fields["SENSITIVE_APPROVAL"].default == "both"
