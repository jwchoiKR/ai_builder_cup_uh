"""Two-way routing: triage says whether a person must approve the reply; the intent is only a label."""
from __future__ import annotations

import json

import pytest

from app.models.session import Message
from app.pipelines import comments as ops
from app.providers.llm import MockBackend, RawReply

from .helpers import live_runtime, make_ctx, say

SLOTS = {"person_type": None, "life_stage": None, "condition": None, "combined_with": None, "time_of_day": None}


def triage(intent: str, question: str, needs_approval, reason=None) -> dict:
    return {"kind": "question", "hide_category": None, "product_id": None, "product_basis": "context", "intent": intent,
            "condition_slots": SLOTS, "canonical_question": question, "group_candidate_id": None, "language": "en",
            "translation_en": None, "signal": None, "second_question": None, "needs_approval": needs_approval,
            "approval_reason": reason, "reason": "test"}


class Scripted(MockBackend):
    def __init__(self, fixtures_dir, script: dict[str, dict]):
        super().__init__(fixtures_dir)
        self.script = script

    async def generate(self, req, timeout_ms):
        if req.agent == "comment_triage" and req.mock_primary_text in self.script:
            return RawReply(json.dumps(self.script[req.mock_primary_text]), model_version="test")
        return await super().generate(req, timeout_ms)


async def ask(tmp_path, text: str, out: dict, show_mode: str = "team", **settings):
    ctx = make_ctx(backend=Scripted(tmp_path, {text: out}), **settings)
    rt = await live_runtime(ctx, show_mode)
    await say(rt, "Lee", text)
    [g] = await rt.groups()
    return ctx, rt, g


def close(ctx) -> None:
    ctx.runtimes.shutdown()
    ctx.scheduler.shutdown()


async def messages(rt) -> list[Message]:
    return await rt.ctx.store.query(rt.path("messages"), Message, order_by="created_at")


async def test_no_approval_needed_and_a_verified_draft_is_posted(tmp_path):
    # the intent label says a host topic; it decides nothing here
    ctx, rt, g = await ask(tmp_path, "Where is the cream made?", triage("how_to_use", "Where is it made?", False))
    try:
        assert (g.route, g.route_reason, g.status) == ("AUTO", "auto", "auto_answered")
        assert len(await messages(rt)) == 1
    finally:
        close(ctx)


async def test_approval_needed_is_the_hosts_card_and_the_operators_review(tmp_path):
    # the intent label says an auto topic; the approval call wins
    ctx, rt, g = await ask(tmp_path, "How strong is it? I flush easily",
                           triage("ingredient_amount", "How strong is it?", True, "health"))
    try:
        assert (g.route, g.route_reason, g.status) == ("HOST", "approval", "ready")
        assert (g.needs_approval, g.approval_reason) == (True, "health")
        assert await messages(rt) == [] and g.answer_id is not None  # a suggested reply, nothing posted
        assert g.group_id in [slot.group_id for slot in (await rt.load_session()).host_slots]
        await ops.approve(rt, g.group_id)
        [m] = await messages(rt)
        assert m.kind == "brand_answer"
    finally:
        close(ctx)


@pytest.mark.parametrize("reason", ["test_results", "certification", "outside"])
async def test_what_the_host_cannot_settle_on_air_goes_to_the_operator_alone(tmp_path, reason):
    ctx, rt, g = await ask(tmp_path, "Who ran the hydration test?", triage("origin", "Who ran the test?", True, reason))
    try:
        assert (g.route, g.route_reason, g.status) == ("OPERATOR", "approval", "needs_review")
        assert g.group_id not in [slot.group_id for slot in (await rt.load_session()).host_slots]
        assert await messages(rt) == []
    finally:
        close(ctx)


async def test_a_question_about_no_product_goes_to_the_operator(tmp_path):
    ctx, rt, g = await ask(tmp_path, "do you ship to Johor", triage("shipping", "Do you ship to Johor?", True, "outside"))
    try:
        assert g.product_id is None and (g.route, g.route_reason) == ("OPERATOR", "approval")
    finally:
        close(ctx)


async def test_no_approval_needed_but_no_verified_draft_goes_to_the_operator(tmp_path):
    class NoDraft(Scripted):
        async def generate(self, req, timeout_ms):
            if req.agent == "answer_composer":
                return RawReply(json.dumps({"answer": "", "citations": [], "grounded": False, "needs_human": True,
                                            "reason": "no source"}), model_version="test")
            return await super().generate(req, timeout_ms)

    text = "What is the cap made of?"
    ctx = make_ctx(backend=NoDraft(tmp_path, {text: triage("packaging", "What is the cap made of?", False)}))
    rt = await live_runtime(ctx, "team")
    try:
        await say(rt, "Lee", text)
        [g] = await rt.groups()
        assert (g.route, g.route_reason, g.status) == ("OPERATOR", "no_verified_answer", "needs_review")
        assert await messages(rt) == []
    finally:
        close(ctx)


async def test_when_triage_does_not_say_the_intent_decides(tmp_path):
    ctx, rt, g = await ask(tmp_path, "Where is the cream made?", triage("origin", "Where is it made?", None))
    try:
        assert (g.route, g.route_reason) == ("AUTO", "intent")
    finally:
        close(ctx)
