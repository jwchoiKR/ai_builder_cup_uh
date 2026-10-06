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


Q1E = [  # (category, result say, line, exempt with Q1E)
    ("haircare", "Brightwell Labs: no colour transfer through 8 hours (independent lab test, 20 adults)",
     "Brightwell Labs found no transfer through 8 hours.", True),
    ("children", "Removes 90% of plaque in 4 weeks (clinical study, 40 children)",
     "In a study with 40 children it removed 90% of plaque in 4 weeks.", True),
    ("supplement", "Absorbed 2x faster (in our in-house test, 20 adults)",
     "With 20 adults it was absorbed twice as fast.", False),  # our own test needs our own words (D-250)
    ("fragrance", "Lasts 8 hours on skin (tested by Kestrel Institute)", "It lasts 8 hours on skin.", False),
    ("kettle", "Boils 1 litre in 3 minutes (tested by Larkmoor Test Centre, 30 runs)",
     "It boils a litre in 3 minutes, every time.", False),
]


@pytest.mark.parametrize("category, say, line, exempt", Q1E, ids=[f"{c[0]}-{i}" for i, c in enumerate(Q1E)])
def test_d284_q1e_a_line_naming_the_tester_needs_no_qualifier(pack, category, say, line, exempt):
    from app.agents.utterance_judge import names_the_source, names_the_tester

    lex = pack.lexicon
    assert (names_the_source(line, say, lex) or names_the_tester(line, say, lex)) is exempt


def test_d284_q1e_covers_what_d244_missed(pack):
    from app.agents.utterance_judge import names_the_source

    for _, say, line, exempt in Q1E[:2]:
        assert exempt and not names_the_source(line, say, pack.lexicon)  # today these lines get the qualifier alert


@pytest.mark.parametrize("first, second", [
    ("The bottle at S$32 contains", "two hundred tablets of vitamin C."),  # supplement: the price of another size
    ("Our travel spray for", "S$32 is the 10 mL one."),  # fragrance
    ("Each kettle comes with", "a S$32 descaling kit."),  # kitchen
])
@pytest.mark.parametrize("q5", [False, True])
async def test_d285_q5_a_fragment_is_judged_with_the_next_final(first, second, q5):
    """Judged alone, the fragment reads as a wrong price (the scripted false alert); with Q5 it is held and judged
    once, joined with the next final, which the fact checker reads as fine."""
    from .helpers import live_runtime, make_ctx
    from .judge_fakes import ScriptedBackend, close_env, price_contradiction, speak

    llm = ScriptedBackend()
    llm.facts(first, price_contradiction())
    rt = await live_runtime(make_ctx(backend=llm, FACT_FIXES="Q5" if q5 else ""))
    try:
        await speak(rt, first, wait=False)
        await speak(rt, second, wait=False)
        await rt.utterances.drain()
        await rt.ctx.scheduler.idle()
        facts = [a for a in await rt.alerts() if a.kind == "fact"]
        assert (facts == []) is q5
    finally:
        await close_env(rt)


async def test_d285_q5_a_held_fragment_with_no_next_final_is_still_checked():
    from .helpers import live_runtime, make_ctx
    from .judge_fakes import ScriptedBackend, close_env, price_contradiction, speak

    llm = ScriptedBackend()
    llm.facts("Today it costs S$32 for", price_contradiction())  # a true wrong price, the line just trails off
    rt = await live_runtime(make_ctx(backend=llm, FACT_FIXES="Q5"))
    try:
        await speak(rt, "Today it costs S$32 for", wait=False)
        await rt.ctx.scheduler.advance(rt.settings.UTTERANCE_MERGE_WINDOW_MS + 100)  # the window passes
        await rt.utterances.drain()
        assert [a.kind for a in await rt.alerts() if a.kind == "fact"] == ["fact"]
    finally:
        await close_env(rt)


def test_d285_mid_clause():
    from app.pipelines.utterances import mid_clause

    assert mid_clause("The bottle at SGD 158 contains") and mid_clause("It is 158") and mid_clause("Made for")
    assert not mid_clause("It is 158 dollars.") and not mid_clause("It feels light") and not mid_clause("Yes!")


def _release_catalog(tmp_path, result: str, qualifier: str, category: str):
    """A made-up release with one qualified result, on the clean base."""
    from app.logic.catalog import Catalog
    from app.onboarding.record import ProductRecord
    from app.onboarding.release import release_pack

    from .helpers import make_ctx
    from .test_clean_base import EV, clean_data, kettle

    rec = ProductRecord.model_validate(kettle().model_dump() | {"category": category, "qualified_results": [
        {"statement": result, "provenance": "third_party_lab", "qualifier": qualifier, "conditions": None,
         "evidence": EV}]})
    ctx = make_ctx(DATA_DIR=str(clean_data(tmp_path)), ONBOARDING_DIR=str(tmp_path / "onb"))
    pack = release_pack(ctx.pack, rec, "rel_t_v1", tmp_path / "onb")
    ctx.runtimes.shutdown()
    ctx.scheduler.shutdown()
    return Catalog(pack, "rel_t_v1")


def _validate(catalog, line, violations, fixes):
    from app.agents.utterance_judge import JudgeInput, build_judge_values, validate_compliance
    from app.models.agent_io import ComplianceOutput

    pid = catalog.products[0].product_id
    values = build_judge_values(catalog, JudgeInput(utterance=line, on_air=pid))
    out = ComplianceOutput.model_validate({"compliance": {"violations": violations},
                                           "correction": {"corrects_alert_ids": []}, "reason": "t"})
    import os
    old = os.environ.get("FACT_FIXES")
    os.environ["FACT_FIXES"] = ",".join(fixes)
    from app.config import get_settings
    get_settings.cache_clear()
    try:
        return validate_compliance(out, catalog, values).compliance.violations
    finally:
        os.environ.pop("FACT_FIXES") if old is None else os.environ.__setitem__("FACT_FIXES", old)
        get_settings.cache_clear()


Q1T = [  # (category, result, qualifier, line, alert with Q1T)
    ("supplement", "Absorbed 2 times faster than a standard tablet", "tested by Fenmore Labs",
     "Lab-tested: it is absorbed 2 times faster!", True),
    ("children", "Removes 90% of plaque in 4 weeks", "clinical study by Ardent Dental Institute, 40 children",
     "Clinically proven to remove 90% of plaque in 4 weeks.", True),
    ("fragrance", "Lasts 8 hours on skin", "tested by Kestrel Labs", "Tests confirm it lasts 8 hours on skin.", True),
    ("haircare", "Reduces breakage by 60%", "tested by Brightwell Labs, 20 adults",
     "In a lab test it reduced breakage by up to 60%, results may vary.", False),  # hedged, states its limits
    ("kitchen_appliance", "Boils 1 litre in 3 minutes", "tested by Larkmoor Test Centre",
     "Lab-tested by Larkmoor Test Centre: it boils a litre in 3 minutes.", False),  # names the tester
    ("supplement", "Absorbed 2 times faster than a standard tablet", "tested by Fenmore Labs",
     "It is lab-tested and pharmacist approved.", False),  # no result stated
]


@pytest.mark.parametrize("category, result, qualifier, line, alert", Q1T,
                         ids=[f"{c[0]}-{i}" for i, c in enumerate(Q1T)])
def test_d286_q1t_a_result_with_only_a_generic_test_word(tmp_path, category, result, qualifier, line, alert):
    from app.logic.qualifier import RULE_ID

    catalog = _release_catalog(tmp_path, result, qualifier, category)
    assert _validate(catalog, line, [], ()) == []  # today: the judge was silent, so nothing
    got = [v.rule_id for v in _validate(catalog, line, [], ("Q1T",))]
    assert (got == [RULE_ID]) is alert


Q3 = [  # (line, span, negated by Q3)
    ("It guarantees no individual result, everyone is different.", "guarantees no individual result", True),
    ("We can't guarantee you'll see results in a week.", "guarantee you'll see results", True),
    ("Our kettle does not promise faster boiling for every model.", "promise faster boiling", True),
    ("No more breakouts, guaranteed.", "No more breakouts, guaranteed", False),
    ("We guarantee no wrinkles after a month.", "guarantee no wrinkles", False),
    ("It is not only guaranteed to last, it cures dandruff.", "guaranteed to last", False),
]


@pytest.mark.parametrize("line, span, negated", Q3, ids=[str(i) for i in range(len(Q3))])
def test_d286_q3_a_denied_guarantee_is_no_guarantee(catalog, line, span, negated):
    v = {"span": span, "rule_id": "ASEAN-2E-PERMANENT", "severity": "HIGH", "is_negated": False, "is_quoted": False,
         "say_instead": "x"}
    assert [x.is_negated for x in _validate(catalog, line, [v], ())] == [False]
    assert [x.is_negated for x in _validate(catalog, line, [v], ("Q3",))] == [negated]
