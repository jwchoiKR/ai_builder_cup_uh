"""D-412 (user: "2. ㅇㅋ"): a failed check says its cause; the snapshot keeps the last 5 minutes' failures and the
lines unchecked since the judges last answered normally; a normal answer clears them."""
from __future__ import annotations

from app.pipelines.utterances import failure_cause
from app.providers.llm import AgentResult, LLMError

from .helpers import live_runtime, make_ctx
from .judge_fakes import ScriptedBackend, close_env, events, speak


def _res(status, failure=None):
    return AgentResult(status=status, output=None, latency_ms=1, call_id="c", meta={"failure": failure})


def test_d412_the_cause_of_a_failed_check():
    assert failure_cause(_res("error", "http_429")) == "busy"
    assert failure_cause(_res("timeout", "client_timeout")) == "timeout"
    assert failure_cause(_res("error", "http_504")) == "timeout"
    assert failure_cause(_res("invalid", "other_error")) == "invalid"
    assert failure_cause(_res("error", "other_error")) == "error"


class _Busy(ScriptedBackend):
    """Every judge call of the listed lines fails with a 429."""

    def __init__(self, lines):
        super().__init__()
        self.lines = set(lines)

    async def generate(self, req, timeout_ms):
        if req.mock_primary_text in self.lines and req.agent in ("compliance_judge", "utterance_judge", "fact_checker"):
            raise LLMError("429 RESOURCE_EXHAUSTED")
        return await super().generate(req, timeout_ms)


async def test_d412_failures_carry_their_cause_stay_in_the_snapshot_and_clear_on_a_normal_answer():
    first, second, fine = "It feels light.", "And it smells nice.", "Hello everyone."
    rt = await live_runtime(make_ctx(backend=_Busy([first, second])))
    try:
        await speak(rt, first)
        await speak(rt, second)
        checks = await events(rt, "line.check")
        assert {e.payload["cause"] for e in checks} == {"busy"}
        assert {e.payload["agent"] for e in await events(rt, "judge.failed")} == {"compliance_judge", "fact_checker"}
        snap = rt.utterances.check_failures()
        assert len(snap["recent"]) == 4  # D-416: one per line and judge
        assert {u["cause"] for u in snap["unchecked"]} == {"busy"} and len({u["transcript_id"] for u in snap["unchecked"]}) == 2
        await speak(rt, fine)  # the judges answer normally again
        [ok] = await events(rt, "checks.recovered")
        assert rt.utterances.check_failures()["unchecked"] == []
        assert len(rt.utterances.check_failures()["recent"]) == 4  # the 5-minute count stays
        await rt.ctx.scheduler.advance(300_000)
        assert rt.utterances.check_failures()["recent"] == []
        assert ok.payload["transcript_id"]
    finally:
        await close_env(rt)


# ---- D-416: context failures, per-line recovery, one counting rule -----------------------------------------


class _Fails(ScriptedBackend):
    """The listed (agent, line) calls fail with the given error."""

    def __init__(self, fails):
        super().__init__()
        self.fails = fails

    async def generate(self, req, timeout_ms):
        err = self.fails.get((req.agent, req.mock_primary_text))
        if err:
            raise LLMError(err)
        return await super().generate(req, timeout_ms)


async def test_d416_a_context_only_failure_shows():
    line = "It feels light."
    rt = await live_runtime(make_ctx(backend=_Fails({("context_judge", line): "429 RESOURCE_EXHAUSTED"})))
    try:
        await speak(rt, line)
        [f] = await events(rt, "judge.failed")
        assert (f.payload["agent"], f.payload["cause"]) == ("context_judge", "busy")
        assert [u["transcript_id"] for u in rt.utterances.check_failures()["unchecked"]] == [f.payload["transcript_id"]]
    finally:
        await close_env(rt)


async def test_d416_an_earlier_line_s_late_success_does_not_clear_a_later_failure():
    import asyncio

    a, b = "It feels light.", "And it smells nice."
    llm = _Fails({("compliance_judge", b): "429 RESOURCE_EXHAUSTED"})
    llm.delays[("compliance_judge", a)] = 0.3  # A's verdicts land after B's failure
    rt = await live_runtime(make_ctx(backend=llm))
    try:
        await rt.inject_transcript(a)
        await rt.inject_transcript(b)
        await rt.utterances.drain()
        await asyncio.sleep(0.4)
        await rt.ctx.scheduler.idle()
        [fb] = await events(rt, "judge.failed")
        assert [u["transcript_id"] for u in rt.utterances.check_failures()["unchecked"]] == [fb.payload["transcript_id"]]
        assert await events(rt, "checks.recovered") == []
    finally:
        await close_env(rt)


async def test_d416_busy_then_timeout_on_one_line_counts_the_same_live_and_after_a_refresh():
    line = "It feels light."
    rt = await live_runtime(make_ctx(backend=_Fails({("compliance_judge", line): "429 RESOURCE_EXHAUSTED",
                                                     ("fact_checker", line): "504 DEADLINE_EXCEEDED"})))
    try:
        await speak(rt, line)
        live = [(e.payload["agent"], e.payload["cause"]) for e in await events(rt, "judge.failed")]
        snap = rt.utterances.check_failures()
        assert sorted(live) == sorted((x["agent"], x["cause"]) for x in snap["recent"])
        assert sorted(c for _, c in live) == ["busy", "timeout"]
        # D-420: the same events, in the same (at, n) order, as the live stream carried them
        assert [(u["agent"], u["cause"]) for u in snap["unchecked"]] == live
        assert [e.payload["n"] for e in await events(rt, "judge.failed")] == [u["n"] for u in snap["unchecked"]]
    finally:
        await close_env(rt)


async def test_d420_an_unchecked_line_older_than_5_minutes_stays_in_the_snapshot():
    line = "It feels light."
    rt = await live_runtime(make_ctx(backend=_Fails({("compliance_judge", line): "429 RESOURCE_EXHAUSTED"})))
    try:
        await speak(rt, line)
        await rt.ctx.scheduler.advance(360_000)
        snap = rt.utterances.check_failures()
        assert snap["recent"] == []  # only the per-cause count uses the 5-minute window
        assert [(u["agent"], u["cause"]) for u in snap["unchecked"]] == [("compliance_judge", "busy")]
    finally:
        await close_env(rt)
