"""BRAND-TEST-QUALIFIER (D-105, PLANNING 5.1.3): test numbers need "in our in-house test"."""
from __future__ import annotations

import pytest

from app.logic import qualifier
from app.models.session import Alert

from .judge_fakes import AMPOULE, CREAM, claim, close_env, make_env, price_contradiction, speak, violation

from app.config import get_settings as _settings  # noqa: E402
from app.logic.catalog import DataPack as _DataPack  # noqa: E402

LEX = _DataPack.load(_settings().data_path).lexicon  # D-134: English (SG) lexicon


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
    assert LEX.is_qualified(text) is qualified


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
    r = qualifier.approved_replacement(text, catalog.get_product(on_air), others, catalog.lexicon)
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


async def test_no_second_card_while_active_but_a_repeat_after_correction_alerts_again(env):
    """D-108 (user: always alert again): wrong -> correct -> wrong again shows a second alert."""
    rt, llm = env
    again = "Again, zero of thirty-two had a reaction."
    fixed = "In our in-house patch test, 0 of 32 participants had an irritation reaction."
    for text in (UNQUALIFIED, again):
        llm.judge(text, violations=[violation(RULE, text, severity="MEDIUM")])
    await speak(rt, UNQUALIFIED)
    [first] = await compliance_alerts(rt)
    await speak(rt, again)  # still active: no double card
    assert [a.alert_id for a in await compliance_alerts(rt)] == [first.alert_id]
    await speak(rt, fixed)  # says the approved wording: corrected (D-098)
    assert (await rt.get_alert(first.alert_id)).status == "corrected"
    await speak(rt, again)
    [second] = await compliance_alerts(rt)
    assert second.alert_id != first.alert_id and second.say_instead == CR_0_32


async def test_a_wrong_fact_repeated_after_its_correction_alerts_again(env):
    rt, llm = env
    wrong, right = "And today the live price is only thirty-two dollars.", "Sorry, it is thirty-six dollars."
    llm.facts(wrong, price_contradiction("S$32"))
    llm.facts(right, claim("price", "supported", stated="S$36"))
    await speak(rt, wrong)
    [first] = [a for a in await rt.alerts() if a.kind == "fact" and a.status == "active"]
    await speak(rt, right)
    assert (await rt.get_alert(first.alert_id)).status == "corrected"
    await speak(rt, wrong)
    [second] = [a for a in await rt.alerts() if a.kind == "fact" and a.status == "active"]
    assert second.alert_id != first.alert_id


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


@pytest.mark.parametrize("text", [
    "The cream has five percent panthenol.",  # an ingredient amount
    "The live price is thirty-six dollars.",  # a price
    "It's a fifty mL jar.",  # a volume
])
async def test_ingredient_amounts_prices_and_volumes_never_get_the_test_qualifier(env, text):
    """D-116 (holdout HV16): only in-house test or study results need the qualifier. A verdict whose
    sentence matches none of the product's in-house results is dropped."""
    rt, llm = env
    llm.judge(text, violations=[violation(RULE, text, severity="MEDIUM")])
    await speak(rt, text)
    assert await compliance_alerts(rt) == []


async def test_approved_wording_is_never_a_red_alert(env):
    """D-123 (adversarial AV037): the judge flagged ASEAN-3-SKIN-ACNE with the span of an approved,
    in-house result. A violation whose span is approved product wording is dropped (the qualifier rule
    still applies to an unqualified number)."""
    rt, llm = env
    text = "29 of 32 participants said their skin felt less dry after 2 weeks."
    llm.judge(text, violations=[violation("ASEAN-3-SKIN-ACNE", "29 of 32 participants said their skin felt less dry "
                                          "after 2 weeks")])
    await speak(rt, text)
    assert await compliance_alerts(rt) == []


async def test_say_instead_with_a_test_number_carries_the_qualifier(env):
    """D-131 (holdout H090): the judge copied the approved claim without its '*'. The host is told to say
    the qualified line, so saying it word for word never raises the test-qualifier alert."""
    rt, llm = env
    text = "Your wrinkles will completely disappear."
    llm.judge(text, violations=[violation("ASEAN-3-SKIN-AGEING", "wrinkles will completely disappear",
                                          say="It helps keep skin hydrated for up to 24 hours.")])
    await speak(rt, text)
    [a] = await compliance_alerts(rt)
    assert a.say_instead == "It helps keep skin hydrated for up to 24 hours in our in-house test."
    assert LEX.is_qualified(a.say_instead)


async def test_say_instead_without_a_test_number_is_kept(env):
    rt, llm = env
    text = "It cures eczema."
    llm.judge(text, violations=[violation("ASEAN-2D-DISEASE", "cures eczema", say="It helps relieve the feeling of dryness.")])
    await speak(rt, text)
    [a] = await compliance_alerts(rt)
    assert a.say_instead == "It helps relieve the feeling of dryness."


async def test_a_statement_of_the_product_sheet_is_never_an_alert(env):
    """D-132 (sealed AW010): "suitable for all skin types" is in the cream's sheet (Key facts, FAQ);
    the judge flagged it once HIGH (vulnerable users) and twice MEDIUM (superlative)."""
    rt, llm = env
    text = "Contains no added fragrance and no essential oils, making it suitable for all skin types."
    llm.judge(text, violations=[violation("ASEAN-2D-VULNERABLE", "suitable for all skin types"),
                                violation("BRAND-SUPERLATIVE", "it is suitable for all skin types", severity="MEDIUM")])
    await speak(rt, text)
    assert await compliance_alerts(rt) == []


async def test_sheet_words_do_not_cover_a_wider_claim(env):
    rt, llm = env
    text = "It is suitable for babies and every skin condition."
    llm.judge(text, violations=[violation("ASEAN-2D-VULNERABLE", "suitable for babies and every skin condition")])
    await speak(rt, text)
    assert len(await compliance_alerts(rt)) == 1


def test_not_approved_claims_of_the_sheet_never_count_as_approved(catalog, pack):
    from app.agents.utterance_judge import _is_approved_wording

    cream = catalog.get_product(CREAM)
    passages = [p for p in pack.passages if p.product_id == CREAM]
    lex = catalog.lexicon
    assert not _is_approved_wording("the best moisturiser in Singapore", cream, lex, passages)
    assert not _is_approved_wording("removes wrinkles or reverses skin ageing", cream, lex, passages)
    assert _is_approved_wording("suitable for all skin types", cream, lex, passages)


async def test_a_lead_in_final_naming_our_test_qualifies_the_next_one(env):
    """D-146 (sealed show replay): "In our in-house test," came as its own final before the number."""
    rt, llm = env
    await speak(rt, "In our in-house test.")  # a full stop: not merged (D-088), the lead-in rule applies
    text = "skin hydration went up thirty-eight percent right after one application."
    llm.judge(text, violations=[violation(RULE, text, severity="MEDIUM")])
    await speak(rt, text)
    assert await compliance_alerts(rt) == []


async def test_a_lead_in_with_its_own_number_does_not_qualify_the_next_line(env):
    rt, llm = env
    await speak(rt, "In our in-house test 29 of 32 people loved it.")
    text = "And hydration goes up 38% right after you put it on."
    llm.judge(text, violations=[violation(RULE, text, severity="MEDIUM")])
    await speak(rt, text)
    assert len(await compliance_alerts(rt)) == 1


@pytest.mark.parametrize("text, alerts", [
    ("Acne, um, no no,", 0),  # D-148: a topic word and fillers is not a claim
    ("It cures acne.", 1),  # a short real claim still alerts
])
async def test_a_topic_word_alone_is_not_a_claim(env, text, alerts):
    rt, llm = env
    llm.judge(text, violations=[violation("ASEAN-3-SKIN-ACNE", "acne" if alerts == 0 else "cures acne")])
    await speak(rt, text)
    assert len(await compliance_alerts(rt)) == alerts


async def test_a_qualifier_added_in_the_next_final_corrects_the_alert(env):
    """D-151 (sealed round 3): the number, then "That's from our in-house test." as its own final; the judge
    listed no correction."""
    rt, llm = env
    text = "Redness went down 30% after two weeks."
    llm.judge(text, violations=[violation(RULE, text, severity="MEDIUM")])
    await speak(rt, text)
    [a] = await compliance_alerts(rt)
    await speak(rt, "That's from our in-house test.")
    assert await compliance_alerts(rt) == []
    assert (await rt.ctx.store.get(rt.path("alerts"), a.alert_id, Alert)).status == "corrected"


async def test_a_qualifier_add_on_judged_first_prevents_the_alert(env):
    """D-151: the add-on's judgment finished before the number's, so no alert existed yet to correct."""
    import asyncio

    rt, llm = env
    text = "Redness went down 30% after two weeks."
    llm.judge(text, violations=[violation(RULE, text, severity="MEDIUM")])
    llm.delays[("utterance_judge", text)] = 0.3  # the number's judgment arrives last
    await speak(rt, text, wait=False)
    await speak(rt, "That's from our in-house test.", wait=False)
    await rt.utterances.drain()
    await asyncio.sleep(0.4)
    await rt.ctx.scheduler.idle()
    assert await compliance_alerts(rt) == []


async def test_an_add_on_with_its_own_number_is_not_a_late_qualifier(env):
    rt, llm = env
    text = "Redness went down 30% after two weeks."
    llm.judge(text, violations=[violation(RULE, text, severity="MEDIUM")])
    await speak(rt, text)
    await speak(rt, "In our in-house test 29 of 32 people loved it.")
    assert len(await compliance_alerts(rt)) == 1
