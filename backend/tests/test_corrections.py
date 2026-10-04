"""Compliance corrections need correcting content, not just an apology (D-089)."""
from __future__ import annotations

import pytest

from app.logic.corrections import check_correction, content_words, coverage
from app.models.session import Alert

from .judge_fakes import advance, close_env, events, make_env, speak, violation

WRINKLES = "Use it every night and your wrinkles will disappear overnight."
SPAN = "your wrinkles will disappear overnight"
SAY = "With regular use, it helps keep your skin hydrated for up to 24 hours in our in-house test."
APPROVED = ["Helps keep skin hydrated for up to 24 hours.*", "Helps relieve the feeling of dryness."]


def alert(span=SPAN, say=SAY) -> Alert:
    return Alert(alert_id="al_1", kind="compliance", status="active", transcript_id="tr_1",
                 product_id="cream_hydra_barrier", rule_id="ASEAN-3-SKIN-AGEING", severity="HIGH", span=span,
                 say_instead=say, created_at=0, shown_at=0)


@pytest.fixture
def reflex():
    from app.config import get_settings
    from app.logic.catalog import DataPack
    from app.logic.reflex import Reflex

    return Reflex(DataPack.load(get_settings().data_path).rules)


def test_content_words_normalise_numbers_and_drop_fillers():
    assert content_words("Oh, I'm sorry. Let me correct that.") == []
    assert content_words("up to twenty-four hours") == ["24", "hour"]
    assert content_words("4% niacinamide") == ["4", "percent", "niacinamide"]
    assert coverage(["keep", "skin"], ["skin"]) == 0.5


@pytest.mark.parametrize("text, ok, reason", [
    ("Oh, I'm sorry.", False, "no_correcting_content"),
    ("Let me correct that.", False, "no_correcting_content"),
    ("Sorry, that's not true.", False, "no_correcting_content"),  # retracts nothing specific
    ("Sorry, it's a moisturiser.", False, "no_correcting_content"),
    # the approved claim, with spoken numbers and the in-house qualifier
    ("Let me correct that. It helps keep your skin hydrated for up to twenty-four hours in our in-house test.",
     True, "approved_statement"),
    # another approved claim, with a speech-to-text slip ("really" for "relieve")
    ("It helps really the feeling of dryness, I'm sorry.", True, "approved_statement"),
    # an explicit retraction of the flagged claim
    ("Sorry, your wrinkles won't disappear overnight.", True, "retraction"),
])
def test_check_correction(reflex, text, ok, reason):
    check = check_correction(text, alert(), APPROVED, reflex)
    assert (check.ok, check.reason) == (ok, reason)


PERMANENT = Alert(alert_id="al_2", kind="compliance", status="active", transcript_id="tr_1",
                  product_id="cream_hydra_barrier", rule_id="ASEAN-2E-PERMANENT", severity="HIGH",
                  span="your dry skin condition will be permanently fixed for good",
                  say_instead="Helps keep skin hydrated for up to 24 hours.", created_at=0, shown_at=0)


@pytest.mark.parametrize("text, ok", [
    # holdout S08: few span words, but the rule's own trigger phrase is negated (D-104)
    ("Let me correct my earlier statement, cosmetic results are not permanent, regular daily use is needed.", True),
    ("Let me correct that, it is permanent.", False),  # the trigger phrase, not negated
    ("Sorry, it does not cure eczema.", False),  # a negated phrase of another rule
])
def test_negated_trigger_phrase_of_the_alerts_rule_retracts(reflex, text, ok):
    assert check_correction(text, PERMANENT, APPROVED, reflex).ok is ok


@pytest.fixture
async def env():
    rt, llm = await make_env()
    yield rt, llm
    await close_env(rt)


async def test_apology_alone_keeps_the_alert_active_and_escalates(env):
    rt, llm = env
    llm.judge(WRINKLES, violations=[violation("ASEAN-3-SKIN-AGEING", SPAN)])
    await speak(rt, WRINKLES)
    [a] = await rt.alerts()
    await advance(rt, 1500)
    llm.judge("Oh, I'm sorry.", corrects=[a.alert_id], utterance_type="correction")
    await speak(rt, "Oh, I'm sorry.")
    assert (await rt.get_alert(a.alert_id)).status == "active"
    await advance(rt, 5000)
    assert (await rt.get_alert(a.alert_id)).escalated_at is not None
    assert len(await events(rt, "alert.escalated")) == 1


ACNE = "It stops your acne."
RELIEVE = "It helps relieve the feeling of dryness."


async def test_saying_the_replacement_corrects_even_if_the_judge_misses_it(env):
    """D-098, from the 2026-10-02 rehearsal: the host said the "Say this instead" wording a few lines
    after the alert; the judge called it product talk and listed no correction."""
    rt, llm = env
    llm.judge(ACNE, violations=[violation("ASEAN-3-SKIN-ACNE", "stops your acne", say=RELIEVE)])
    await speak(rt, ACNE)
    [a] = [x for x in await rt.alerts() if x.status == "active"]
    for line in ("Oh.", "Okay, one second."):
        await advance(rt, 4000)
        await speak(rt, line)
    await advance(rt, 4000)
    llm.judge(RELIEVE)  # no corrects_alert_ids
    t = await speak(rt, RELIEVE)
    a = await rt.get_alert(a.alert_id)
    assert a.status == "corrected" and a.corrected_by_transcript_id == t.transcript_id


async def test_replacement_wording_also_works_when_the_judge_fails(env):
    rt, llm = env
    llm.judge(ACNE, violations=[violation("ASEAN-3-SKIN-ACNE", "stops your acne", say=RELIEVE)])
    await speak(rt, ACNE)
    [a] = [x for x in await rt.alerts() if x.status == "active"]
    await advance(rt, 4000)
    llm.fail("utterance_judge", RELIEVE)
    await speak(rt, RELIEVE)
    assert (await rt.get_alert(a.alert_id)).status == "corrected"


async def test_other_talk_does_not_correct_without_the_judge(env):
    rt, llm = env
    llm.judge(ACNE, violations=[violation("ASEAN-3-SKIN-ACNE", "stops your acne", say=RELIEVE)])
    await speak(rt, ACNE)
    [a] = [x for x in await rt.alerts() if x.status == "active"]
    for line in ("Oh, I'm sorry.", "It is suitable for sensitive skin.", "Relieve it."):
        await advance(rt, 4000)
        await speak(rt, line)
    assert (await rt.get_alert(a.alert_id)).status == "active"


async def test_judge_input_lists_the_replacement_wording(env):
    from app.agents.inputs import active_alerts_json

    a = alert(say=RELIEVE)
    assert active_alerts_json([a]) == [{"alert_id": "al_1", "span": SPAN, "rule_id": "ASEAN-3-SKIN-AGEING",
                                        "say_instead": RELIEVE}]


async def test_real_correction_clears_the_alert(env):
    rt, llm = env
    llm.judge(WRINKLES, violations=[violation("ASEAN-3-SKIN-AGEING", SPAN)])
    await speak(rt, WRINKLES)
    [a] = await rt.alerts()
    await advance(rt, 1500)
    fix = "Let me correct that. It helps keep your skin hydrated for up to twenty-four hours in our in-house test."
    llm.judge(fix, corrects=[a.alert_id], utterance_type="correction")
    await speak(rt, fix)
    a = await rt.get_alert(a.alert_id)
    assert a.status == "corrected" and a.corrected_text == fix
