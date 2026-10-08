"""D-387 (user: "위반은 각각 ID로 묶어서 처리"): each violation the model returns is its own alert, also two claims under
one section; only the same claim (same span) of one line is one alert. Fictional law pack; scripted verdicts."""
from __future__ import annotations

import pytest

from .judge_fakes import advance, close_env, speak
from .test_d358 import _Backend, _show, _verdict

pytestmark = pytest.mark.originals


async def test_d387_two_claims_under_one_section_are_two_alerts(tmp_path):
    llm = _Backend()
    first, second = "Honestly, this cures eczema.", "And it prevents diabetes too."
    llm.outputs[("compliance_judge", first)] = _verdict("kelmar_code.pdf#2.1", "must not be presented",
                                                        span="cures eczema")
    llm.outputs[("compliance_judge", second)] = _verdict("kelmar_code.pdf#2.1", "must not be presented",
                                                         span="prevents diabetes")
    rt = await _show(tmp_path, llm)
    try:
        await speak(rt, first)
        await speak(rt, second)
        alerts = [a for a in await rt.alerts() if a.kind == "compliance"]
        assert [(a.span, a.status) for a in alerts] == [("cures eczema", "active"), ("prevents diabetes", "active")]
        assert len({a.alert_id for a in alerts}) == 2 and {a.rule_id for a in alerts} == {"kelmar-code#2-1"}
    finally:
        await close_env(rt)


async def test_d387_one_verdict_with_two_claims_gives_two_alerts_and_a_repeated_span_one(tmp_path):
    llm = _Backend()
    line = "It cures eczema and prevents diabetes, it cures eczema."
    out = _verdict("kelmar_code.pdf#2.1", "must not be presented", span="cures eczema")
    v = out["compliance"]["violations"][0]
    out["compliance"]["violations"] = [v, {**v, "span": "prevents diabetes"}, {**v, "span": "Cures  eczema"}]
    llm.outputs[("compliance_judge", line)] = out
    rt = await _show(tmp_path, llm)
    try:
        await speak(rt, line)
        assert sorted(a.span for a in await rt.alerts() if a.kind == "compliance") == ["cures eczema",
                                                                                     "prevents diabetes"]
    finally:
        await close_env(rt)


async def test_d395_one_correction_clears_a_claim_said_four_times_and_leaves_another(tmp_path):
    """D-395: since D-387 a claim said in four lines is four alerts; every one gets a handle, so one correction line
    the model marks as fixing all four clears all four; an alert of a different claim stays."""
    llm = _Backend()
    other, claim_lines = "And it prevents diabetes.", [f"It cures eczema, line {i}." for i in range(4)]
    fix = "Sorry, it does not cure eczema; it soothes dry skin."
    llm.outputs[("compliance_judge", other)] = _verdict("kelmar_code.pdf#2.1", "q", span="prevents diabetes")
    for line in claim_lines:
        llm.outputs[("compliance_judge", line)] = _verdict("kelmar_code.pdf#2.1", "q", span=line)
    rt = await _show(tmp_path, llm)
    try:
        await speak(rt, other)
        for line in claim_lines:
            await advance(rt, 5000)  # 5 s apart: each its own alert, newest first in ACTIVE_ALERTS
            await speak(rt, line)
        # newest first: A1..A4 are the four eczema alerts, A5 the diabetes one
        llm.outputs[("compliance_judge", fix)] = {
            "alert_checks": [{"handle": f"A{i}", "fixed_by_this_line": i <= 4} for i in range(1, 6)],
            "compliance": {"violations": []}, "reason": "scripted"}
        await speak(rt, fix)
        await rt.utterances.drain()
        req = [r for r in llm.requests if r.agent == "compliance_judge" and r.mock_primary_text == fix][-1]
        assert '"handle":"A5"' in req.user_message.replace(" ", "") and '"product_id"' in req.user_message
        status = {a.span: a.status for a in await rt.alerts() if a.kind == "compliance"}
        assert [status[x] for x in claim_lines] == ["corrected"] * 4 and status["prevents diabetes"] == "active"
    finally:
        await close_env(rt)
