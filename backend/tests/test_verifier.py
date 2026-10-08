"""D-300 R2 (JUDGE_ARM=verify): the flaggers keep every candidate (no code drops), one verifier call per candidate
keeps or rejects it, decides a compliance alert's severity, and a verifier failure keeps the candidate as an
unverified alert. Made-up lines; the verifier's answers are scripted."""
from __future__ import annotations

import pytest


from .judge_fakes import CREAM, ScriptedBackend, close_env, speak, violation
from .test_relation import _RelationBackend

V = "ASEAN-2D-VULNERABLE"
LINE = "Zero side effects with this cream."
SPAN = "Zero side effects"


def _verdict(decision: str, severity: str | None = None, evidence: str | None = None) -> dict:
    return {"evidence": evidence, "reason": f"scripted {decision}", "decision": decision, "severity": severity}


async def _compliance(arm: str, verdict: dict | None = None, fail: bool = False):
    from .helpers import live_runtime, make_ctx

    llm = ScriptedBackend()
    llm.judge(LINE, violations=[violation(V, SPAN)])
    if verdict is not None:
        llm.outputs[("verifier", f"{LINE}|{SPAN}")] = verdict
    if fail:
        llm.fail("verifier", f"{LINE}|{SPAN}")
    rt = await live_runtime(make_ctx(backend=llm, JUDGE_ARM=arm))
    try:
        await speak(rt, LINE)
        await rt.utterances.drain()
        return [a for a in await rt.alerts() if a.kind == "compliance" and a.status == "active"], llm
    finally:
        await close_env(rt)


@pytest.mark.parametrize("verdict, fail, alerts, severity, unverified", [
    (_verdict("reject"), False, 0, None, None),
    (_verdict("keep", "MEDIUM"), False, 1, "MEDIUM", False),  # the verifier decides the severity
    (_verdict("keep", "HIGH"), False, 1, "HIGH", False),
    (None, True, 1, "HIGH", True),  # a verifier failure keeps the candidate, marked unverified
])
async def test_d300_the_verifier_decides_compliance(verdict, fail, alerts, severity, unverified):
    active, llm = await _compliance("verify", verdict, fail)
    assert ("verifier", f"{LINE}|{SPAN}") in llm.calls
    assert len(active) == alerts
    if alerts:
        assert (active[0].severity, active[0].unverified) == (severity, unverified)


@pytest.mark.parametrize("verdict, fail, alerts, unverified", [
    (_verdict("reject"), False, 0, None),
    (_verdict("keep"), False, 1, False),
    (None, True, 1, True),
])
async def test_d300_the_verifier_decides_facts(verdict, fail, alerts, unverified):
    from .helpers import live_runtime, make_ctx

    line, span = "It's only thirty-two dollars today.", "thirty-two dollars"
    llm = _RelationBackend("contradicts")
    if verdict is not None:
        llm.outputs[("verifier", f"{line}|{span}")] = verdict
    if fail:
        llm.fail("verifier", f"{line}|{span}")
    rt = await live_runtime(make_ctx(backend=llm, FACT_RELATION=True, FACT_GUARDS="off", JUDGE_ARM="verify"))
    try:
        await speak(rt, line)
        await rt.utterances.drain()
        facts = [a for a in await rt.alerts() if a.kind == "fact"]
        assert len(facts) == alerts
        if alerts:
            assert facts[0].unverified is unverified and facts[0].correct_value == "S$36.00"
    finally:
        await close_env(rt)


async def test_d301_window_evidence_is_the_cited_sentences_and_their_neighbours():
    from .helpers import live_runtime, make_ctx

    rt = await live_runtime(make_ctx(backend=ScriptedBackend(), JUDGE_ARM="verify", VERIFY_EVIDENCE="window"))
    try:
        v = rt.utterances.verifier
        blocks, index = v.source(CREAM)
        win = v.evidence(CREAM, "Live broadcast price: S$36.00")
        got = [s for b in win for s in b["sentences"]]
        assert any("S$36.00" in s[1] for s in got) and 1 <= len(got) <= 2 * 2 + 1 < len(index)
        assert all(s[0] in index for s in got)  # the same ids as the whole documents
        assert v.evidence(CREAM, None) == []  # a compliance candidate gets no documents in window mode
    finally:
        await close_env(rt)


async def test_d301_the_verifier_cache_is_warmed_at_session_start():
    from .helpers import live_runtime, make_ctx

    class Warm(ScriptedBackend):
        def __init__(self):
            super().__init__()
            self.warmed = []

        async def warm_cache(self, req):
            self.warmed.append(req.agent)

    llm = Warm()
    rt = await live_runtime(make_ctx(backend=llm, JUDGE_ARM="verify"))
    try:
        await rt.ctx.scheduler.idle()
        assert "verifier" in llm.warmed
    finally:
        await close_env(rt)


def test_d301_the_verifier_is_hedged_only_when_named(settings, clock, ids, store, bus):
    from app.context import StoreAudit
    from app.providers.llm import LLMClient

    for names, hedged in (("compliance,fact,context", False), ("compliance,verifier", True)):
        s = settings.model_copy(update={"HEDGED_AGENTS": names})
        client = LLMClient(ScriptedBackend(), s, clock, ids, StoreAudit(store, bus))
        assert ("verifier" in client._hedged_agents) is hedged
