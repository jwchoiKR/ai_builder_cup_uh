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
