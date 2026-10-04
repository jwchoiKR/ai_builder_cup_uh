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
    advance,
    claim,
    close_env,
    events,
    make_env,
    price_contradiction,
    speak,
)

from app.config import get_settings as _settings  # noqa: E402
from app.logic.catalog import DataPack as _DataPack  # noqa: E402

LEX = _DataPack.load(_settings().data_path).lexicon  # D-134: English (SG) lexicon


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
    assert (a.passage_id, a.quote, a.product_id) == (PRICE_PASSAGE, PRICE_QUOTE, CREAM)
    assert a.shown_at is not None and a.host_hidden_at is None
    [created] = [e for e in await events(rt, "alert.created") if e.payload["kind"] == "fact"]
    assert created.payload["alert_id"] == a.alert_id


@pytest.mark.parametrize("bad", [
    claim("price", "contradicted", stated="S$32", correct="S$40.00", passage_id=PRICE_PASSAGE, quote=PRICE_QUOTE),
    claim("price", "contradicted", stated="S$32", correct="S$36.00", passage_id=PRICE_PASSAGE, quote="Live price: S$36.00"),
    claim("price", "contradicted", stated="S$32", correct="S$36.00", passage_id="NOPE", quote=PRICE_QUOTE),
    claim("price", "contradicted", stated="S$32", correct="S$36.00", passage_id=None, quote=None),  # no promo active
    claim("other", "contradicted", stated="treats acne", correct="Claims not approved: Treats acne",
          passage_id="DL-CR-01#approved-on-air-claims#not-approved", quote="Claims not approved:"),
    claim("price", "contradicted", product_id="nope", stated="S$32", correct="S$36.00", passage_id=PRICE_PASSAGE,
          quote=PRICE_QUOTE),
])
async def test_unbacked_contradiction_is_downgraded(env, bad):
    rt, llm = env
    llm.facts(WRONG, bad)
    await speak(rt, WRONG)
    assert await fact_alerts(rt) == []


async def test_promo_price_contradiction_without_passage(env):
    rt, llm = env
    await rt.start_promo("promo_time_sale_10")
    text = "With the time sale it's thirty dollars now."
    llm.facts(text, claim("promo", "contradicted", stated="S$30", correct="S$32.40"))
    await speak(rt, text)
    [a] = await fact_alerts(rt)
    assert a.correct_value == "S$32.40" and a.passage_id is None


async def test_same_product_and_field_is_reshown_not_duplicated(env):
    rt, llm = env
    llm.facts(WRONG, price_contradiction("S$32"))
    llm.facts(WRONGER, price_contradiction("S$30"))
    await speak(rt, WRONG)
    first = (await fact_alerts(rt))[0]
    await advance(rt, 3000)
    t2 = await speak(rt, WRONGER)
    [a] = await fact_alerts(rt)
    assert a.alert_id == first.alert_id and a.stated_value == "S$30" and a.shown_at == first.shown_at + 3000
    assert a.transcript_id == t2.transcript_id
    assert any(e.payload["alert_id"] == a.alert_id for e in await events(rt, "alert.updated"))


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
    llm.facts(RIGHT, claim("price", "supported", stated="S$36"))
    await speak(rt, WRONG)
    await advance(rt, 4000)
    t = await speak(rt, RIGHT)
    [a] = await fact_alerts(rt)
    assert a.status == "corrected" and a.resolved_at == a.shown_at + 4000
    assert a.corrected_by_transcript_id == t.transcript_id and a.corrected_text == RIGHT
    await advance(rt, 60_000)
    assert (await fact_alerts(rt))[0].host_hidden_at is None  # no hide after correction


async def test_supported_other_field_does_not_correct(env):
    rt, llm = env
    llm.facts(WRONG, price_contradiction())
    llm.facts("It's 50 mL.", claim("volume", "supported", stated="50 mL"))
    await speak(rt, WRONG)
    await speak(rt, "It's 50 mL.")
    assert (await fact_alerts(rt))[0].status == "active"


async def test_host_hide_after_max_seconds_and_resend(env):
    rt, llm = env
    llm.facts(WRONG, price_contradiction())
    await speak(rt, WRONG)
    [a] = await fact_alerts(rt)
    await advance(rt, 44_999)
    assert (await fact_alerts(rt))[0].host_hidden_at is None
    await advance(rt, 1)
    a = (await fact_alerts(rt))[0]
    assert a.status == "active" and a.host_hidden_at == a.shown_at + 45_000  # operator keeps it
    await utt.resend_fact(rt, rt.utterances, a.alert_id)
    resent = (await fact_alerts(rt))[0]
    assert resent.host_hidden_at is None and resent.status == "active"
    await advance(rt, 44_000)
    assert (await fact_alerts(rt))[0].host_hidden_at is None  # timer restarted
    await advance(rt, 1_000)
    assert (await fact_alerts(rt))[0].host_hidden_at is not None


async def test_resend_only_active_fact_notes(env):
    rt, llm = env
    llm.facts(WRONG, price_contradiction())
    llm.facts(RIGHT, claim("price", "supported"))
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
    created, reshown, corrected = fact_logic.apply_fact_check([c], [], t, new_id, now=100, lex=LEX)
    assert len(created) == 1 and not reshown and not corrected
    alerts = created
    c2 = FactClaim.model_validate(price_contradiction("S$31"))
    created, reshown, corrected = fact_logic.apply_fact_check([c2], alerts, t, new_id, now=200, lex=LEX)
    assert not created and reshown[0].stated_value == "S$31" and reshown[0].shown_at == 200
    sup = FactClaim.model_validate(claim("price", "supported"))
    created, reshown, corrected = fact_logic.apply_fact_check([sup], alerts, t, new_id, now=300, lex=LEX)
    assert corrected and corrected[0].status == "corrected" and corrected[0].resolved_at == 300
    assert fact_logic.PURCHASE_FIELDS >= {"price", "volume", "ingredient_amount"}


# ---- D-100: no fact note on compliance wording ---------------------------------------------------

TEST_PASSAGE = "DL-AM-01#in-house-test-results#participants-who-said-skin-looked-more-radiant-after-4-weeks"


def verdicts(pack, catalog, text: str, *claims: dict) -> list[str]:
    from app.agents.fact_checker import post_validate
    from app.models.agent_io import FactCheckOutput

    out = FactCheckOutput.model_validate({"claims": list(claims), "reason": "scripted"})
    passages = [p for p in pack.passages if p.passage_id == TEST_PASSAGE]
    return [c.verdict for c in post_validate(out, passages, catalog, None, text).claims]


def weeks(field: str = "test_result") -> dict:
    return claim(field, "contradicted", product_id=AMPOULE, stated="2 weeks", correct="4 weeks",
                 passage_id=TEST_PASSAGE, quote="after 4 weeks")


@pytest.mark.parametrize("text, verdict", [
    ("It whitens your skin in two weeks.", "not_in_sources"),  # benefit timing: the compliance judge's job
    ("In our test, skin looked more radiant after two weeks.", "contradicted"),
    ("Eighty-seven percent saw more radiant skin in two weeks.", "contradicted"),
    ("Twenty-six of thirty participants saw it in two weeks.", "contradicted"),
])
def test_test_result_is_checked_only_when_a_test_is_cited(pack, catalog, text, verdict):
    assert verdicts(pack, catalog, text, weeks()) == [verdict]


def test_other_field_never_gives_a_note(pack, catalog):
    """"prescription cream" -> "cosmetic product" has no value to compare; the quote alone is not enough."""
    assert verdicts(pack, catalog, "In our test it worked in two weeks.", weeks("other")) == ["not_in_sources"]


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


@pytest.mark.parametrize("bad", [
    claim("promo", "contradicted", product_id=SET, stated="S$50", correct="S$50.00"),  # not the set's promo price
    claim("promo", "contradicted", product_id=CREAM, stated="S$50", correct="S$55.80"),  # set price on the cream
    claim("volume", "contradicted", product_id=SET, stated="2 pieces", correct="3 pieces"),  # sets have only prices
])
async def test_set_claims_that_stay_downgraded(env, bad):
    rt, llm = env
    await rt.start_promo("promo_time_sale_10")
    llm.facts(H046, bad)
    await speak(rt, H046)
    assert await fact_alerts(rt) == []


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
    llm.facts(fix, claim("ingredient_amount", "supported", stated="5%"))  # no passage: matched by the value
    await speak(rt, fix)
    assert (await rt.get_alert(note.alert_id)).status == "corrected"


# ---- D-121: an ingredient the product does not contain; pH ----------------------------------------

ABSENT = "not in this product"


@pytest.mark.parametrize("stated, verdict", [
    ("4% niacinamide", "contradicted"),  # the cream's sheet never names niacinamide
    ("5% panthenol", "not_in_sources"),  # it does contain panthenol: absence is not accepted
])
def test_an_absent_ingredient_is_contradicted_only_when_the_sheet_never_names_it(pack, catalog, stated, verdict):
    from app.agents.fact_checker import post_validate
    from app.models.agent_io import FactCheckOutput

    c = claim("ingredient", "contradicted", stated=stated, correct=ABSENT)
    out = FactCheckOutput.model_validate({"claims": [c], "reason": "scripted"})
    sheet = [p for p in pack.passages if p.product_id == CREAM]
    assert [x.verdict for x in post_validate(out, sheet, catalog, None, f"It has {stated}.").claims] == [verdict]


def test_a_wrong_ph_is_a_fact_note(pack, catalog):
    from app.agents.fact_checker import post_validate
    from app.models.agent_io import FactCheckOutput

    c = claim("ph", "contradicted", stated="pH 6.8", correct="5.5 (plus or minus 0.5)",
              passage_id="DL-CR-01#key-facts#ph", quote="pH: 5.5 (plus or minus 0.5)")
    out = FactCheckOutput.model_validate({"claims": [c], "reason": "scripted"})
    sheet = [p for p in pack.passages if p.product_id == CREAM]
    assert [x.verdict for x in post_validate(out, sheet, catalog, None, "It has a pH of 6.8.").claims] == ["contradicted"]


def test_a_less_specific_container_is_not_contradicted(pack, catalog):
    """D-123 (adversarial AV117): "a 50 mL tube" is consistent with "Airless pump tube"."""
    from app.agents.fact_checker import post_validate
    from app.models.agent_io import FactCheckOutput

    sheet = [p for p in pack.passages if p.product_id == CREAM]
    for stated, verdict in [("50 mL tube", "not_in_sources"), ("jar", "contradicted")]:
        c = claim("packaging", "contradicted", stated=stated, correct="Airless pump tube",
                  passage_id="DL-CR-01#key-facts#packaging", quote="Packaging: Airless pump tube")
        out = FactCheckOutput.model_validate({"claims": [c], "reason": "scripted"})
        assert [x.verdict for x in post_validate(out, sheet, catalog, None, f"It is a {stated}.").claims] == [verdict]


def test_d148_a_wrong_promo_discount_is_a_checked_fact(catalog, pack):
    """D-148 (sealed show replay): "It's an extra 20% off" during the 10% time sale got no note: code only
    accepted promo prices as right values."""
    from app.agents.fact_checker import post_validate
    from app.models.agent_io import FactCheckOutput

    promo = pack.promos_by_id["promo_time_sale_10"]
    claim = {"span": "an extra 20% off", "field": "promo", "product_id": "cream_hydra_barrier", "stated_value": "20% off",
             "verdict": "contradicted", "correct_value": "10% off", "passage_id": None, "quote": None}
    out = FactCheckOutput.model_validate({"claims": [claim], "reason": "t"})
    [c] = post_validate(out, [], catalog, promo).claims
    assert c.verdict == "contradicted"
    made_up = FactCheckOutput.model_validate({"claims": [claim | {"correct_value": "15% off"}], "reason": "t"})
    assert post_validate(made_up, [], catalog, promo).claims[0].verdict == "not_in_sources"


def test_d148_the_live_price_said_as_now_during_a_sale_is_stale(catalog, pack):
    from app.agents.fact_checker import post_validate
    from app.models.agent_io import FactCheckOutput

    promo = pack.promos_by_id["promo_time_sale_10"]
    claim = {"span": "thirty-six dollars", "field": "price", "product_id": "cream_hydra_barrier", "stated_value": "S$36",
             "verdict": "supported", "correct_value": None, "passage_id": "DL-CR-01#key-facts#live-broadcast-price",
             "quote": "Live broadcast price: S$36.00"}
    out = FactCheckOutput.model_validate({"claims": [claim], "reason": "t"})
    [c] = post_validate(out, [], catalog, promo, utterance="It's thirty-six dollars, very cheap.").claims
    assert (c.verdict, c.field, c.correct_value) == ("contradicted", "promo", "S$32.40")
    [c] = post_validate(out, [], catalog, promo, utterance="Normally thirty-six dollars, now it's less.").claims
    assert c.verdict == "supported"
    [c] = post_validate(out, [], catalog, None, utterance="It's thirty-six dollars.").claims
    assert c.verdict == "supported"  # no sale: the live price is right
