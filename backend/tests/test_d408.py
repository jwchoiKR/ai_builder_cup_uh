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


# ---- D-411/D-417: one fact deadline for the line, from its end; the time left is measured by the clock ------------


async def _deadline_run(first_ms: int, end_ago_ms: int = 0, status: str = "invalid", step_back_ms: int = 0,
                        latency_ms: int | None = None, lookup_ms: int = 0):
    """_run_facts on a line that ended `end_ago_ms` ago; the first call takes `first_ms` of clock time (its audit save
    included) and comes back `status`. Returns (calls as (deadline_ms, opts), result)."""
    from app.agents.utterance_judge import JudgeInput
    from app.models.session import Transcript

    rt = await live_runtime(make_ctx(backend=ScriptedBackend(), FACT_LATE_MS=5000))
    now = rt.now()
    t = Transcript(transcript_id="tr_x", text=LINE, is_final=True, speech_end_at=now - end_ago_ms, received_at=now,
                   source="injected", segment_id="seg_x")
    rt.utterances._prepared["tr_x"] = (t, LINE, None)
    calls, lookups = [], []

    async def run(inp, *, deadline_ms, **opts):
        calls.append((deadline_ms, opts))
        if len(calls) == 1:
            rt.ctx.clock.advance(first_ms)
            rt.ctx.clock.set(rt.ctx.clock.now_ms() - step_back_ms)  # D-421: a wall-clock step back
            return AgentResult(status=status, output=None,
                               latency_ms=first_ms if latency_ms is None else latency_ms, call_id="c1")
        return AgentResult(status="ok", output=None, latency_ms=10, call_id="c2")

    real_passages = rt.utterances._fact_passages

    async def passages(*args, **kw):  # D-421: a slow lookup before the call
        lookups.append(1)
        rt.ctx.clock.advance(lookup_ms)
        return await real_passages(*args, **kw)

    rt.utterances.facts.run = run
    rt.utterances._fact_passages = passages
    try:
        res = await rt.utterances._run_facts(LINE, CREAM, JudgeInput(utterance=LINE, on_air=CREAM), "default",
                                             transcript_id="tr_x")
    finally:
        await close_env(rt)
    _deadline_run.lookups = lookups
    return calls, res


# ---- D-421: monotonic time spent; the deadline checked before the lookups and before the call -------------------


async def test_d422_the_test_scheduler_moves_the_monotonic_time_too():
    from app.clock import ManualClock
    from app.scheduler import ManualScheduler

    clock = ManualClock()
    sched = ManualScheduler(clock)
    fired = []
    sched.call_later("t", 1000, lambda: fired.append(clock.monotonic_ms()) or _noop())
    before = clock.monotonic_ms()
    await sched.advance(2500)
    assert fired == [before + 1000] and clock.monotonic_ms() == before + 2500
    sched.shutdown()


async def _noop():
    return None
