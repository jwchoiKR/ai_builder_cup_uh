"""D-408 (codex on D-388): a fact check is retried only after a fast failure (error, invalid); an invalid answer is
asked again without JUDGE_SEED; a timeout is not retried and shows the judge-failed state at once; the result's
latency counts both calls."""
from __future__ import annotations

import asyncio

from app.providers.llm import AgentResult, LLMError, RawReply

from .helpers import live_runtime, make_ctx
from .judge_fakes import CREAM, ScriptedBackend, close_env, events, speak

LINE = "It's thirty-six dollars today."


class _FirstFactCall(ScriptedBackend):
    """The first fact call fails in the given way; every fact call's seed is kept."""

    def __init__(self, how: str):
        super().__init__()
        self.how, self.seeds = how, []

    async def generate(self, req, timeout_ms):
        if req.agent == "fact_checker":
            self.seeds.append(req.seed)
            if len(self.seeds) == 1:
                if self.how == "error":
                    raise LLMError("scripted failure")
                if self.how == "invalid":
                    return RawReply("{not json", model_version="scripted")
                await asyncio.sleep(timeout_ms / 1000 + 0.2)  # timeout
        return await super().generate(req, timeout_ms)


async def _run(how: str):
    backend = _FirstFactCall(how)
    backend.facts(LINE)
    rt = await live_runtime(make_ctx(backend=backend, JUDGE_SEED="7", FACT_LATE_MS=300, FACT_TIMEOUT_MS=300))
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
    rt, backend = await _run("timeout")
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
