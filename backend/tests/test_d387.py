"""D-387 (user: "위반은 각각 ID로 묶어서 처리"): each violation the model returns is its own alert, also two claims under
one section; only the same claim (same span) of one line is one alert. Fictional law pack; scripted verdicts."""
from __future__ import annotations

import pytest

from .judge_fakes import close_env, speak
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
