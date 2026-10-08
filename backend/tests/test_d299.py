"""D-299: pool 5's failure classes, each next to the line that must keep its old outcome (made-up lines)."""
from __future__ import annotations

import pytest

from app.agents.fact_checker import from_relation, hard_validate, sentence_index
from app.logic.qualifier import RULE_ID

from .conftest import ALL_FIXES
from .judge_fakes import CREAM
from .test_q_fixes import _release_catalog
from .test_relation import V, _high, _p, _rel, _validate_r


def _fixes() -> tuple:
    return tuple(ALL_FIXES.split(","))  # D-353: the opt-in code checks, named (no longer the default)


def _qualifier(span: str, rid: str | None = None) -> dict:
    return {"span": span, "rule_id": RULE_ID, "severity": "MEDIUM", "is_negated": False, "is_quoted": False,
            "say_instead": "x", "claim_kind": None, "group": None, "qualified_result_id": rid}


@pytest.mark.parametrize("result, line, named, kept", [
    # a recorded result said with no test word keeps its qualifier alert (the gate dropped these)
    ("Mean SPF 22.5 under lab conditions", "This lotion gives SPF 22.5.", True, True),
    ("Mean SPF 22.5 under lab conditions", "This lotion gives SPF 22.5.", False, True),  # one decimal number
    ("100% of assessed strands covered", "You get complete coverage of every grey hair.", True, True),
    ("100% of assessed strands covered", "You get complete coverage of every grey hair.", False, False),  # today
    # the pair: a composition line that matches no recorded result still drops
    ("Absorbed 2 times faster than a standard tablet", "Each tablet has zinc at 2 percent.", False, False),
])
def test_d299_a_recorded_result_passes_the_gate(tmp_path, result, line, named, kept):
    catalog = _release_catalog(tmp_path, result, "tested by Fenmore Labs", "skincare")
    rid = catalog.products[0].qualified_results[0].result_id if named else None
    got = _validate_r(catalog, line, [_qualifier(line, rid)], _fixes())
    assert [x.rule_id for x in got] == ([RULE_ID] if kept else [])


@pytest.mark.parametrize("quote, other, stated, correct, alert", [
    # the right number is in another passage of the same product (a second pack), not in the cited one
    ("Standard tub: 30 tablets.", "Large tub: 60 tablets.", "90 tablets", "60 tablets", True),
    ("Measured under lab conditions.", "Mean SPF 22.5 in the lab test.", "SPF 30", "SPF 22.5 under lab conditions",
     True),
    # the pair: a number no passage or record value gives is still no correction
    ("Standard tub: 30 tablets.", "Large tub: 60 tablets.", "90 tablets", "135 tablets", False),
])
def test_d299_the_number_check_reads_every_passage_of_the_product(catalog, quote, other, stated, correct, alert):
    passages = [_p("DL-CR-01#key-facts#x", quote), _p("DL-CR-01#key-facts#y", other)]
    _, index = sentence_index(passages)
    line = f"The big tub holds {stated}."
    out = from_relation(_rel((line, CREAM, "volume", stated, ["S1"], "contradicts", correct)), index, set())
    got = hard_validate(out, passages, catalog, None, (), {CREAM}, line, frozenset(_fixes()), None)
    assert (got.claims[0].verdict == "contradicted") is alert


@pytest.mark.parametrize("line, group, kept", [
    ("Damaged skin? Go ahead and use it.", "damaged skin", False),  # reverses the caution: a fact, no HIGH
    ("Safe for pregnant women.", "pregnant women", True),  # a caution names pregnancy too, but this is a group
])
def test_d299_a_reversed_caution_is_no_vulnerable_high(catalog, line, group, kept):
    v = _high(V, line, "safety_promise", group)
    assert [x.rule_id for x in _validate_r(catalog, line, [v], _fixes())] == ([V] if kept else [])


def test_d299_the_relation_prompt_has_the_bound_hint():
    from pathlib import Path

    text = (Path(__file__).parents[2] / "prompts" / "fact_relation.md").read_text(encoding="utf-8")
    assert "excludes 25 itself" in text
