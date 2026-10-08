"""D-283: the false-alert fixes Q2 (a quoted value corrected in the same line) and Q4 (a contradicted verdict whose
own reason says the line agrees), on made-up lines across categories (a supplement, a children's product, a
fragrance, a haircare product, a kettle). Each fix must drop its false alerts and keep every true contradiction."""
from __future__ import annotations

import pytest


PID = "cream_hydra_barrier"


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


Q4 = [  # (category, reason, false alert today)
    ("children", "The host's 'from 4' is consistent with 'not suitable under 4'.", True),
    ("fragrance", "The stated 15% matches the sheet.", True),
    ("haircare", "S$48 matches the list price, but the live price is S$36.", False),
    ("supplement", "The host's dose does not match the label: 2 tablets vs 1.", False),
    ("kettle", "The stated capacity is correct for the 1.5 L model, not this 1.7 L one.", False),
    ("supplement", "The amount is not consistent with the label.", False),
]


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


Q3 = [  # (line, span, negated by Q3)
    ("It guarantees no individual result, everyone is different.", "guarantees no individual result", True),
    ("We can't guarantee you'll see results in a week.", "guarantee you'll see results", True),
    ("Our kettle does not promise faster boiling for every model.", "promise faster boiling", True),
    ("No more breakouts, guaranteed.", "No more breakouts, guaranteed", False),
    ("We guarantee no wrinkles after a month.", "guarantee no wrinkles", False),
    ("It is not only guaranteed to last, it cures dandruff.", "guaranteed to last", False),
]


@pytest.mark.parametrize("line", [  # D-410: every failed line gets the card, whatever its words
    "It is suitable for eczema-prone skin.", "This cream cures eczema.", "It feels light and soft."])
async def test_d288_a1_a_failed_compliance_call_gives_a_check_card_not_a_rule_alert(line):
    from .helpers import live_runtime, make_ctx
    from .judge_fakes import ScriptedBackend, close_env, events, speak

    llm = ScriptedBackend()
    for agent in ("compliance_judge", "utterance_judge"):
        llm.fail(agent, line)
    rt = await live_runtime(make_ctx(backend=llm))
    try:
        await speak(rt, line)
        await rt.utterances.drain()
        active = [a.rule_id for a in await rt.alerts() if a.kind == "compliance" and a.status == "active"]
        assert active == []
        assert len(await events(rt, "line.check")) == 1
    finally:
        await close_env(rt)


V, P = "ASEAN-2D-VULNERABLE", "ASEAN-2E-PERMANENT"
Q6 = [  # (category, line, span, rule, kept with Q6)
    ("hand gel", "This hand gel has zero side effects, honestly.", "zero side effects", V, False),
    ("supplement", "No side effects at all with these vitamins.", "No side effects at all", V, False),
    ("haircare", "The best beard oil on the market.", "The best beard oil on the market", P, False),
    ("kitchen", "Our kettle is the toughest one you can buy.", "the toughest one you can buy", P, False),
    ("fragrance", "Safe for everyone, even sensitive noses.", "Safe for everyone", V, True),
    ("supplement", "Totally safe in pregnancy.", "safe in pregnancy", V, True),
    ("children", "Gentle enough for babies, no side effects.", "Gentle enough for babies, no side effects", V, True),
    ("haircare", "Your dandruff will never come back.", "will never come back", P, True),
    ("skincare", "The results are permanent.", "The results are permanent", P, True),
]


def _with_law_rules(catalog, *rules):
    """The demo catalog plus made-up law-pack rules (as onboarding's to_rules makes them)."""
    import dataclasses

    from app.logic.catalog import Catalog

    pack = catalog.pack
    pack = dataclasses.replace(pack, rules=pack.rules.model_copy(update={"rules": [*pack.rules.rules, *rules]}))
    return Catalog(pack)


def _law_rule(rule_id: str, category: str):
    from app.onboarding.lawpack import LawPackRecord

    rec = LawPackRecord.model_validate({"rules": [{
        "rule_id": rule_id, "title": rule_id, "description": "made up", "severity": "HIGH", "rule_category": category,
        "unacceptable_examples": [], "say_instead_hint": "", "evidence": []}], "covers": ["food_supplement"],
        "name": "made up", "regulator": "made up", "language": "en"})
    return rule_id, rec


def test_d291_law_pack_rules_get_their_category_s_required_terms(pack):
    from app.onboarding.lawpack import required_terms_for, to_rules

    wording = pack.lang_pack.categories
    assert "pregnan" in required_terms_for("vulnerable_groups", wording)
    assert "forever" in required_terms_for("permanent_results", wording)
    assert required_terms_for("safety", wording) == [] and required_terms_for("disease", wording) == []
    rid, rec = _law_rule("HS-VULNERABLE", "vulnerable_groups")
    assert "baby" in to_rules("law_x_v1", rec, wording)[0].required_terms


LAW = [  # (line, rule id, rule category, span, fixes, negated or dropped)
    ("These documents give no lab result that supports a no-side-effects claim.", "HS-SAFETY-GUARANTEES", "safety",
     "no-side-effects claim", ("Q3",), "negated"),
    ("We cannot claim it has no side effects.", "HS-SAFETY-GUARANTEES", "safety", "no side effects", ("Q3",),
     "negated"),
    ("Guaranteed no side effects.", "HS-SAFETY-GUARANTEES", "safety", "Guaranteed no side effects", ("Q3", "Q6"),
     "kept"),
    ("This protein powder cures kidney disease and has 50 g protein.", "HS-DISEASE", "disease",
     "cures kidney disease", ("Q3", "Q6"), "kept"),  # a fact error with a real rule: the cure claim stays HIGH
    ("Zero side effects with these gummies.", "HS-VULNERABLE", "vulnerable_groups", "Zero side effects", ("Q6",),
     "dropped"),
    ("Safe for kids, zero side effects.", "HS-VULNERABLE", "vulnerable_groups", "Safe for kids", ("Q6",), "kept"),
]

