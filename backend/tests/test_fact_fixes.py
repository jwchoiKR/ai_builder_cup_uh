"""D-280: the fact fixes F1-F4 on made-up claims and passages. Each case is a right model verdict that today's code
drops; the fix keeps it. The guards each fix must keep are the rest of the suite run with FACT_FIXES set."""
from __future__ import annotations

import pytest

from app.agents.fact_checker import post_validate
from app.models.agent_io import FactCheckOutput
from app.models.data import Passage

PID = "cream_hydra_barrier"


def passage(pid_key: str, section: str, text: str) -> Passage:
    return Passage(passage_id=f"DL-CR-01#{pid_key}", product_id=PID, doc="sheet", section=section, text=text, score=0.0)


CASES = {
    "F1": (passage("record-facts#offer-o1", "Record facts",
                   "Offer: Free pouch over S$60; condition: purchases in different markets cannot be combined"),
           dict(field="other", stated_value="the gift counts across both markets",
                correct_value="purchases in different markets cannot be combined",
                quote="purchases in different markets cannot be combined"),
           "the gift counts across both markets"),
    "F2": (passage("key-ingredients#ethanol", "Key ingredients", "Ethanol 78 % v/v"),
           dict(field="ingredient_amount", stated_value="60% ethanol", correct_value="78% v/v ethanol",
                quote="Ethanol 78% v/v"),
           "it has sixty percent ethanol"),
    "F3": (passage("key-ingredients#panthenol", "Key ingredients", "Panthenol 5%: helps relieve the feeling of dryness"),
           dict(field="ingredient", stated_value="10% panthenol", correct_value="5% panthenol", quote="Panthenol 5%"),
           "there is ten percent panthenol in it"),
    "F4": (passage("record-facts#offer-o2", "Record facts",
                   "Offer: Buy 3 get 10% off; the 4th bottle is at the regular price"),
           dict(field="promo", stated_value="all 4 discounted", correct_value="the 4th bottle is at the regular price",
                quote="the 4th bottle is at the regular price"),
           "buy four and all four are discounted"),
}


@pytest.mark.parametrize("fix", sorted(CASES))
def test_d280_each_fix_keeps_a_right_verdict_that_today_s_code_drops(fix, catalog):
    p, fields, line = CASES[fix]
    raw = {"claims": [{"span": line, "product_id": PID, "verdict": "contradicted", "passage_id": p.passage_id,
                       **fields}], "reason": "t"}
    verdict = lambda fixes: post_validate(FactCheckOutput.model_validate(raw), [p], catalog, None, line,  # noqa: E731
                                          fixes=frozenset(fixes)).claims[0]
    assert verdict(()).verdict == "not_in_sources"  # today: dropped by code
    kept = verdict({fix})
    assert kept.verdict == "contradicted"
    if fix == "F1":
        assert kept.field == "promo"  # re-fielded from its source


def test_d280_f2_never_grounds_a_quote_in_another_product(catalog):
    mine = passage("key-facts#volume", "Key facts", "Volume: 50 mL")
    other = Passage(passage_id="DL-AM-01#key-ingredients#ethanol", product_id="ampoule_deep_hydration", doc="sheet",
                    section="Key ingredients", text="Ethanol 78 % v/v", score=0.0)
    raw = {"claims": [{"span": "x", "product_id": PID, "verdict": "contradicted", "passage_id": mine.passage_id,
                       "field": "ingredient_amount", "stated_value": "60% ethanol", "correct_value": "78% v/v",
                       "quote": "Ethanol 78% v/v"}], "reason": "t"}
    out = post_validate(FactCheckOutput.model_validate(raw), [mine, other], catalog, None, "x", fixes=frozenset({"F2"}))
    assert out.claims[0].verdict == "not_in_sources"


@pytest.mark.parametrize("field, stated, correct, quote, line, kept", [
    # rescue: the right number, the quote OCR-spaced so the quote check fails
    ("price", "S$32", "S$36.00", "Live broadcast price S$ 36 . 00", "the cream is only thirty-two dollars", True),
    ("ingredient_amount", "10% panthenol", "5%", "Panthenol 5 %", "ten percent panthenol in it", True),
    # no rescue: a number the record does not hold for this field, or for the ingredient the line names
    ("price", "S$32", "S$38.00", "Live broadcast price S$ 38 . 00", "the cream is thirty-two dollars", False),
    ("ingredient_amount", "10% squalane", "5%", "Panthenol 5 %", "ten percent squalane in it", False),
])
def test_d282_r1_a_record_value_grounds_a_correction_whose_quote_fails(catalog, field, stated, correct, quote, line,
                                                                        kept):
    p = passage("key-facts#live-broadcast-price", "Key facts", "Live broadcast price: S$36.00")
    raw = {"claims": [{"span": line, "product_id": PID, "verdict": "contradicted", "passage_id": p.passage_id,
                       "field": field, "stated_value": stated, "correct_value": correct, "quote": quote}],
           "reason": "t"}
    verdict = lambda fixes: post_validate(FactCheckOutput.model_validate(raw), [p], catalog, None, line,  # noqa: E731
                                          fixes=frozenset(fixes)).claims[0].verdict
    assert verdict(()) == "not_in_sources"
    assert (verdict({"R1"}) == "contradicted") is kept


def test_d282_r1_never_resurrects_a_restatement(catalog):
    p = passage("key-facts#live-broadcast-price", "Key facts", "Live broadcast price: S$36.00")
    raw = {"claims": [{"span": "x", "product_id": PID, "verdict": "contradicted", "passage_id": p.passage_id,
                       "field": "price", "stated_value": "S$36", "correct_value": "S$36.00", "quote": "S$ 36"}],
           "reason": "t"}
    out = post_validate(FactCheckOutput.model_validate(raw), [p], catalog, None, "it is thirty-six dollars",
                        fixes=frozenset({"R1"}))
    assert out.claims[0].verdict == "not_in_sources"
