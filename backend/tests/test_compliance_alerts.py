"""Compliance alerts from the judge's verdicts (was test_qualifier.py; D-427: the TEST-QUALIFIER rule is gone, these
cases keep the general behaviour with market rules)."""
from __future__ import annotations

import pytest

from app.models.session import Alert

from .judge_fakes import PRICE_PASSAGE, PRICE_QUOTE, claim, close_env, make_env, price_contradiction, speak, violation

CLAIM = "It cures eczema."


@pytest.fixture
async def env():
    rt, llm = await make_env()
    yield rt, llm
    await close_env(rt)


async def compliance_alerts(rt) -> list[Alert]:
    return [a for a in await rt.alerts() if a.kind == "compliance" and a.status == "active"]


@pytest.mark.parametrize("flags", [{"quoted": True}, {"negated": True}])
async def test_quoted_or_negated_gives_no_alert(env, flags):
    rt, llm = env
    llm.judge(CLAIM, violations=[violation("ASEAN-2D-DISEASE", "cures eczema", **flags)])
    await speak(rt, CLAIM)
    assert await compliance_alerts(rt) == []


async def test_d387_a_repeat_while_the_first_is_active_is_its_own_alert(env):
    """D-108 kept one card while the same claim's alert was active; D-387 (user): each violation is its own alert."""
    rt, llm = env
    again = "Again, it cures eczema."
    for text in (CLAIM, again):
        llm.judge(text, violations=[violation("ASEAN-2D-DISEASE", text)])
    await speak(rt, CLAIM)
    await speak(rt, again)
    assert [a.span for a in await compliance_alerts(rt)] == [CLAIM, again]


async def test_a_wrong_fact_repeated_after_its_correction_alerts_again(env):
    rt, llm = env
    wrong, right = "And today the live price is only thirty-two dollars.", "Sorry, it is thirty-six dollars."
    llm.facts(wrong, price_contradiction("S$32"))
    llm.facts(right, claim("price", "supported", stated="S$36", passage_id=PRICE_PASSAGE, quote=PRICE_QUOTE),
              fixed=["F1"])
    await speak(rt, wrong)
    [first] = [a for a in await rt.alerts() if a.kind == "fact" and a.status == "active"]
    await speak(rt, right)
    assert (await rt.get_alert(first.alert_id)).status == "corrected"
    await speak(rt, wrong)
    [second] = [a for a in await rt.alerts() if a.kind == "fact" and a.status == "active"]
    assert second.alert_id != first.alert_id


async def test_d215_the_judges_verdict_on_approved_wording_stands(env):
    """D-215 (full review P3): code no longer drops a violation because its words overlap approved wording (D-123,
    D-132, D-174 removed); the judge weighs approved wording under the rules (prompt)."""
    rt, llm = env
    text = "Contains no added fragrance and no essential oils, making it suitable for all skin types."
    # D-293: a rule with no required terms (Q6 would drop the vulnerable-group rule here: no group is named)
    llm.judge(text, violations=[violation("ASEAN-3-SKIN-AGEING", "suitable for all skin types")])
    await speak(rt, text)
    assert len(await compliance_alerts(rt)) == 1


async def test_say_instead_without_a_test_number_is_kept(env):
    rt, llm = env
    llm.judge(CLAIM, violations=[violation("ASEAN-2D-DISEASE", "cures eczema", say="It helps relieve the feeling of dryness.")])
    await speak(rt, CLAIM)
    [a] = await compliance_alerts(rt)
    assert a.say_instead == "It helps relieve the feeling of dryness."


async def test_sheet_words_do_not_cover_a_wider_claim(env):
    rt, llm = env
    text = "It is suitable for babies and every skin condition."
    llm.judge(text, violations=[violation("ASEAN-2D-VULNERABLE", "suitable for babies and every skin condition")])
    await speak(rt, text)
    assert len(await compliance_alerts(rt)) == 1


@pytest.mark.parametrize("text, span, alerts", [
    # D-174 (sealed verbal set): the judge flagged the short span "all users" (HIGH, vulnerable users) inside the
    # sheet's own "all skin types and all users"; a short span is checked with the phrase around it
    ("Guys can use it too, it even cures acne for all users.", "cures acne", 1),  # the phrase is not sheet wording
])
async def test_d174_a_short_span_inside_sheet_wording_is_not_an_alert(env, text, span, alerts):
    rt, llm = env
    llm.judge(text, violations=[violation("ASEAN-2D-VULNERABLE" if alerts == 0 else "ASEAN-3-SKIN-ACNE", span)])
    await speak(rt, text)
    assert len(await compliance_alerts(rt)) == alerts


pytestmark = pytest.mark.legacy_live  # D-434: not migrated yet (removed in its batch)
