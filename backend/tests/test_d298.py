"""D-298: two checks of the model's extraction against the text, before the freeze. The CK group must be said in the
line or the previous final; a quote or question in the previous final, rejected in this one, is no contradiction
when this line says the correction. Paired: each false-alert class next to the line that must still alert."""
from __future__ import annotations

import pytest

from app.agents.fact_checker import from_relation, hard_validate, sentence_index

from .judge_fakes import CREAM
from .test_relation import ALL, V, _high, _p, _rel, _validate_r


@pytest.mark.parametrize("line, prev, group, kept", [
    ("Ten-free means absolutely no harmful effects, guaranteed.", None, "everyone", False),
    ("Safe for everyone.", None, "everyone", True),
    ("After a patch test this oil is completely safe.", None, "sensitive skin", False),
    ("Gentle on sensitive skin.", None, "sensitive skin", True),
    ("This is totally safe.", "My little one has eczema.", "children with eczema", True),  # the previous final
    ("임산부도 안심하고 쓸 수 있어요.", None, "임산부", True),  # any script: the judge copies the line's words
])
def test_d298_ck_the_group_must_be_said(catalog, line, prev, group, kept):
    v = _high(V, line, "safety_promise", group)
    assert [x.rule_id for x in _validate_r(catalog, line, [v], ALL, prev)] == ([V] if kept else [])


PRICE = "Live broadcast price (50 mL): S$24.00"


@pytest.mark.parametrize("prev, line, stated, correct, quote, field, alert", [
    # the previous final quotes or asks, this one rejects it and says the correction
    ("Someone asked whether it cures acne.", "No, I'm not making that claim; it cleanses.", "cures acne",
     "A gentle cleanser", "A gentle cleanser for daily use.", "other", False),
    ("Someone asked whether it cures acne.", "Yes, it cures acne.", "cures acne", "A gentle cleanser",
     "A gentle cleanser for daily use.", "other", True),
    ("Someone asked if it's fragrance-free.", "No, it contains fragrance.", "fragrance-free", "Contains fragrance",
     "Contains fragrance (parfum).", "fragrance", False),
    ("Someone asked if it's fragrance-free.", "Yes, it's fragrance-free.", "fragrance-free", "Contains fragrance",
     "Contains fragrance (parfum).", "fragrance", True),
    ("Someone asked if the 50 mL is S$20.", "No, it's S$24.", "S$20", "S$24.00", PRICE, "price", False),
    # The critic's guards: a line that starts with a rejection and asserts its own wrong value still alerts
    ("Someone asked if the 50 mL is S$20.", "No, it's S$15.", "S$15", "S$24.00", PRICE, "price", True),
    ("It's a great price.", "No, it's S$15.", "S$15", "S$24.00", PRICE, "price", True),
    ("Someone asked whether it cures eczema.", "No, it cures eczema.", "cures eczema",
     "Not for treating skin conditions", "Not for treating skin conditions.", "other", True),
    # the same final: "That is wrong" rejects the quote
    (None, "Someone wrote, 'No reapplication needed.' That is wrong; follow the reapplication time.",
     "No reapplication needed", "Reapply every 2 hours", "Reapply every 2 hours.", "usage", False),
    (None, "Someone wrote, 'No reapplication needed.' That is right, no need to reapply.",
     "No reapplication needed", "Reapply every 2 hours", "Reapply every 2 hours.", "usage", True),
])
def test_d298_a_rejection_of_the_previous_quote(catalog, prev, line, stated, correct, quote, field, alert):
    from app.config import get_settings

    fixes = frozenset(x.strip() for x in get_settings().FACT_FIXES.split(","))
    passages = [_p("DL-CR-01#key-facts#x", quote)]
    _, index = sentence_index(passages)
    out = from_relation(_rel((line, CREAM, field, stated, ["S1"], "contradicts", correct)), index, set())
    got = hard_validate(out, passages, catalog, None, (), {CREAM}, line, fixes, prev).claims[0].verdict
    assert (got == "contradicted") is alert
