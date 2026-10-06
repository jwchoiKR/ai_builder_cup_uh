"""D-309 (JUDGE_ARM=single): one model judges, no verifier and no code drops. The compliance judge and the fact
checker run on SINGLE_MODEL / SINGLE_THINKING (COMPLIANCE_MODEL / FACTS_MODEL override the model), the compliance
call gets VERIFY_TIMEOUT_MS, and the judge may lower a HIGH rule to MEDIUM. Also: an unverified alert from a failed
judge carries its failure type, a window that finds no sentence is logged, and the eval rows carry alert latency."""
from __future__ import annotations

import pytest

from app.providers.llm import LLMError

from .conftest import SHIPPED
from .judge_fakes import CREAM, ScriptedBackend, close_env, events, make_env, speak, violation


def test_d309_the_single_arm_s_models(settings, clock, ids, store, bus):
    from app.context import StoreAudit
    from app.providers.llm import LLMClient

    def specs(**kw):
        c = LLMClient(ScriptedBackend(), settings.model_copy(update=kw), clock, ids, StoreAudit(store, bus))
        return (c.compliance.model, c.compliance.thinking_level), (c.facts.model, c.facts.thinking_level)

    fast = settings.LLM_FAST_MODEL
    assert specs(JUDGE_ARM="verify") == ((fast, settings.COMPLIANCE_THINKING), (fast, settings.FACTS_THINKING))
    assert specs(JUDGE_ARM="single") == (("gemini-3.8-flash", "LOW"), ("gemini-3.8-flash", "LOW"))  # cell B
    lite = specs(JUDGE_ARM="single", SINGLE_MODEL="gemini-3.5-flash-lite", SINGLE_THINKING="HIGH")  # cell A
    assert lite == (("gemini-3.5-flash-lite", "HIGH"), ("gemini-3.5-flash-lite", "HIGH"))
    assert specs(JUDGE_ARM="single", COMPLIANCE_MODEL="m1")[0][0] == "m1"


class _Record(ScriptedBackend):
    def __init__(self):
        super().__init__()
        self.reqs = []

    async def generate(self, req, timeout_ms):
        self.reqs.append(req)
        return await super().generate(req, timeout_ms)


@pytest.mark.parametrize("said, severity", [("HIGH", "HIGH"), ("MEDIUM", "MEDIUM")])
async def test_d309_one_judge_no_verifier_no_drops(said, severity):
    from .helpers import live_runtime, make_ctx

    llm = _Record()
    line = "Zero side effects with this cream."  # Q6/CK would drop it in guards mode: no group named
    llm.judge(line, violations=[violation("ASEAN-2D-VULNERABLE", "Zero side effects", severity=said)])
    rt = await live_runtime(make_ctx(backend=llm, **(SHIPPED | {"JUDGE_ARM": "single"})))
    try:
        await speak(rt, line)
        await rt.utterances.drain()
        [a] = [a for a in await rt.alerts() if a.kind == "compliance" and a.status == "active"]
        assert a.severity == severity  # the judge may lower a HIGH rule to MEDIUM
        assert not any(r.agent == "verifier" for r in llm.reqs) and await events(rt, "verify.started") == []
        assert {r.deadline_ms for r in llm.reqs if r.agent == "compliance_judge"} == {5000}
        assert rt.utterances.verifier is None
    finally:
        await close_env(rt)


async def test_d309_a_failed_judge_s_unverified_alert_says_why():
    class Busy(ScriptedBackend):
        async def generate(self, req, timeout_ms):
            if req.agent in ("compliance_judge", "utterance_judge"):
                raise LLMError("504 DEADLINE_EXCEEDED")
            return await super().generate(req, timeout_ms)

    from .helpers import live_runtime, make_ctx

    rt = await live_runtime(make_ctx(backend=Busy(), REFLEX_ON_FAIL="alert"))
    try:
        await speak(rt, "This cream cures eczema.")
        await rt.utterances.drain()
        [a] = [a for a in await rt.alerts() if a.kind == "compliance" and a.status == "active"]
        assert (a.unverified, a.unverified_reason) == (True, "http_504")
    finally:
        await close_env(rt)


async def test_d309_a_window_with_no_matching_sentence_is_logged():
    from app.agents.fact_checker import DROPS

    rt, _ = await make_env(**SHIPPED)
    try:
        sink: list = []
        token = DROPS.set(sink)
        try:
            assert rt.utterances.verifier.evidence(CREAM, "A quote that is in no document at all") == []
        finally:
            DROPS.reset(token)
        assert [d["reason"] for d in sink] == ["verifier window: no sentence matches the quote"]
    finally:
        await close_env(rt)


async def test_d309_eval_rows_carry_the_alert_latency(monkeypatch):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import eval_adversarial

    from .helpers import make_ctx

    line = "This cream cures eczema."
    llm = ScriptedBackend()
    llm.judge(line, violations=[violation("ASEAN-2D-DISEASE", "cures eczema")])
    real_sleep = __import__("asyncio").sleep
    monkeypatch.setattr(__import__("asyncio"), "sleep", lambda _s: real_sleep(0))
    ctx = make_ctx(backend=llm)
    try:
        row = await eval_adversarial.run_case(ctx, {"case_id": "L", "type": "t", "utterance": line,
                                                    "current_product_id": CREAM,
                                                    "expected": {"risky": True}}, 0)
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
    [a] = [a for a in row["alerts"] if a["kind"] == "compliance"]
    assert a["ms_to_shown"] is not None and a["ms_to_shown"] >= 0 and a["ms_to_created"] is not None
