"""D-408 (codex on D-388): a fact check is retried only after a fast failure (error, invalid); an invalid answer is
asked again without JUDGE_SEED; a timeout is not retried and shows the judge-failed state at once; the result's
latency counts both calls."""
from __future__ import annotations

import pytest

import asyncio

from app.providers.llm import AgentResult, LLMError, RawReply

from .helpers import live_runtime, make_ctx
from .judge_fakes import CREAM, ScriptedBackend, close_env, events, speak

LINE = "It's thirty-six dollars today."


class _FirstFactCall(ScriptedBackend):
    """The first fact call fails in the given way; every fact call's seed is kept."""

    def __init__(self, how: str, after: float = 0.0):
        super().__init__()
        self.how, self.after, self.seeds, self.deadlines = how, after, [], []

    async def generate(self, req, timeout_ms):
        if req.agent == "fact_checker":
            self.seeds.append(req.seed)
            self.deadlines.append(timeout_ms)
            if len(self.seeds) == 1:
                await asyncio.sleep(self.after)
                if self.how == "error":
                    raise LLMError("scripted failure")
                if self.how == "invalid":
                    return RawReply("{not json", model_version="scripted")
                await asyncio.sleep(timeout_ms / 1000 + 0.2)  # timeout
        return await super().generate(req, timeout_ms)


async def _run(how: str, late_ms: int = 3000, after: float = 0.0):
    backend = _FirstFactCall(how, after)
    backend.facts(LINE)
    rt = await live_runtime(make_ctx(backend=backend, JUDGE_SEED="7", FACT_LATE_MS=late_ms, FACT_TIMEOUT_MS=late_ms))
    await speak(rt, LINE)
    return rt, backend


async def test_d408_an_error_is_retried_with_the_seed():
    rt, backend = await _run("error")
    try:
        assert backend.seeds == [7, 7]
        assert not await events(rt, "line.check")
    finally:
        await close_env(rt)


async def test_d408_an_invalid_answer_is_retried_without_the_seed():
    rt, backend = await _run("invalid")
    try:
        assert backend.seeds == [7, None]
        assert not await events(rt, "line.check")
    finally:
        await close_env(rt)


async def test_d408_a_timeout_is_not_retried_and_shows_the_failure_at_once():
    rt, backend = await _run("timeout", late_ms=300)
    try:
        assert backend.seeds == [7]
        [card] = await events(rt, "line.check")
        assert card.payload["text"] == LINE and card.payload["rule_ids"] == []
        assert [e.payload["agent"] for e in await events(rt, "judge.failed")] == ["fact_checker"]
    finally:
        await close_env(rt)


async def test_d408_the_retried_result_counts_the_failed_call_s_time():
    from app.agents.utterance_judge import JudgeInput

    rt = await live_runtime(make_ctx(backend=ScriptedBackend()))
    calls = []

    async def run(inp, *, deadline_ms, **opts):
        calls.append(opts)
        if len(calls) == 1:
            return AgentResult(status="invalid", output=None, latency_ms=1200, call_id="c1", error="bad json")
        return AgentResult(status="ok", output=None, latency_ms=300, call_id="c2")

    rt.utterances.facts.run = run
    try:
        res = await rt.utterances._run_facts(LINE, CREAM, JudgeInput(utterance=LINE, on_air=CREAM), "default")
        assert res.latency_ms == 1500 and res.meta["first_failure"] == "invalid"
        assert calls == [{}, {"seeded": False}]
    finally:
        await close_env(rt)


# ---- D-411/D-417: one fact deadline for the line, from its end; the time left is measured by the clock ------------


async def _deadline_run(first_ms: int, end_ago_ms: int = 0, status: str = "invalid"):
    """_run_facts on a line that ended `end_ago_ms` ago; the first call takes `first_ms` of clock time (its audit save
    included) and comes back `status`. Returns (calls as (deadline_ms, opts), result)."""
    from app.agents.utterance_judge import JudgeInput
    from app.models.session import Transcript

    rt = await live_runtime(make_ctx(backend=ScriptedBackend(), FACT_LATE_MS=5000))
    now = rt.now()
    t = Transcript(transcript_id="tr_x", text=LINE, is_final=True, speech_end_at=now - end_ago_ms, received_at=now,
                   source="injected", segment_id="seg_x")
    rt.utterances._prepared["tr_x"] = (t, LINE, None)
    calls = []

    async def run(inp, *, deadline_ms, **opts):
        calls.append((deadline_ms, opts))
        if len(calls) == 1:
            rt.ctx.clock.advance(first_ms)
            return AgentResult(status=status, output=None, latency_ms=first_ms, call_id="c1")
        return AgentResult(status="ok", output=None, latency_ms=10, call_id="c2")

    rt.utterances.facts.run = run
    try:
        res = await rt.utterances._run_facts(LINE, CREAM, JudgeInput(utterance=LINE, on_air=CREAM), "default",
                                             transcript_id="tr_x")
    finally:
        await close_env(rt)
    return calls, res


async def test_d417_a_call_starting_2_s_after_the_line_end_gets_only_the_rest():
    calls, res = await _deadline_run(first_ms=3000, end_ago_ms=2000, status="timeout")
    assert [d for d, _ in calls] == [3000]  # it times out at the line's deadline, 5 s after the line end
    assert res.status == "timeout"


async def test_d417_a_line_whose_deadline_passed_is_not_checked():
    calls, res = await _deadline_run(first_ms=0, end_ago_ms=5000)
    assert calls == [] and res.status == "timeout" and res.meta["failure"] == "client_timeout"


@pytest.mark.parametrize("first_ms, retried", [(3999, True), (4000, True), (4001, False), (4100, False)])
async def test_d417_the_retry_needs_1_s_left_by_the_clock(first_ms, retried):
    # the first call (with its slow audit save) used first_ms of the line's 5 s
    calls, _ = await _deadline_run(first_ms=first_ms)
    assert len(calls) == (2 if retried else 1)
    if retried:
        assert calls[1] == (5000 - first_ms, {"seeded": False})
