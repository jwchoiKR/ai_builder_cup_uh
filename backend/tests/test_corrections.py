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
