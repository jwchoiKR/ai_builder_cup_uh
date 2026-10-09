"""D-349 SWITCH_MODE=immediate: the context judge's transition verdict alone switches the prompter at once (no name
match, no confirming line, no pending countdown); for SWITCH_DUAL_SCOPE_SEC after a switch or an undo the fact
checker and the compliance judge get both products, labelled, and the compliance judge says which product each claim
is about. The default (two_step) is unchanged. Made-up lines on the demo show's two products."""
from __future__ import annotations

import pytest

from .judge_fakes import AMPOULE, CREAM, ScriptedBackend, close_env, events, speak, violation

MOVE_ON = "Okay, let me show you the next one now."  # names no product


class _Recording(ScriptedBackend):
    def __init__(self) -> None:
        super().__init__()
        self.requests = []

    async def generate(self, req, timeout_ms):
        self.requests.append(req)
        return await super().generate(req, timeout_ms)

    def last(self, agent: str, text: str):
        return [r for r in self.requests if r.agent == agent and r.mock_primary_text == text][-1]


async def _env(**settings):
    from .helpers import live_runtime, make_ctx

    llm = _Recording()
    rt = await live_runtime(make_ctx(backend=llm, **settings))
    return rt, llm


async def _on_air(rt) -> str:
    return (await rt.current_segment()).product_id


async def test_d349_a_transition_verdict_switches_at_once():
    rt, llm = await _env()
    try:
        llm.judge(MOVE_ON, utterance_type="transition", transition=True, target=AMPOULE, confidence="medium",
                  reason="the host moves on to the next product")
        await speak(rt, MOVE_ON)
        assert await _on_air(rt) == AMPOULE  # no confirming line, no 5 s countdown, no name heard
        assert not await events(rt, "segment.switch_counting") and not await events(rt, "segment.switch_pending")
        [d] = await events(rt, "segment.switch_decided")
        assert d.payload["switch"] is True and d.payload["confidence"] == "medium"
        assert d.payload["reason"] == "the host moves on to the next product"
        [seg] = [e for e in await events(rt, "segment.started") if e.payload["product_id"] == AMPOULE]
        assert seg.payload["start_reason"] == "auto_speech"
        s = await rt.load_session()
        assert s.switch.last_commit["immediate"] is True and s.switch.previous_product_id == CREAM
    finally:
        await close_env(rt)


@pytest.mark.parametrize("kw", [
    {"quote": True},  # a viewer's words read out
    {"target": CREAM},  # back to the on-air product
])  # D-351: an answer line and a low confidence no longer block a switch (tests/test_d351.py)
async def test_d349_no_switch_on_a_quote_or_another_target(kw):
    rt, llm = await _env()
    try:
        llm.judge(MOVE_ON, **({"utterance_type": "transition", "transition": True, "target": AMPOULE,
                               "confidence": "high"} | kw))
        await speak(rt, MOVE_ON)
        assert await _on_air(rt) == CREAM
        assert [e.payload["switch"] for e in await events(rt, "segment.switch_decided")] == [False]
    finally:
        await close_env(rt)


async def test_d349_both_products_reach_the_judges_for_the_window_only():
    from .judge_fakes import advance

    rt, llm = await _env(SWITCH_DUAL_SCOPE_SEC=10)
    try:
        llm.judge(MOVE_ON, utterance_type="transition", transition=True, target=AMPOULE, confidence="high")
        await speak(rt, MOVE_ON)
        inside, outside = "This one feels so light on the skin.", "You can layer it under any cream."
        await speak(rt, inside)
        comp = llm.last("compliance_judge", inside)
        assert '<data name="PREVIOUS_PRODUCT">' in comp.user_message and CREAM in comp.user_message
        assert "product_id" in comp.output_model.model_json_schema()["$defs"][
            next(k for k in comp.output_model.model_json_schema()["$defs"] if k.startswith("Violation"))]["properties"]
        facts = llm.last("fact_checker", inside)
        assert '"previous_product"' in facts.user_message and CREAM in facts.user_message
        await advance(rt, 10_001)
        await speak(rt, outside)
        comp = llm.last("compliance_judge", outside)
        assert "PREVIOUS_PRODUCT" not in comp.user_message and '"previous_product"' not in llm.last(
            "fact_checker", outside).user_message
    finally:
        await close_env(rt)


async def test_d349_an_undo_opens_the_window_for_the_undone_product():
    from app.pipelines.utterances import undo_switch

    rt, llm = await _env()
    try:
        llm.judge(MOVE_ON, utterance_type="transition", transition=True, target=AMPOULE, confidence="high")
        await speak(rt, MOVE_ON)
        await undo_switch(rt)
        s = await rt.load_session()
        assert await _on_air(rt) == CREAM and s.switch.previous_product_id == AMPOULE
        line = "So that is the cream again."
        await speak(rt, line)
        assert AMPOULE in llm.last("compliance_judge", line).user_message.split('<data name="PREVIOUS_PRODUCT">')[1]
    finally:
        await close_env(rt)


async def close_env_ctx(ctx) -> None:
    ctx.runtimes.shutdown()
    ctx.scheduler.shutdown()
