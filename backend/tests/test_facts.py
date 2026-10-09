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


# ---- review B3: one note per subject (ingredient, test, offer), not per field ---------------------

PANTHENOL = "DL-CR-01#key-ingredients#panthenol"
SQUALANE = "DL-CR-01#key-ingredients#squalane"


# ---- D-121: an ingredient the product does not contain; pH ----------------------------------------

ABSENT = "not in this product"


def _full_list():
    from app.models.data import Passage

    return Passage(passage_id="DL-CR-01#ingredients#all", product_id=CREAM, doc="sheet", section="Ingredients",
                   text="Water, glycerin, panthenol, ceramide NP, squalane.", score=0.0)
