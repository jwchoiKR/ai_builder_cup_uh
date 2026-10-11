"""D-450: the prompter judge is the only judge that ticks prompter points. It runs per final line next to the other
three judges, nothing waits on it, its ticks go to the line's own segment (also when the result comes after a
switch), and its failures only count for the operator (no host strip). The context judge no longer ticks. A made-up
two-product show built as the rebuilt onboarding builds one; the judges' answers are scripted."""
from __future__ import annotations

import asyncio

from app.models.session import AgentCall
from app.pipelines.utterances import operator_switch

from .helpers import text_pdf
from .judge_fakes import ScriptedBackend, close_env, events, speak

REG = text_pdf("Lunelle Code\n2.1 A cosmetic must not be presented as treating disease.\n")
CREAM = {"brand": "Lunelle", "product_name": "Hydra Calm Cream", "category": "face cream", "currency": "SGD",
         "variants": [{"label": "", "list_price": "42.00", "live_price": "36.00"}],
         "points": [{"text": "5% panthenol to calm dry skin.", "required": True},
                    {"text": "Fragrance-free.", "required": False}]}
AMPOULE = {"brand": "Lunelle", "product_name": "Deep Glow", "category": "serum ampoule", "currency": "SGD",
           "variants": [{"label": "", "list_price": "48.00", "live_price": "39.00"}],
           "points": [{"text": "10% niacinamide.", "required": True}]}
P1, P2, NEXT_P1 = "prd_000000000101-p1", "prd_000000000101-p2", "prd_000000000102-p1"
LINE = "This one has 5% panthenol to calm dry skin."


class _Backend(ScriptedBackend):
    def __init__(self):
        super().__init__()
        self.requests = []

    async def generate(self, req, timeout_ms):
        self.requests.append(req)
        return await super().generate(req, timeout_ms)


def _covered(*ids: str) -> dict:
    return {"covered": [{"host_words": LINE, "point_id": i} for i in ids]}


async def _show(llm):
    from app.pipelines.runtime import create_session

    from .helpers import make_ctx, product_show

    ctx = make_ctx(backend=llm)
    keys = [product_show(ctx, CREAM, [("lunelle_code.pdf", REG)], "prd_000000000101", "reg_000000000101"),
            product_show(ctx, AMPOULE, [("lunelle_code.pdf", REG)], "prd_000000000102", "reg_000000000102")]
    s = await create_session(ctx, "", release_ids=keys)
    rt = await ctx.runtimes.get(s.session_id)
    await rt.start()
    await ctx.scheduler.advance(5000)
    return rt


async def _covered_now(rt) -> list[str]:
    return list((await rt.current_segment()).covered_point_ids)


async def test_d450_the_prompter_judge_ticks_the_lines_points():
    llm = _Backend()
    llm.outputs[("prompter_judge", LINE)] = _covered(P1, NEXT_P1, "not-a-point")  # an unknown id is skipped
    rt = await _show(llm)
    try:
        await speak(rt, LINE)
        await rt.utterances.drain()
        assert await _covered_now(rt) == [P1]
        assert (await rt.load_session()).pre_covered == {"prd_000000000102": [NEXT_P1]}  # the next product, as before
        [req] = [r for r in llm.requests if r.agent == "prompter_judge"]
        # D-455: gemini-3.8-flash LOW, no app deadline, no 429 wait, not hedged
        assert (req.model, req.thinking_level, req.deadline_ms, req.retry_429, req.hedge) == (
            "gemini-3.8-flash", "LOW", None, False, False)
        assert '"brand":"Lunelle"' in req.user_message and '"category":"serum ampoule"' in req.user_message
    finally:
        await close_env(rt)


async def test_d450_the_context_judge_no_longer_ticks(caplog):
    caplog.set_level("INFO")
    llm = _Backend()
    llm.judge(LINE, covered=[P1, P2])  # a scripted one-call verdict that names points: the context part drops them
    rt = await _show(llm)
    try:
        await speak(rt, LINE)
        await rt.utterances.drain()
        assert await _covered_now(rt) == []  # no prompter judge script: it ticks nothing
        ctx_req = [r for r in llm.requests if r.agent == "context_judge"][-1]
        assert "covered_point_ids" not in str(ctx_req.output_model.model_json_schema())
        assert "covered_point_ids" not in ctx_req.system_instruction
        assert any(r.getMessage().startswith("context ") and "points=[]" in r.getMessage() for r in caplog.records)
        assert not [r for r in caplog.records if "background task" in r.getMessage()]  # the context verdict applied
    finally:
        await close_env(rt)


async def test_d450_a_late_result_after_a_switch_ticks_the_lines_own_segment():
    llm = _Backend()
    llm.outputs[("prompter_judge", LINE)] = _covered(P1)
    llm.delays[("prompter_judge", LINE)] = 0.3  # the answer comes after the switch
    rt = await _show(llm)
    try:
        first = await rt.current_segment()
        await speak(rt, LINE, wait=False)
        await asyncio.sleep(0.05)
        await operator_switch(rt, "prd_000000000102")
        await rt.utterances.drain()
        now = await rt.current_segment()
        assert now.product_id == "prd_000000000102" and now.covered_point_ids == []
        assert (await rt.get_segment(first.segment_id)).covered_point_ids == [P1]
    finally:
        await close_env(rt)


async def test_d450_a_failed_prompter_check_only_counts_for_the_operator():
    llm = _Backend()
    llm.fail("prompter_judge", LINE)
    rt = await _show(llm)
    try:
        await speak(rt, LINE)
        await rt.utterances.drain()
        assert await events(rt, "line.check") == [] and await events(rt, "judge.failed") == []  # no host strip
        [ev] = await events(rt, "prompter.failed")
        assert (ev.payload["agent"], ev.payload["cause"]) == ("prompter_judge", "error")
        failures = rt.utterances.check_failures()
        assert [f["agent"] for f in failures["recent"]] == ["prompter_judge"] and failures["unchecked"] == []
        snap = await rt.snapshot("host")
        assert snap["check_failures"]["unchecked"] == []
    finally:
        await close_env(rt)


async def test_d455_a_result_after_later_lines_and_a_switch_ticks_its_own_line():
    llm = _Backend()
    llm.outputs[("prompter_judge", LINE)] = _covered(P1)
    llm.delays[("prompter_judge", LINE)] = 0.5  # no deadline: it comes after two more lines and a switch
    rt = await _show(llm)
    try:
        first = await rt.current_segment()
        await speak(rt, LINE, wait=False)
        await asyncio.sleep(0.05)
        await speak(rt, "And the texture is light.")
        await operator_switch(rt, "prd_000000000102")
        await speak(rt, "Now the ampoule, it has 10% niacinamide.")
        await rt.utterances.drain()
        assert (await rt.get_segment(first.segment_id)).covered_point_ids == [P1]
        assert (await rt.current_segment()).covered_point_ids == []
        [call] = [c for c in await rt.ctx.store.query(rt.path("agent_calls"), AgentCall)
                  if c.agent == "prompter_judge" and c.input_preview == LINE]
        assert call.status == "ok" and call.latency_ms >= 500
    finally:
        await close_env(rt)
