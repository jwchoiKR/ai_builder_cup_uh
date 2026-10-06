"""D-283: the false-alert fixes Q2 (a quoted value corrected in the same line) and Q4 (a contradicted verdict whose
own reason says the line agrees), on made-up lines across categories (a supplement, a children's product, a
fragrance, a haircare product, a kettle). Each fix must drop its false alerts and keep every true contradiction."""
from __future__ import annotations

import pytest

from app.agents.fact_checker import post_validate
from app.models.agent_io import FactCheckOutput
from app.models.data import Passage

PID = "cream_hydra_barrier"


@pytest.fixture
def check(catalog):
    def go(line, stated, correct, quote, field, fixes, reason="t"):
        p = Passage(passage_id="DL-CR-01#key-facts#x", product_id=PID, doc="sheet", section="Key facts", text=quote,
                    score=0.0)
        raw = {"claims": [{"span": line, "product_id": PID, "verdict": "contradicted", "passage_id": p.passage_id,
                           "field": field, "stated_value": stated, "correct_value": correct, "quote": quote}],
               "reason": reason}
        return post_validate(FactCheckOutput.model_validate(raw), [p], catalog, None, line,
                             fixes=frozenset(fixes)).claims[0].verdict
    return go


Q2 = [  # (category, line, stated, correct, quote, field, false alert today)
    ("supplement", "Someone asked 'is it 500 mg?' No, it's 1000 mg of vitamin C.", "500 mg", "1000 mg",
     "Vitamin C 1000 mg per tablet", "ingredient_amount", True),
    ("fragrance", "A viewer wrote S$89 for the 50 mL? No, it's S$98.", "S$89", "S$98.00",
     "Live broadcast price (50 ml): S$98.00", "price", True),
    ("kettle", "Is it 1.5 litres? No, it holds 1.7 litres.", "1.5 litres", "1.7 litres", "Capacity: 1.7 litres",
     "volume", True),
    ("children", "Someone asked if it's from age 2. Yes, from 2.", "age 2", "age 4", "For children aged 4 and up",
     "usage", False),
    ("haircare", "Someone asked about the price, it's S$25.", "S$25", "S$28.00", "Live broadcast price: S$28.00",
     "price", False),
    ("supplement", "Someone asked if it's 1000 mg. Yes, it is 500 mg.", "500 mg", "1000 mg",
     "Vitamin C 1000 mg per tablet", "ingredient_amount", False),
    ("fragrance", "Is it S$98? It's S$89 today.", "S$89", "S$98.00", "Live broadcast price (50 ml): S$98.00", "price",
     False),
]


@pytest.mark.parametrize("category, line, stated, correct, quote, field, false_alert", Q2,
                         ids=[f"{c[0]}-{i}" for i, c in enumerate(Q2)])
def test_d283_q2_a_quoted_value_corrected_in_the_line(check, category, line, stated, correct, quote, field,
                                                      false_alert):
    assert check(line, stated, correct, quote, field, ()) == "contradicted"  # today: an alert either way
    assert (check(line, stated, correct, quote, field, {"Q2"}) == "contradicted") is not false_alert


Q4 = [  # (category, reason, false alert today)
    ("children", "The host's 'from 4' is consistent with 'not suitable under 4'.", True),
    ("fragrance", "The stated 15% matches the sheet.", True),
    ("haircare", "S$48 matches the list price, but the live price is S$36.", False),
    ("supplement", "The host's dose does not match the label: 2 tablets vs 1.", False),
    ("kettle", "The stated capacity is correct for the 1.5 L model, not this 1.7 L one.", False),
    ("supplement", "The amount is not consistent with the label.", False),
]


@pytest.mark.parametrize("category, reason, false_alert", Q4, ids=[f"{c[0]}-{i}" for i, c in enumerate(Q4)])
def test_d283_q4_a_verdict_whose_reason_says_the_line_agrees(check, category, reason, false_alert):
    args = ("It costs twenty dollars.", "S$20", "S$36.00", "Live broadcast price: S$36.00", "price")
    assert check(*args, (), reason) == "contradicted"
    assert (check(*args, {"Q4"}, reason) == "contradicted") is not false_alert
