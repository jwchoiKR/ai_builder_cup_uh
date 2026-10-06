"""D-303 (the STT set): switches for speech-to-text input. STT_AWARE tells the flaggers and the verifier the line is
speech-to-text; CONTEXT_WINDOW_MS gives the judges the finals of the last N ms; NUMBER_CHECK lets the verifier answer
"check" for one misheard number, shown as "check what was said". Made-up lines."""
from __future__ import annotations

import pytest

from .judge_fakes import ScriptedBackend, close_env, speak
from .test_relation import _RelationBackend


@pytest.mark.parametrize("on", [False, True])
async def test_d303_stt_aware_prompts(on):
    from app.agents.split_judges import ComplianceJudge

    from .helpers import live_runtime, make_ctx

    rt = await live_runtime(make_ctx(backend=ScriptedBackend(), STT_AWARE=on, JUDGE_ARM="verify"))
    try:
        j = ComplianceJudge(rt.ctx.llm, rt.ctx.prompts, rt.catalog, rt.reflex)
        u = rt.utterances
        for instruction in (j.system_instruction, u.facts.system_instruction, u.verifier.system_instruction):
            assert ("Quote marks are often missing" in instruction) is on
    finally:
        await close_env(rt)


class _Record(ScriptedBackend):
    def __init__(self):
        super().__init__()
        self.messages: dict[str, str] = {}

    async def generate(self, req, timeout_ms):
        if req.agent == "compliance_judge":
            self.messages[req.mock_primary_text] = req.user_message
        return await super().generate(req, timeout_ms)


@pytest.mark.parametrize("window, sees_first", [(0, False), (20_000, True)])
async def test_d303_the_context_window(window, sees_first):
    from .helpers import live_runtime, make_ctx

    llm = _Record()
    rt = await live_runtime(make_ctx(backend=llm, CONTEXT_WINDOW_MS=window, UTTERANCE_MERGE_WINDOW_MS=0))
    try:
        lines = ["Someone in the chat asks.", "Whether the balm is waterproof.", "Good question, honestly.",
                 "It is not waterproof."]
        for line in lines:
            await speak(rt, line)
            await rt.ctx.scheduler.advance(1000)  # one second apart, all within the window
        await rt.utterances.drain()
        last = llm.messages[lines[-1]]
        assert ("Someone in the chat asks." in last) is sees_first
        assert "Good question, honestly." in last  # the last two are there either way
    finally:
        await close_env(rt)


@pytest.mark.parametrize("number_check, decision, alerts, heard_check", [
    (True, "check", 1, True),  # shown as "check what was said"
    (True, "keep", 1, False),
    (False, "keep", 1, False),
])
async def test_d303_number_check(number_check, decision, alerts, heard_check):
    from app.models.agent_io import VerifyOutput, VerifyOutputC

    from .helpers import live_runtime, make_ctx

    line, span = "It's only thirty-two dollars today.", "thirty-two dollars"
    llm = _RelationBackend("contradicts")
    llm.outputs[("verifier", f"{line}|{span}")] = {"evidence": None, "reason": "scripted", "decision": decision,
                                                   "severity": None}
    rt = await live_runtime(make_ctx(backend=llm, FACT_RELATION=True, JUDGE_ARM="verify", NUMBER_CHECK=number_check))
    try:
        assert rt.utterances.verifier.number_check is number_check
        await speak(rt, line)
        await rt.utterances.drain()
        facts = [a for a in await rt.alerts() if a.kind == "fact"]
        assert [a.heard_check for a in facts] == [heard_check] * alerts
    finally:
        await close_env(rt)
    assert VerifyOutputC.model_validate({"evidence": None, "reason": "r", "decision": "check", "severity": None})
    with pytest.raises(ValueError):
        VerifyOutput.model_validate({"evidence": None, "reason": "r", "decision": "check", "severity": None})
