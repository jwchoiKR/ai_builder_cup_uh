"""Comment path end to end inside one process (mock LLM with rule-based fallbacks)."""
from __future__ import annotations

import pytest

from app.models.session import Comment, Message, QuestionGroup
from app.pipelines import comments as ops
from app.pipelines.runtime import ActionError, RateLimited
from app.providers.llm import LLMError

from .helpers import live_runtime, make_ctx, say

CREAM = "cream_hydra_barrier"


@pytest.fixture
async def rt(tmp_path):
    ctx = make_ctx(tmp_path)  # empty fixture dir: agents use their rule-based fallbacks
    runtime = await live_runtime(ctx)
    yield runtime
    ctx.runtimes.shutdown()
    ctx.scheduler.shutdown()


async def groups(rt) -> list[QuestionGroup]:
    return await rt.groups()


async def messages(rt) -> list[Message]:
    return await rt.ctx.store.query(rt.path("messages"), Message, order_by="created_at")


async def test_prefilter_hides_and_reactions_skip_llm(rt):
    hidden = await say(rt, "Spam", "Cheap creams here >>> www.deal-cosmetics.example")
    reaction = await say(rt, "Amy", "So pretty! 💜")
    assert hidden.visibility == "hidden" and hidden.hide_category == "link"
    assert reaction.kind == "reaction"
    calls = await rt.ctx.store.query(rt.path("agent_calls"), __import__("app.models.session", fromlist=["AgentCall"]).AgentCall)
    assert calls == []
    state_viewer = await rt.snapshot("viewer")
    assert [c["comment_id"] for c in state_viewer["comments"]] == [reaction.comment_id]
    state_op = await rt.snapshot("operator")
    assert {c["comment_id"] for c in state_op["comments"]} == {hidden.comment_id, reaction.comment_id}


async def test_auto_answer_coalescing_and_unique_askers(rt):
    await say(rt, "Lee", "How much is the cream?")
    [g] = await groups(rt)
    assert g.intent == "price" and g.route == "AUTO" and g.status == "auto_answered"
    [m] = await messages(rt)
    assert m.kind == "ai_answer" and m.reply_to_author_names == ["Lee"]
    assert rt.counters["composed_answers"] == 1

    await rt.ctx.scheduler.advance(3000)
    await say(rt, "Kumar", "How much is the cream?")
    await say(rt, "Lee", "How much is the cream?")  # same author again
    [g] = await groups(rt)
    assert len(g.member_comment_ids) == 3 and g.unique_author_ids == ["u_lee", "u_kumar"]
    [m] = await messages(rt)  # coalesced into the same reply (within REPLY_COALESCE_SEC)
    assert m.reply_to_author_names == ["Lee", "Kumar"] and len(m.reply_to_comment_ids) == 3
    assert rt.counters["instant_answers"] == 2

    await rt.ctx.scheduler.advance(11_000)
    await say(rt, "Nur", "How much is the cream?")
    msgs = await messages(rt)
    assert len(msgs) == 2 and msgs[1].text == msgs[0].text and msgs[1].reply_to_author_names == ["Nur"]
    agent_names = [c.agent for c in await rt.ctx.store.query(rt.path("agent_calls"),
                   __import__("app.models.session", fromlist=["AgentCall"]).AgentCall)]
    assert agent_names.count("answer_composer") == 1  # later askers answered without a composer call
    assert agent_names.count("comment_triage") == 1  # same text: triage cache


async def test_key_level_cache_after_group_closes(rt):
    await say(rt, "Lee", "How much is the cream?")
    [g] = await groups(rt)
    g.status = "closed"
    await rt.save_group(g)
    await say(rt, "Ben", "How much is the cream?")
    gs = await groups(rt)
    assert len(gs) == 2 and gs[1].status == "auto_answered"
    assert rt.counters["instant_answers"] == 1  # new group answered from the key-level cache


async def test_host_route_goes_to_host_slots(rt):
    await say(rt, "Raj", "Is it OK for oily skin?")
    [g] = await groups(rt)
    assert g.route == "HOST" and g.status == "ready" and g.condition_slots["skin_type"] == "oily"
    s = await rt.load_session()
    assert [sl.group_id for sl in s.host_slots] == [g.group_id] and g.host_slot == "on_host"
    await say(rt, "Kai", "is it okay for dry skin too?")
    assert len(await groups(rt)) == 2  # different slot value: separate group


async def test_sensitive_goes_to_the_host_with_draft(rt):
    """D-113: the host answers sensitive questions on air; no operator routing by sensitivity."""
    await say(rt, "Jun", "Can I use it while pregnant?")
    [g] = await groups(rt)
    assert (g.route, g.route_reason, g.status) == ("HOST", "sensitive", "ready")
    answer = await rt.get_answer(g.answer_id)
    assert answer is not None and answer.verified and "pregnant" in answer.text.lower()
    assert await messages(rt) == []  # never posted automatically
    s = await rt.load_session()
    assert [sl.group_id for sl in s.host_slots] == [g.group_id]


async def test_general_question_has_no_draft(rt):
    await say(rt, "Kumar", "Do you ship to Malaysia?")
    [g] = await groups(rt)
    assert g.product_id is None and g.status == "needs_review" and g.answer_id is None


async def test_price_promo_closes_price_groups_and_invalidates_cache(rt):
    await say(rt, "Lee", "How much is the cream?")
    await rt.start_promo("promo_time_sale_10")
    [old] = await groups(rt)
    assert old.status == "closed" and old.closed_reason == "promo_changed"
    await say(rt, "Daniel", "How much is the cream?")
    gs = await groups(rt)
    assert len(gs) == 2 and gs[1].status == "auto_answered"
    assert rt.counters["composed_answers"] == 2  # fresh composer call with the promo state
    with pytest.raises(ActionError, match="already running"):
        await rt.start_promo("promo_time_sale_10")
    await rt.ctx.scheduler.advance(600_000)  # promo duration
    s = await rt.load_session()
    assert s.active_promo_id is None and s.active_promos == []
    assert all(g.status == "closed" for g in await groups(rt))


async def test_triage_failure_falls_back_to_operator(tmp_path):
    class Failing:
        name = "failing"

        async def generate(self, req, timeout_ms):
            raise LLMError("boom")

        async def warm_up(self, model, timeout_ms):
            return None

        async def aclose(self):
            return None

    ctx = make_ctx(backend=Failing())
    rt = await live_runtime(ctx)
    await say(rt, "Lee", "How much is the cream?")
    [g] = await groups(rt)
    assert (g.route, g.route_reason, g.status) == ("OPERATOR", "ai_unavailable", "needs_review")
    assert await messages(rt) == []
    ctx.runtimes.shutdown()


async def test_rate_limit_per_author(rt):
    for i in range(10):
        await say(rt, "Fast", f"hello number {i} from me", wait=False)
    with pytest.raises(RateLimited):
        await say(rt, "Fast", "one more")
    await rt.ctx.scheduler.idle()


async def test_operator_actions(rt):
    await say(rt, "Tom", "Do you ship to Malaysia?")
    [g] = await groups(rt)
    assert g.route == "OPERATOR"
    with pytest.raises(ActionError, match="verified draft"):
        await ops.approve(rt, g.group_id)
    with pytest.raises(ActionError, match="restricted phrase"):
        await ops.write_answer(rt, g.group_id, "Sure, and it cures eczema.", "operator_written", confirm=False)
    await ops.write_answer(rt, g.group_id, "We ship within Singapore only.", "operator_written", confirm=False)
    [g] = await groups(rt)
    [m] = await messages(rt)
    assert g.status == "answered" and m.kind == "brand_answer" and m.reply_to_author_names == ["Tom"]

    await say(rt, "Raj", "Is it OK for oily skin?")
    oily = next(x for x in await groups(rt) if x.intent == "skin_type_suitability")
    await ops.recall_from_host(rt, oily.group_id)
    assert (await rt.load_session()).host_slots == []
    await ops.push_to_host(rt, oily.group_id)
    s = await rt.load_session()
    assert s.host_slots[0].group_id == oily.group_id and s.host_slots[0].pinned
    await ops.reject(rt, oily.group_id)
    assert (await rt.load_session()).host_slots == []


async def test_unhide_reruns_triage(rt):
    c = await say(rt, "Spam", "visit daonlab.sg for the price?")
    assert c.visibility == "hidden"
    await ops.unhide_comment(rt, c.comment_id)
    await rt.ctx.scheduler.idle()
    c2 = await rt.get_comment(c.comment_id)
    assert c2.visibility == "visible" and c2.kind == "question"


async def test_end_stops_everything(rt):
    rt.feed.start_pool()
    s = await rt.end()
    assert s.status == "ended" and not rt.feed.pool_running
    with pytest.raises(ActionError):
        await rt.end()


async def test_feed_burst_offsets(rt):
    result = await rt.feed.fire("B1")
    assert result["status"] == "fired"
    await rt.ctx.scheduler.advance(2_000)
    first = await rt.ctx.store.query(rt.path("comments"), Comment)
    assert [c.text for c in first] == ["So pretty! 💜", "love the packaging"]
    await rt.ctx.scheduler.advance(10_000)
    assert len(await rt.ctx.store.query(rt.path("comments"), Comment)) == 9
    armed = await rt.feed.fire("B5")
    assert armed["status"] == "armed" and rt.feed.state()["armed"] == ["B5_switch_boundary"]


async def test_background_pool_is_seeded(rt):
    rt.feed.start_pool()
    await rt.ctx.scheduler.advance(60_000)
    texts = [c.text for c in await rt.ctx.store.query(rt.path("comments"), Comment, order_by="received_at")]
    assert 10 <= len(texts) <= 25
    assert all(c.source == "pool" for c in await rt.ctx.store.query(rt.path("comments"), Comment))
    rt.feed.stop_pool()


async def test_reassigning_a_drafting_question_never_applies_the_old_products_draft():
    """Review B5 (D-117): the operator moves a question to another product while its draft is being
    written; the draft for the old product must not land on it."""
    import asyncio

    from .helpers import live_runtime, make_ctx
    from .judge_fakes import ScriptedBackend

    class FirstComposerWaits(ScriptedBackend):
        def __init__(self):
            super().__init__()
            self.gate, self.started, self.first = asyncio.Event(), asyncio.Event(), True

        async def generate(self, req, timeout_ms):
            if req.agent == "answer_composer" and self.first:
                self.first = False
                self.started.set()
                await self.gate.wait()
            return await super().generate(req, timeout_ms)

    llm = FirstComposerWaits()
    ctx = make_ctx(backend=llm)
    rt = await live_runtime(ctx)
    try:
        await say(rt, "Lee", "Is it okay for oily skin?", wait=False)
        await asyncio.wait_for(llm.started.wait(), 2)
        [g] = await groups(rt)
        assert g.status == "composing" and g.product_id == "cream_hydra_barrier"
        await ops.assign_product(rt, g.group_id, "ampoule_deep_hydration")
        llm.gate.set()
        await rt.ctx.scheduler.idle()
        g = await rt.get_group(g.group_id)
        answer = await rt.get_answer(g.answer_id)
        assert g.product_id == "ampoule_deep_hydration"
        assert answer is not None and answer.cache_key == await ops.answer_key(rt, g)
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()


async def test_a_promo_change_while_drafting_drafts_again_instead_of_sticking():
    """D-117 B5: the answer key changed (promo or document) while drafting: no stale draft, no stuck group."""
    import asyncio

    from .helpers import live_runtime, make_ctx
    from .judge_fakes import ScriptedBackend

    class FirstComposerWaits(ScriptedBackend):
        def __init__(self):
            super().__init__()
            self.gate, self.started, self.first = asyncio.Event(), asyncio.Event(), True

        async def generate(self, req, timeout_ms):
            if req.agent == "answer_composer" and self.first:
                self.first = False
                self.started.set()
                await self.gate.wait()
            return await super().generate(req, timeout_ms)

    llm = FirstComposerWaits()
    ctx = make_ctx(backend=llm)
    rt = await live_runtime(ctx)
    try:
        await say(rt, "Lee", "Is it okay for oily skin?", wait=False)
        await asyncio.wait_for(llm.started.wait(), 2)
        await rt.start_promo("promo_time_sale_10")
        llm.gate.set()
        await rt.ctx.scheduler.idle()
        [g] = await groups(rt)
        answer = await rt.get_answer(g.answer_id)
        assert g.status != "composing" and answer.cache_key == await ops.answer_key(rt, g)
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
