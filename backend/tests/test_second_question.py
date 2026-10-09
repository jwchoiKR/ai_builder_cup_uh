"""A comment that asks two different things gets each part handled as a question."""
from __future__ import annotations

import json

from app.models.session import Message
from app.providers.llm import MockBackend, RawReply

from .helpers import live_runtime, make_ctx, say

SLOTS = {"person_type": None, "life_stage": None, "condition": None, "combined_with": None, "time_of_day": None}


def triage(intent: str, question: str, second: str | None = None, kind: str = "question") -> dict:
    return {"kind": kind, "hide_category": None, "product_id": None, "product_basis": "context", "intent": intent,
            "condition_slots": SLOTS, "canonical_question": question, "group_candidate_id": None, "language": "en",
            "translation_en": None, "signal": None, "second_question": second, "reason": "test"}


class Scripted(MockBackend):
    """Triage answers from a script keyed by the text it is given; everything else from the mock."""

    def __init__(self, fixtures_dir, script: dict[str, dict]):
        super().__init__(fixtures_dir)
        self.script, self.texts = script, []

    async def generate(self, req, timeout_ms):
        if req.agent == "comment_triage" and req.mock_primary_text in self.script:
            self.texts.append(req.mock_primary_text)
            return RawReply(json.dumps(self.script[req.mock_primary_text]), model_version="test")
        return await super().generate(req, timeout_ms)


BOTH = "is the cream made in korea? and how much is it"


async def run(tmp_path, script, **settings):
    backend = Scripted(tmp_path, script)
    ctx = make_ctx(backend=backend, **({"RECORD_ANSWERS": True} | settings))
    rt = await live_runtime(ctx)
    c = await say(rt, "Lee", BOTH)
    return ctx, rt, backend, c


def close(ctx) -> None:
    ctx.runtimes.shutdown()
    ctx.scheduler.shutdown()


async def test_both_questions_get_their_own_group_and_reply(tmp_path):
    ctx, rt, backend, c = await run(tmp_path, {
        BOTH: triage("origin", "Where is it made?", second="How much is the cream?"),
        "How much is the cream?": triage("price", "How much is it?", second="And another one?"),
    })
    try:
        groups = {g.intent: g for g in await rt.groups()}
        assert set(groups) == {"origin", "price"}
        assert all(g.member_comment_ids == [c.comment_id] and g.status == "auto_answered" for g in groups.values())
        replies = await rt.ctx.store.query(rt.path("messages"), Message, order_by="created_at")
        assert len(replies) == 2 and all(m.reply_to_comment_ids == [c.comment_id] for m in replies)
        assert sum("S$36.00" in m.text for m in replies) == 1  # the price reply, and one other
        saved = await rt.get_comment(c.comment_id)
        assert saved.group_id == groups["origin"].group_id  # the comment stays with its first question
        assert backend.texts == [BOTH, "How much is the cream?"] and rt.counters["second_questions"] == 1  # no third
    finally:
        close(ctx)


async def test_a_second_part_that_is_the_same_question_is_dropped(tmp_path):
    ctx, rt, _, c = await run(tmp_path, {
        BOTH: triage("price", "How much is it?", second="What does the cream cost?"),
        "What does the cream cost?": triage("price", "What does it cost?"),
    })
    try:
        [g] = await rt.groups()
        assert g.intent == "price" and rt.counters.get("second_questions", 0) == 0
    finally:
        close(ctx)


async def test_a_second_part_that_is_no_question_is_dropped(tmp_path):
    ctx, rt, _, c = await run(tmp_path, {
        BOTH: triage("origin", "Where is it made?", second="Nice colour"),
        "Nice colour": triage(None, "", kind="reaction"),
    })
    try:
        assert [g.intent for g in await rt.groups()] == ["origin"]
    finally:
        close(ctx)


async def test_the_plain_part_waits_when_the_other_part_needs_a_person(tmp_path):
    """Two-way routing: "how many drops, and ok while pregnant?": the drops are not answered ahead of the health
    part; both wait for a person, each with its suggested reply."""
    health = triage("pregnancy_breastfeeding", "Can it be used while pregnant?", second="How much is the cream?")
    health |= {"needs_approval": True, "approval_reason": "health"}
    plain = triage("price", "How much is it?") | {"needs_approval": False, "approval_reason": None}
    ctx, rt, backend, c = await run(tmp_path, {BOTH: health, "How much is the cream?": plain})
    try:
        groups = {g.intent: g for g in await rt.groups()}
        assert set(groups) == {"pregnancy_breastfeeding", "price"}
        assert all(g.route_reason == "approval" and g.needs_approval for g in groups.values())
        assert groups["price"].answer_id is not None  # the suggested reply is there
        assert await rt.ctx.store.query(rt.path("messages"), Message) == []  # nothing posted by itself
    finally:
        close(ctx)
