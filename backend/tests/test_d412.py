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
        assert len(snap["recent"]) == 2 and snap["unchecked"]["cause"] == "busy"  # one per line, both judges
        assert len(snap["unchecked"]["ids"]) == 2
        await speak(rt, fine)  # the judges answer normally again
        [ok] = await events(rt, "checks.recovered")
        assert rt.utterances.check_failures()["unchecked"] == {"ids": [], "cause": None}
        assert len(rt.utterances.check_failures()["recent"]) == 2  # the 5-minute count stays
        await rt.ctx.scheduler.advance(300_000)
        assert rt.utterances.check_failures()["recent"] == []
        assert ok.payload["transcript_id"]
    finally:
        await close_env(rt)
