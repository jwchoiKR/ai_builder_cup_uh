"""D-352: a correction (or a qualifier re-said) spoken before its alert turned active is no longer lost. Made-up lines;
the judges' verdicts are scripted, and the correcting line's verdict lists whatever alerts its input showed."""
from __future__ import annotations

import asyncio
import json
import re

from app.providers.llm import LLMError, RawReply

from .judge_fakes import ScriptedBackend, close_env, split_part, judge_output, violation

CLAIM = "Honestly this cream cures eczema."
SORRY = "Sorry guys, I shouldn't have said it cures eczema."


class _Backend(ScriptedBackend):
    """SORRY's compliance verdict corrects every alert in its ACTIVE_ALERTS (none when it has none)."""

    def __init__(self, fail_recheck: bool = False) -> None:
        super().__init__()
        self.fail_recheck = fail_recheck
        self.sorry_calls = 0

    async def generate(self, req, timeout_ms):
        if req.agent == "compliance_judge" and req.mock_primary_text == SORRY:
            self.sorry_calls += 1
            if self.fail_recheck and self.sorry_calls > 1:
                raise LLMError("scripted failure")
            block = re.search(r'<data name="ACTIVE_ALERTS">(.*?)</data>', req.user_message, re.S)
            ids = [a["alert_id"] for a in json.loads(block.group(1))] if block else []
            out = split_part("compliance_judge", judge_output(corrects=ids, utterance_type="correction"))
            return RawReply(json.dumps(out), model_version="scripted")
        return await super().generate(req, timeout_ms)


async def _run(backend, **settings):
    from .helpers import live_runtime, make_ctx

    backend.judge(CLAIM, violations=[violation("ASEAN-2D-DISEASE", "cures eczema")])
    backend.delays[("utterance_judge", CLAIM)] = 0.3  # the claim's verdict comes after the apology's
    rt = await live_runtime(make_ctx(backend=backend, CORRECTION_CHECK="judge", **settings))
    try:
        await rt.inject_transcript(CLAIM)
        await asyncio.sleep(0.05)
        await rt.inject_transcript(SORRY)
        await rt.utterances.drain()
        await rt.ctx.scheduler.idle()
        return [a for a in await rt.alerts() if a.kind == "compliance" and a.rule_id == "ASEAN-2D-DISEASE"], backend
    finally:
        await close_env(rt)


async def test_d352_a_line_judged_before_the_alert_existed_is_asked_once_more():
    alerts, llm = await _run(_Backend())  # the apology's verdict saw no alert at all
    assert [a.status for a in alerts] == ["corrected"] and llm.sorry_calls == 2


async def test_d352_a_failed_re_check_is_never_a_correction():
    alerts, llm = await _run(_Backend(fail_recheck=True))
    assert [a.status for a in alerts] == ["active"] and llm.sorry_calls == 2


class _HandleBackend(_Backend):
    """D-357, with CORRECTION_HANDLES: SORRY marks every alert it is shown (by handle) as fixed; its own verdict is
    slow, so it comes back after the claim's alert turned active."""

    async def generate(self, req, timeout_ms):
        if req.agent == "compliance_judge" and req.mock_primary_text == SORRY:
            self.sorry_calls += 1
            first = self.sorry_calls == 1
            if first:
                await asyncio.sleep(0.6)  # the line's own verdict lands after the alert is active
            block = re.search(r'<data name="ACTIVE_ALERTS">(.*?)</data>', req.user_message, re.S)
            shown = json.loads(block.group(1)) if block else []
            out = {"alert_checks": [{"handle": a["handle"], "fixed_by_this_line": True} for a in shown],
                   "compliance": {"violations": []}, "reason": "scripted"}
            return RawReply(json.dumps(out), model_version="scripted")
        return await super().generate(req, timeout_ms)


async def test_d357_the_re_check_fires_although_the_line_s_own_verdict_has_not_come_back(caplog):
    import logging

    with caplog.at_level(logging.INFO):
        alerts, llm = await _run(_HandleBackend(), CORRECTION_HANDLES=True)
    assert [a.status for a in alerts] == ["corrected"] and llm.sorry_calls == 2
    assert "re-check trigger" in caplog.text and "-> fired" in caplog.text
