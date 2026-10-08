"""D-383 (user; 00010 show): one rule for the model (prompt v5): true if the line, in context, corrects or takes back
the alert's claim in any way, saying its say_instead included. Code only sends the alert's say_instead and applies the
model's handles. Mock: the verdicts are scripted."""
from __future__ import annotations

import pytest

from .judge_fakes import close_env, speak
from .test_d358 import CLAIM, _Backend, _show, _verdict

pytestmark = pytest.mark.originals

REPLACEMENT = "It supports normal joint comfort."  # the alert's say_instead, from _verdict


@pytest.mark.parametrize("line, fixed", [
    ("What I mean is, it supports your normal joint comfort.", True),  # the say_instead, in other words
    ("And the tub has sixty capsules.", False),  # an unrelated line
    ("It supports joint comfort and cures arthritis.", False),  # the say_instead with the violation again
])
async def test_d383_the_judge_sees_the_say_instead_and_its_verdict_is_applied(tmp_path, line, fixed):
    llm = _Backend()
    llm.outputs[("compliance_judge", CLAIM)] = _verdict(
        "kelmar_code.pdf#2.1", "must not be presented as treating, curing or preventing disease")
    llm.outputs[("compliance_judge", line)] = {
        "alert_checks": [{"handle": "A1", "fixed_by_this_line": fixed}], "compliance": {"violations": []},
        "reason": "scripted"}
    rt = await _show(tmp_path, llm)
    try:
        await speak(rt, CLAIM)
        [alert] = [a for a in await rt.alerts() if a.kind == "compliance"]
        assert alert.say_instead == REPLACEMENT
        await speak(rt, line)
        await rt.utterances.drain()
        req = [r for r in llm.requests if r.agent == "compliance_judge" and r.mock_primary_text == line][-1]
        assert req.prompt_version == "compliance_judge_v5"
        block = req.user_message.split('<data name="ACTIVE_ALERTS">')[1].split("</data>")[0]
        assert REPLACEMENT in block  # the model compares the line with what the screen told the host to say
        assert "corrects or takes back that alert's claim, in any way" in req.system_instruction
        assert (await rt.get_alert(alert.alert_id)).status == ("corrected" if fixed else "active")
    finally:
        await close_env(rt)
