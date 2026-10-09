"""Fact correction notes (DEV_SPEC §8.5, §7.4 post-validation, §14.1 facts)."""
from __future__ import annotations

import pytest

from app.logic import facts as fact_logic
from app.models.agent_io import FactClaim
from app.models.session import Alert, Transcript
from app.pipelines import utterances as utt
from app.pipelines.runtime import ActionError

from .judge_fakes import (
    AMPOULE,
    CREAM,
    PRICE_PASSAGE,
    PRICE_QUOTE,
    PROMPTER_PRICE,
    PROMPTER_PRICE_TEXT,
    advance,
    claim,
    close_env,
    events,
    make_env,
    price_contradiction,
    speak,
)


WRONG = "And today the live price is only thirty-two dollars."
WRONGER = "Actually it's thirty dollars live."
RIGHT = "Sorry, my mistake, the live price is thirty-six dollars."


@pytest.fixture
async def env():
    rt, llm = await make_env()
    yield rt, llm
    await close_env(rt)


async def fact_alerts(rt) -> list[Alert]:
    return [a for a in await rt.alerts() if a.kind == "fact"]


async def test_contradiction_creates_active_note(env):
    rt, llm = env
    llm.facts(WRONG, price_contradiction("S$32"))
    t = await speak(rt, WRONG)
    [a] = await fact_alerts(rt)
    assert a.alert_id.startswith("fx_") and a.status == "active" and a.transcript_id == t.transcript_id
    assert (a.field, a.stated_value, a.correct_value) == ("price", "S$32", "S$36.00")
    assert (a.passage_id, a.quote, a.product_id) == (PROMPTER_PRICE, PROMPTER_PRICE_TEXT, CREAM)  # D-360
    assert a.shown_at is not None
    [created] = [e for e in await events(rt, "alert.created") if e.payload["kind"] == "fact"]
    assert created.payload["alert_id"] == a.alert_id


async def test_promo_price_contradiction_cites_the_prompter_s_sale_price(env):
    rt, llm = env
    await rt.start_promo("promo_time_sale_10")
    text = "With the time sale it's thirty dollars now."
    llm.facts(text, claim("promo", "contradicted", stated="S$30", correct="S$32.40"))
    await speak(rt, text)
    [a] = await fact_alerts(rt)
    # D-361/D-423: the running time sale's price is a prompter item, so the note cites it
    assert a.correct_value == "S$32.40" and a.passage_id == "DL-CR-01#prompter#sale-price-promo_time_sale_10"


async def test_d398_each_wrong_claim_is_its_own_note(env):
    rt, llm = env
    llm.facts(WRONG, price_contradiction("S$32"))
    llm.facts(WRONGER, price_contradiction("S$30"))
    await speak(rt, WRONG)
    first = (await fact_alerts(rt))[0]
    await advance(rt, 3000)
    t2 = await speak(rt, WRONGER)
    notes = await fact_alerts(rt)  # D-398: one note per claim, no re-show of the first
    assert [(a.stated_value, a.transcript_id) for a in notes] == [("S$32", first.transcript_id),
                                                                  ("S$30", t2.transcript_id)]


async def test_other_product_gets_its_own_note(env):
    rt, llm = env
    text = "The ampoule has ten percent niacinamide and the cream is thirty-two dollars."
    llm.facts(text, price_contradiction("S$32"),
              claim("ingredient_amount", "contradicted", product_id=AMPOULE, stated="10% niacinamide",
                    correct="4% niacinamide", passage_id="DL-AM-01#key-ingredients#niacinamide", quote="Niacinamide: 4%"))
    await speak(rt, text)
    notes = await fact_alerts(rt)
    assert {(a.product_id, a.field) for a in notes} == {(CREAM, "price"), (AMPOULE, "ingredient_amount")}


async def test_supported_claim_corrects_the_note(env):
    rt, llm = env
    llm.facts(WRONG, price_contradiction())
    llm.facts(RIGHT, claim("price", "supported", stated="S$36", passage_id=PRICE_PASSAGE, quote=PRICE_QUOTE),
              fixed=["F1"])  # D-363: the model marks the note fixed by its handle
    await speak(rt, WRONG)
    await advance(rt, 4000)
    t = await speak(rt, RIGHT)
    [a] = await fact_alerts(rt)
    assert a.status == "corrected" and a.resolved_at == a.shown_at + 4000
    assert a.corrected_by_transcript_id == t.transcript_id and a.corrected_text == RIGHT


async def test_supported_other_field_does_not_correct(env):
    rt, llm = env
    llm.facts(WRONG, price_contradiction())
    llm.facts("It's 50 mL.", claim("volume", "supported", stated="50 mL"))
    await speak(rt, WRONG)
    await speak(rt, "It's 50 mL.")
    assert (await fact_alerts(rt))[0].status == "active"


async def test_d402_a_note_stays_until_closed_and_resend_makes_it_newest(env):
    rt, llm = env
    llm.facts(WRONG, price_contradiction())
    await speak(rt, WRONG)
    [a] = await fact_alerts(rt)
    await advance(rt, 600_000)  # D-402: no host-hide timer: ten minutes later it is still on the host
    assert (await fact_alerts(rt))[0].status == "active"
    await utt.resend_fact(rt, rt.utterances, a.alert_id)
    resent = (await fact_alerts(rt))[0]
    assert resent.status == "active" and resent.shown_at == a.shown_at + 600_000


async def test_resend_only_active_fact_notes(env):
    rt, llm = env
    llm.facts(WRONG, price_contradiction())
    llm.facts(RIGHT, claim("price", "supported", passage_id=PRICE_PASSAGE, quote=PRICE_QUOTE), fixed=["F1"])
    await speak(rt, WRONG)
    await speak(rt, RIGHT)
    [a] = await fact_alerts(rt)
    with pytest.raises(ActionError) as e:
        await utt.resend_fact(rt, rt.utterances, a.alert_id)
    assert e.value.status == 409


async def test_fact_cue_and_notice_template(env):
    rt, llm = env
    llm.facts(WRONG, price_contradiction())
    await speak(rt, WRONG)
    [a] = await fact_alerts(rt)
    cue = await utt.correction_cue(rt, a.alert_id)
    assert cue.text == "Say: S$36.00" and (await rt.load_session()).cue.cue_id == cue.cue_id
    assert utt.notice_template(rt, a) == "Correction: the current price of Hydra Barrier Cream is S$36.00."
    msg = await utt.post_notice(rt, a.alert_id, utt.notice_template(rt, a))
    assert msg.kind == "correction_notice" and msg.state == "published"


# ---- pure function ------------------------------------------------------------------------------


def test_apply_fact_check_pure(ids):
    t = Transcript(transcript_id="tr_1", text="x", is_final=True, speech_end_at=0, received_at=0, source="injected",
                   segment_id="seg_1")
    new_id = lambda p: ids.new(p, "s")  # noqa: E731
    c = FactClaim.model_validate(price_contradiction("S$32"))
    alerts = fact_logic.apply_fact_check([c], t, new_id, now=100)
    assert len(alerts) == 1
    c2 = FactClaim.model_validate(price_contradiction("S$31"))  # D-398: its own note, not a re-show
    assert [a.stated_value for a in fact_logic.apply_fact_check([c2], t, new_id, now=200)] == ["S$31"]
    # D-363: a supported claim corrects nothing by itself; the model's handle (mapped to the id) does
    sup = FactClaim.model_validate(claim("price", "supported", passage_id=PRICE_PASSAGE, quote=PRICE_QUOTE))
    assert fact_logic.apply_fact_check([sup], t, new_id, now=300) == []
    corrected = fact_logic.correct_notes({alerts[0].alert_id}, alerts, t, now=300)
    assert corrected and corrected[0].status == "corrected" and corrected[0].resolved_at == 300
    assert fact_logic.PURCHASE_FIELDS >= {"price", "volume", "ingredient_amount"}


# ---- D-100: no fact note on compliance wording ---------------------------------------------------

TEST_PASSAGE = "DL-AM-01#in-house-test-results#participants-who-said-skin-looked-more-radiant-after-4-weeks"


def weeks(field: str = "test_result") -> dict:
    return claim(field, "contradicted", product_id=AMPOULE, stated="2 weeks", correct="4 weeks",
                 passage_id=TEST_PASSAGE, quote="after 4 weeks")


# ---- set offers (holdout H046) -------------------------------------------------------------------

SET = "set_cream_ampoule"
H046 = "The time sale price for the two-piece set is fifty dollars flat."


async def test_set_promo_price_contradiction_names_the_set(env):
    """The model names the set offer, which is not a product; the note must still stand."""
    rt, llm = env
    await rt.start_promo("promo_time_sale_10")
    llm.facts(H046, claim("promo", "contradicted", product_id=SET, stated="S$50", correct="S$55.80"))
    await speak(rt, H046)
    [a] = await fact_alerts(rt)
    assert (a.product_id, a.correct_value) == (SET, "S$55.80")
    assert utt.notice_template(rt, a).startswith("Correction: the current price of ")
    assert "S$55.80" in utt.notice_template(rt, a)


# ---- review B3: one note per subject (ingredient, test, offer), not per field ---------------------

PANTHENOL = "DL-CR-01#key-ingredients#panthenol"
SQUALANE = "DL-CR-01#key-ingredients#squalane"


async def test_a_right_fact_about_another_ingredient_does_not_clear_the_note(env):
    rt, llm = env
    wrong = "It has ten percent panthenol."
    llm.facts(wrong, claim("ingredient_amount", "contradicted", stated="10%", correct="5%", passage_id=PANTHENOL,
                           quote="Panthenol: 5%"))
    await speak(rt, wrong)
    [note] = await fact_alerts(rt)
    other = "And squalane is three percent."
    llm.facts(other, claim("ingredient_amount", "supported", stated="3%", passage_id=SQUALANE))
    await speak(rt, other)
    assert (await rt.get_alert(note.alert_id)).status == "active"
    second = "Squalane is ten percent."
    llm.facts(second, claim("ingredient_amount", "contradicted", stated="10%", correct="3%", passage_id=SQUALANE,
                            quote="Squalane: 3%"))
    await speak(rt, second)
    assert len([a for a in await fact_alerts(rt) if a.status == "active"]) == 2  # two subjects, two notes
    fix = "Sorry, panthenol is five percent."
    # D-362: the model's verdict names the note (its cited passage); no number parsed from the line
    llm.facts(fix, claim("ingredient_amount", "supported", stated="5%", passage_id=PANTHENOL), fixed=["F1"])
    await speak(rt, fix)
    assert (await rt.get_alert(note.alert_id)).status == "corrected"


# ---- D-121: an ingredient the product does not contain; pH ----------------------------------------

ABSENT = "not in this product"


def _full_list():
    from app.models.data import Passage

    return Passage(passage_id="DL-CR-01#ingredients#all", product_id=CREAM, doc="sheet", section="Ingredients",
                   text="Water, glycerin, panthenol, ceramide NP, squalane.", score=0.0)
