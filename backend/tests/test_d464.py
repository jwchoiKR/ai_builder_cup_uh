"""D-464: a failed check's event carries the HTTP status Gemini answered with and the deadline the call had, so the
operator's cards can show "504", "429" or "timeout 2.5 s". Made-up lines only."""
from __future__ import annotations

from app.providers.llm import LLMServerError, LLMTimeout, _coded

from .judge_fakes import ScriptedBackend, close_env, events, speak
from .test_d462 import show

LINE = "This toner comes in a glass bottle."


class _Failing(ScriptedBackend):
    def __init__(self, errors: dict):
        super().__init__()
        self.raise_for = errors  # agent -> the exception the backend raises for LINE

    async def generate(self, req, timeout_ms):
        if req.mock_primary_text == LINE and req.agent in self.raise_for:
            raise self.raise_for[req.agent]()
        return await super().generate(req, timeout_ms)


async def failures(rt) -> dict[str, dict]:
    return {e.payload["agent"]: e.payload for e in await events(rt, "judge.failed")}


async def test_the_failure_event_carries_the_http_status_and_the_deadline():
    llm = _Failing({"compliance_judge": lambda: _coded(LLMServerError("503 UNAVAILABLE: busy"), 503),
                    "context_judge": lambda: _coded(LLMTimeout("504 DEADLINE_EXCEEDED"), 504)})
    rt = await show(llm)
    try:
        await speak(rt, LINE)
        got = await failures(rt)
        assert got["compliance_judge"]["http_status"] == 503
        assert got["compliance_judge"]["deadline_ms"] == rt.settings.VERIFY_TIMEOUT_MS
        assert got["context_judge"]["http_status"] == 504 and got["context_judge"]["cause"] == "timeout"
        snap = rt.utterances.check_failures()["recent"]  # the snapshot carries the same fields
        assert {f["agent"]: f["http_status"] for f in snap} == {"compliance_judge": 503, "context_judge": 504}
    finally:
        await close_env(rt)


async def test_our_own_timeout_has_no_http_status_but_its_deadline():
    llm = _Failing({"compliance_judge": lambda: LLMTimeout("ReadTimeout")})
    rt = await show(llm)
    try:
        await speak(rt, LINE)
        got = (await failures(rt))["compliance_judge"]
        assert (got["cause"], got["http_status"], got["deadline_ms"]) == ("timeout", None, rt.settings.VERIFY_TIMEOUT_MS)
    finally:
        await close_env(rt)
