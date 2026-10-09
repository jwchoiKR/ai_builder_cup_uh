"""D-309 (D-435: the only arm): one model judges, no verifier and no code drops. The compliance judge and the fact
checker run on SINGLE_MODEL / SINGLE_THINKING (COMPLIANCE_MODEL / FACTS_MODEL override the model), the compliance
call gets VERIFY_TIMEOUT_MS, and the judge may lower a HIGH rule to MEDIUM. Also: an unverified alert from a failed
judge carries its failure type, a window that finds no sentence is logged, and the eval rows carry alert latency."""
from __future__ import annotations

import pytest


from .judge_fakes import CREAM, ScriptedBackend, close_env, events, speak, violation


def test_d309_the_single_arm_s_models(settings, clock, ids, store, bus):
    from app.context import StoreAudit
    from app.providers.llm import LLMClient

    def specs(**kw):
        c = LLMClient(ScriptedBackend(), settings.model_copy(update=kw), clock, ids, StoreAudit(store, bus))
        return (c.compliance.model, c.compliance.thinking_level), (c.facts.model, c.facts.thinking_level)

    # D-434: the production defaults (Flash-Lite, compliance LOW, facts LOW); D-435: the only arm
    assert specs() == (("gemini-3.5-flash-lite", "LOW"), ("gemini-3.5-flash-lite", "LOW"))
    lite = specs(SINGLE_MODEL="gemini-3.5-flash-lite", SINGLE_THINKING="HIGH",
                 SINGLE_FACTS_THINKING="")  # cell A: empty = the facts follow SINGLE_THINKING
    assert lite == (("gemini-3.5-flash-lite", "HIGH"), ("gemini-3.5-flash-lite", "HIGH"))
    assert specs(COMPLIANCE_MODEL="m1")[0][0] == "m1"
    # D-311: compliance MEDIUM, facts LOW on Flash-Lite
    split = specs(SINGLE_MODEL="gemini-3.5-flash-lite", SINGLE_THINKING="MEDIUM",
                  SINGLE_FACTS_THINKING="LOW")
    assert split == (("gemini-3.5-flash-lite", "MEDIUM"), ("gemini-3.5-flash-lite", "LOW"))


class _Record(ScriptedBackend):
    def __init__(self):
        super().__init__()
        self.reqs = []

    async def generate(self, req, timeout_ms):
        self.reqs.append(req)
        return await super().generate(req, timeout_ms)
