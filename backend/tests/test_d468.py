"""D-468: the live judges' answers are not cut at 5 s. Compliance and the fact checker get 60 s (the fact deadline from
the line's end), the context judge 10 s; a call that timed out is not made again (only a fast failure is), and the
comment path's context calls keep JUDGE_TIMEOUT_MS. Made-up lines only."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.config import Settings
from app.providers.llm import AgentResult

from .judge_fakes import ScriptedBackend, claim, close_env, judge_output, speak
from .test_d462 import A, C, show, violation

WRONG = "The toner is S$20 today."


def deadlines(llm, agent: str) -> list[int]:
    return [r.deadline_ms for r in llm.requests if r.agent == agent]


class _Recording(ScriptedBackend):
    def __init__(self):
        super().__init__()
        self.requests = []

    async def generate(self, req, timeout_ms):
        self.requests.append(req)
        return await super().generate(req, timeout_ms)


def test_the_defaults():
    f = Settings.model_fields
    assert (f["VERIFY_TIMEOUT_MS"].default, f["FACT_TIMEOUT_MS"].default, f["FACT_LATE_MS"].default) == (60000,) * 3
    assert (f["CONTEXT_TIMEOUT_MS"].default, f["CONTEXT_RETRY_TOTAL_MS"].default) == (10000, 10000)
    assert f["JUDGE_TIMEOUT_MS"].default == 2500


async def test_verdicts_after_5_s_still_become_alerts():
    llm = _Recording()
    llm.outputs[("compliance_judge", A)] = violation()
    llm.delays[("compliance_judge", A)] = 5.3
    llm.facts(WRONG, claim("price", "contradicted", product_id="prd_000000000001", stated="S$20", correct="S$25.00",
                           span="S$20"), delay=5.3)
    rt = await show(llm, ALERT_GRACE=False)
    try:
        await speak(rt, A)
        await speak(rt, WRONG)
        await rt.utterances.drain()
        assert sorted(a.kind for a in await rt.alerts() if a.status == "active") == ["compliance", "fact"]
        assert deadlines(llm, "compliance_judge")[0] == 60000
        assert 59000 < deadlines(llm, "fact_checker")[0] <= 60000
        assert deadlines(llm, "context_judge")[0] == 10000
    finally:
        await close_env(rt)


@pytest.mark.parametrize("agent, settings", [
    ("compliance_judge", {"VERIFY_TIMEOUT_MS": 1500}),  # a short deadline; a retry needs 1 s of it left
    ("context_judge", {"CONTEXT_TIMEOUT_MS": 1500}),
])
async def test_a_timed_out_call_is_not_made_again_but_a_fast_failure_is(agent, settings):
    slow, broken = "It comes in a glass bottle.", "It is alcohol-free."
    llm = ScriptedBackend()
    llm.delays[(agent, slow)] = 2.0
    llm.fail(agent, broken)
    rt = await show(llm, **settings)
    try:
        await speak(rt, slow)
        await speak(rt, broken)
        await rt.utterances.drain()
        assert llm.calls.count((agent, slow)) == 1
        assert llm.calls.count((agent, broken)) == 2
    finally:
        await close_env(rt)


async def test_the_comment_paths_context_call_keeps_judge_timeout_ms():
    rt = await show(ScriptedBackend())
    try:
        seen = []
        run = rt.utterances.context.run

        async def recording(inp, deadline_ms=None, **kw):
            seen.append(deadline_ms)
            if inp.open_questions:  # the comment path's call: its deadline is all this test reads
                return AgentResult(status="error", output=None, latency_ms=0, call_id="", error="not run")
            return await run(inp, deadline_ms=deadline_ms, **kw)
        rt.utterances.context.run = recording
        t = await speak(rt, C)
        await rt.utterances.drain()
        assert seen == [10000]  # the line's own context call
        shown = SimpleNamespace(answer_id="an_1", published_message_id=None)
        rt.get_group = lambda gid: _value(shown)
        rt.get_answer = lambda aid: _value(SimpleNamespace(verified=True, text="It is 150 ml."))
        await rt.utterances._relink(t, judge_output(), None, rt.utterances._inputs[t.transcript_id], ["g1"], C)
        assert seen == [10000, 2500]
    finally:
        await close_env(rt)


async def _value(x):
    return x