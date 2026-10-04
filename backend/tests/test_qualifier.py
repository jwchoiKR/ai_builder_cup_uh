"""BRAND-TEST-QUALIFIER (D-105, PLANNING 5.1.3): test numbers need "in our in-house test"."""
from __future__ import annotations

import pytest

from app.logic import qualifier
from app.models.session import Alert

from .judge_fakes import AMPOULE, CREAM, claim, close_env, make_env, speak, violation

RULE = qualifier.RULE_ID
AM_45 = "In our in-house test, skin hydration went up 45% right after one use."
CR_0_32 = "In our in-house patch test, 0 of 32 participants had an irritation reaction."


@pytest.mark.parametrize("text, qualified", [
    ("In our in-house test, hydration went up forty-five percent.", True),
    ("In-house study results show plus thirty-eight percent.", True),
    ("In our forty-eight hour patch test, zero out of thirty-two participants reported irritation.", True),  # H032
    ("Hydration goes up forty-five percent right after one use.", False),
    ("Our customers love it, forty-five percent more hydration.", False),
    ("In clinical corneometer tests, instant skin hydration increased by seventy percent.", False),  # H052
])
def test_is_qualified(text, qualified):
    assert qualifier.is_qualified(text) is qualified


@pytest.mark.parametrize("on_air, text, say", [
    (AMPOULE, "You get an instant forty-five percent hydration boost immediately after just one use.", AM_45),  # H064
    (CREAM, "It underwent patch testing where zero out of thirty-two subjects had any adverse reaction.", CR_0_32),  # H059
    (CREAM, "Corneometer readings showed skin hydration jumped thirty-eight percent right after applying.",
     "In our in-house test, skin hydration went up 38% right after one application."),  # H053
    (CREAM, "It keeps your skin hydrated for twenty-four hours.",
     "It helps keep skin hydrated for up to 24 hours in our in-house test."),
    # H052: the number is wrong (70, sheet +45%); the words still point at the hydration result
    (AMPOULE, "In clinical corneometer tests, instant skin hydration increased by seventy percent right after one "
              "application.", AM_45),
    (CREAM, "And the ampoule gives forty-five percent more hydration right after one use.", AM_45),  # other product
    (CREAM, "Everyone is loving it tonight.", None),  # nothing matches: no wording is invented
])
def test_approved_replacement(catalog, on_air, text, say):
    others = [p for p in catalog.products if p.product_id != on_air]
    r = qualifier.approved_replacement(text, catalog.get_product(on_air), others)
    assert (r.say if r else None) == say


# ---- pipeline ------------------------------------------------------------------------------------

UNQUALIFIED = "Zero out of thirty-two people reacted in the patch test."


@pytest.fixture
async def env():
    rt, llm = await make_env()
    yield rt, llm
    await close_env(rt)


async def compliance_alerts(rt) -> list[Alert]:
    return [a for a in await rt.alerts() if a.kind == "compliance" and a.status == "active"]


async def test_unqualified_number_gets_medium_with_approved_wording(env):
    rt, llm = env
    llm.judge(UNQUALIFIED, violations=[violation(RULE, "Zero out of thirty-two", severity="HIGH",
                                                 say="Totally safe, nobody reacts.")])
    await speak(rt, UNQUALIFIED)
    [a] = await compliance_alerts(rt)
    assert (a.rule_id, a.severity, a.say_instead) == (RULE, "MEDIUM", CR_0_32)


async def test_qualified_sentence_never_gets_the_alert(env):
    rt, llm = env
    text = "In our forty-eight hour patch test, zero out of thirty-two participants reported irritation."
    llm.judge(text, violations=[violation(RULE, "zero out of thirty-two", severity="MEDIUM")])
    await speak(rt, text)
    assert await compliance_alerts(rt) == []


async def test_a_real_high_claim_in_the_same_sentence_stays_high(env):
    rt, llm = env
    text = "Zero out of thirty-two reacted and it erases your wrinkles."
    llm.judge(text, violations=[violation(RULE, "Zero out of thirty-two", severity="MEDIUM"),
                                violation("ASEAN-3-SKIN-AGEING", "erases your wrinkles")])
    await speak(rt, text)
    assert sorted((a.rule_id, a.severity) for a in await compliance_alerts(rt)) == [
        ("ASEAN-3-SKIN-AGEING", "HIGH"), (RULE, "MEDIUM")]


@pytest.mark.parametrize("flags", [{"quoted": True}, {"negated": True}])
async def test_quoted_or_negated_gives_no_alert(env, flags):
    rt, llm = env
    llm.judge(UNQUALIFIED, violations=[violation(RULE, "Zero out of thirty-two", severity="MEDIUM", **flags)])
    await speak(rt, UNQUALIFIED)
    assert await compliance_alerts(rt) == []


async def test_the_same_result_alerts_once_per_product_segment(env):
    rt, llm = env
    again = "Again, zero of thirty-two had a reaction."
    other = "It keeps your skin hydrated for twenty-four hours."
    for text in (UNQUALIFIED, again, other):
        llm.judge(text, violations=[violation(RULE, text, severity="MEDIUM")])
    await speak(rt, UNQUALIFIED)
    [first] = await compliance_alerts(rt)
    first.status = "corrected"  # even after a correction, the same result is not raised again
    await rt.save_alert(first)
    await speak(rt, again)
    await speak(rt, other)
    assert [a.say_instead for a in await compliance_alerts(rt)] == [
        "It helps keep skin hydrated for up to 24 hours in our in-house test."]


async def test_wrong_number_keeps_both_findings_on_one_sentence(env):
    """H052: the host card merges them by transcript (frontend); events and logs keep both."""
    rt, llm = env
    text = "In clinical corneometer tests, instant skin hydration increased by seventy percent right after one application."
    llm.judge(text, violations=[violation(RULE, "increased by seventy percent", severity="MEDIUM")])
    llm.facts(text, claim("test_result", "contradicted", product_id=CREAM, stated="+70%", correct="+38%",
                          passage_id=None, quote=None))
    t = await speak(rt, text)
    [a] = await compliance_alerts(rt)
    assert a.transcript_id == t.transcript_id and a.rule_id == RULE
    assert a.say_instead == "In our in-house test, skin hydration went up 38% right after one application."
