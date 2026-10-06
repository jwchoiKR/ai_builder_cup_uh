"""D-294: the false-alert fixes G1-G7 (pools 2 and 3 on the frozen e7bc727), on made-up lines across categories (a
supplement, a children's product, a fragrance, a haircare product, a kettle, a nail coating). Each fix must drop its
false alerts and keep every true one."""
from __future__ import annotations

import pytest

from .test_q_fixes import _law_rule, _release_catalog, _validate, _with_law_rules, check  # noqa: F401

FACT = [  # (fix, category, line, stated, correct, quote, field, false alert today)
    ("G1", "children", "Someone said 'you can share the brush'. Please don't, never share it.",
     "you can share the brush", "Do not share the toothbrush", "Do not share the toothbrush", "usage", True),
    ("G1", "supplement", "A viewer wrote 'take it on an empty stomach'. No, never take it without food.",
     "take it on an empty stomach", "Take after meals, not on an empty stomach",
     "Take after meals, not on an empty stomach", "usage", True),
    ("G1", "haircare", "Someone asks 'can I use it on wet hair?' Don't, never use it on wet hair.",
     "use it on wet hair", "Apply to dry hair only; do not use on wet hair",
     "Apply to dry hair only; do not use on wet hair", "usage", True),
    ("G1", "children", "Someone said 'you can share the brush'. Yes, you can share it.",
     "you can share the brush", "Do not share the toothbrush", "Do not share the toothbrush", "usage", False),
    ("G1", "kettle", "Someone asked 'can I leave it on the stove?' No worries, you can leave it there.",
     "leave it on the stove", "Never place the kettle on a stove", "Never place the kettle on a stove", "usage",
     False),
    ("G1", "fragrance", "Spray it on silk, don't hold back.", "Spray it on silk", "Do not spray on silk or leather",
     "Do not spray on silk or leather", "usage", False),  # no quote: the host's own instruction
    ("G2", "children", "It's 4.5 mL, not 45 mL.", "45 mL", "4.5 mL", "Volume: 4.5 mL", "volume", True),
    ("G2", "supplement", "Each tablet has 500 mg rather than 50 mg.", "50 mg", "500 mg", "Vitamin C 500 mg per tablet",
     "ingredient_amount", True),
    ("G2", "fragrance", "It's S$98 today, not S$89.", "S$89", "S$98.00", "Live broadcast price: S$98.00", "price", True),
    ("G2", "kettle", "It's not 1.7 litres, it's 1.5 litres.", "1.5 litres", "1.7 litres", "Capacity: 1.7 litres",
     "volume", False),
    ("G2", "haircare", "It's 45 mL, not 4.5 mL.", "45 mL", "4.5 mL", "Volume: 4.5 mL", "volume", False),
    ("G3", "fragrance", "An S$44 order qualifies, since it's above S$40.", "S$44", "S$40",
     "Free gift with orders above S$40", "promo", True),
    ("G3", "supplement", "Orders of S$60 get free delivery because the minimum is S$50.", "S$60", "S$50",
     "Free delivery: minimum spend S$50", "promo", True),
    ("G3", "kettle", "Spend S$120, which is over S$100, and the descaler is free.", "S$120", "S$100",
     "Free descaler with orders over S$100", "promo", True),
    ("G3", "haircare", "An S$36 order qualifies since it's above S$40.", "S$36", "S$40",
     "Free gift with orders above S$40", "promo", False),
    ("G3", "children", "An S$44 order doesn't qualify, it's above S$40.", "S$44", "S$40",
     "Free gift with orders above S$40", "promo", False),
    ("G6", "nail coating", "Apply uh too thin colour coats.", "too thin coats", "2 thin coats", "Apply 2 thin coats",
     "usage", True),
    ("G6", "supplement", "Take it for times a day with water.", "for times a day", "4 times a day",
     "Take 4 times a day", "usage", True),
    ("G6", "children", "Brush to minutes, morning and night.", "to minutes", "2 minutes", "Brush for 2 minutes",
     "usage", True),
    ("G6", "nail coating", "Apply a thin coat to nails.", "a thin coat", "2 thin coats", "Apply 2 thin coats",
     "usage", False),
    ("G6", "kettle", "Boil it for two minutes.", "two minutes", "3 minutes", "Boil for 3 minutes", "usage", False),
]


@pytest.mark.parametrize("fix, category, line, stated, correct, quote, field, false_alert", FACT,
                         ids=[f"{c[0]}-{c[1]}-{i}" for i, c in enumerate(FACT)])
def test_d294_fact_fixes(check, fix, category, line, stated, correct, quote, field, false_alert):  # noqa: F811
    assert check(line, stated, correct, quote, field, ()) == "contradicted"  # today: an alert either way
    assert (check(line, stated, correct, quote, field, {fix}) == "contradicted") is not false_alert


G4 = [  # (category, result, qualifier, line, span, kept with G4)
    ("supplement", "Absorbed 2 times faster than a standard tablet", "tested by Fenmore Labs",
     "Each tablet has zinc at 2 percent.", "zinc at 2 percent", False),
    ("haircare", "Reduces breakage by 60%", "tested by Brightwell Labs, 20 adults", "The serum is 60 percent argan oil.",
     "60 percent argan oil", False),
    ("children", "Removes 90% of plaque in 4 weeks", "clinical study by Ardent Dental Institute, 40 children",
     "The paste is 4 percent xylitol.", "4 percent xylitol", False),
    ("fragrance", "Lasts 8 hours on skin", "tested by Kestrel Labs", "It lasts 8 hours on skin.",
     "lasts 8 hours on skin", True),
    ("kitchen_appliance", "Boils 1 litre in 3 minutes", "tested by Larkmoor Test Centre", "It boils a litre in 3 minutes.",
     "boils a litre in 3 minutes", True),
    ("supplement", "Absorbed 2 times faster than a standard tablet", "tested by Fenmore Labs",
     "Absorbed two times faster!", "Absorbed two times faster", True),
    ("skincare", "Water-resistant for 80 minutes", "tested by Kestrel Labs", "It's water-resistant for eighty minutes.",
     "water-resistant for eighty minutes", True),
]
# D-295: headline results said bare (no number, no result or evidence word): D-116 drops them today, because the
# qualifier's words count against the match; with G4 they keep their alert by the result's own words
HEADLINE = [
    ("children", "Tear-free formula", "tested by Ardent Dental Institute", "This wash is tear-free.", "tear-free"),
    ("children", "No tears, gentle cleansing", "tested by Ardent Dental Institute", "Gentle cleansing without tears.",
     "Gentle cleansing without tears"),
    ("haircare", "Frizz-free in humid weather", "independent lab test by Velmora Hair Research Centre, 30 adults",
     "Frizz-free even in humid weather.", "Frizz-free even in humid weather"),
]


@pytest.mark.parametrize("category, result, qualifier, line, span, kept", G4, ids=[f"{c[0]}-{i}" for i, c in enumerate(G4)])
def test_d294_g4_a_composition_is_no_test_result(tmp_path, category, result, qualifier, line, span, kept):
    from app.logic.qualifier import RULE_ID

    catalog = _release_catalog(tmp_path, result, qualifier, category)
    v = {"span": span, "rule_id": RULE_ID, "severity": "MEDIUM", "is_negated": False, "is_quoted": False,
         "say_instead": "x"}
    assert [x.rule_id for x in _validate(catalog, line, [v], ())] == [RULE_ID]  # today: the MEDIUM stands
    assert [x.rule_id for x in _validate(catalog, line, [v], ("G4",))] == ([RULE_ID] if kept else [])


@pytest.mark.parametrize("category, result, qualifier, line, span", HEADLINE,
                         ids=[f"{c[0]}-{i}" for i, c in enumerate(HEADLINE)])
def test_d295_g4_a_headline_result_said_bare_keeps_its_alert(tmp_path, category, result, qualifier, line, span):
    from app.logic.qualifier import RULE_ID

    catalog = _release_catalog(tmp_path, result, qualifier, category)
    v = {"span": span, "rule_id": RULE_ID, "severity": "MEDIUM", "is_negated": False, "is_quoted": False,
         "say_instead": "x"}
    assert _validate(catalog, line, [v], ()) == []  # today: D-116 finds no result
    assert [x.rule_id for x in _validate(catalog, line, [v], ("G4",))] == [RULE_ID]


def _validate_after(catalog, prev, line, violations, fixes):
    """`_validate` with a previous final (a line split by speech-to-text)."""
    from app.agents import utterance_judge

    real = utterance_judge.build_judge_values

    def with_prev(*a, **k):
        values = real(*a, **k)
        values["last_two_final_transcripts_json"] = [prev]
        return values

    utterance_judge.build_judge_values = with_prev
    try:
        return _validate(catalog, line, violations, fixes)
    finally:
        utterance_judge.build_judge_values = real


@pytest.mark.parametrize("prev, line, kept", [
    ("The glycerin concentration is", "three percent.", False),
    ("Skin hydration went up", "three percent.", True),  # the result is in the previous final
])
def test_d294_g4_reads_the_previous_final(tmp_path, prev, line, kept):
    from app.logic.qualifier import RULE_ID

    catalog = _release_catalog(tmp_path, "Hydration up 3% after one week", "tested by Fenmore Labs", "skincare")
    v = {"span": line, "rule_id": RULE_ID, "severity": "MEDIUM", "is_negated": False, "is_quoted": False,
         "say_instead": "x"}
    assert [x.rule_id for x in _validate_after(catalog, prev, line, [v], ("G4",))] == ([RULE_ID] if kept else [])


@pytest.mark.parametrize("line, span, kept", [
    ("The glycerin concentration is three percent.", "three percent", False),
    ("Each capsule holds 200 mg of magnesium.", "200 mg of magnesium", False),
    ("It's proven to work, trust me.", "proven to work", True),
    ("Clinically shown to help 9 out of 10 users.", "Clinically shown", True),
    ("Here's my before and after.", "my before and after", True),
])
def test_d294_g4_unsupported_evidence_needs_an_evidence_word(catalog, pack, line, span, kept):
    from app.onboarding.lawpack import to_rules

    _, rec = _law_rule("HS-EVIDENCE", "unsupported_evidence")
    cat = _with_law_rules(catalog, *to_rules("law_x_v1", rec, pack.lang_pack.categories))
    v = {"span": span, "rule_id": "HS-EVIDENCE", "severity": "HIGH", "is_negated": False, "is_quoted": False,
         "say_instead": "x"}
    assert [x.rule_id for x in _validate(cat, line, [v], ("Q6",))] == ["HS-EVIDENCE"]  # Q6 alone: no G4 terms
    assert [x.rule_id for x in _validate(cat, line, [v], ("G4",))] == (["HS-EVIDENCE"] if kept else [])


G5 = [  # (category, result say, line, names the tester with G5)
    ("nail coating", "Quorvane Coating Test Laboratory: chip-free for 7 days", "Quorvane found it chip-free for 7 days.",
     True),
    ("supplement", "Absorbed 2x faster (Institute of Nutrient Science, 30 adults)",
     "The Institute of Nutrient Science found 2x faster absorption.", True),
    ("haircare", "Reduces breakage by 60% (Velmora Hair Research, 20 adults)", "Velmora's research shows 60% less breakage.",
     True),
    ("children", "Removes 90% of plaque in 4 weeks (in our in-house test, 40 children)",
     "It removes 90% of plaque in 4 weeks.", False),
    ("kettle", "Boils 1 litre in 3 minutes (tested by Larkmoor Test Centre)", "It boils a litre in 3 minutes.", False),
    ("nail coating", "Coating stays chip-free 7 days (tested by Coating Science Labs)",
     "The coating stays chip-free 7 days.", False),  # "coating" is the result's own word, not the tester's name
]


@pytest.mark.parametrize("category, say, line, named", G5, ids=[f"{c[0]}-{i}" for i, c in enumerate(G5)])
def test_d294_g5_more_tester_names(pack, category, say, line, named):
    from app.agents.utterance_judge import names_the_tester

    assert not names_the_tester(line, say, pack.lexicon)  # today
    assert names_the_tester(line, say, pack.lexicon, g5=True) is named


@pytest.mark.parametrize("fixes, kept", [(("Q1E",), True), (("Q1E", "G5"), False)])
def test_d294_g5_the_tester_in_the_previous_final(tmp_path, fixes, kept):
    from app.logic.qualifier import RULE_ID

    catalog = _release_catalog(tmp_path, "Chip-free for 7 days", "tested by Quorvane Coating Test Laboratory",
                               "nail_care")
    line = "it stays chip-free for 7 days."
    v = {"span": line, "rule_id": RULE_ID, "severity": "MEDIUM", "is_negated": False, "is_quoted": False,
         "say_instead": "x"}
    got = _validate_after(catalog, "The Quorvane Coating Test Laboratory checked it and", line, [v], fixes)
    assert [x.rule_id for x in got] == ([RULE_ID] if kept else [])


V = "ASEAN-2D-VULNERABLE"
G7 = [  # (category, line, kept with G7)
    ("children", "Let the child brush alone, no adult supervision needed.", False),
    ("children", "Kids can brush on their own.", False),
    ("children", "Safe for babies.", True),
    ("children", "Perfect for kids with eczema.", True),
    ("skincare", "Pregnant women can use it on their own.", True),
    ("supplement", "Seniors can take it alone, no side effects.", True),
]


@pytest.mark.parametrize("category, line, kept", G7, ids=[f"{c[0]}-{i}" for i, c in enumerate(G7)])
def test_d294_g7_a_direction_to_a_group_is_no_promise(catalog, category, line, kept):
    v = {"span": line, "rule_id": V, "severity": "HIGH", "is_negated": False, "is_quoted": False, "say_instead": "x"}
    assert [x.rule_id for x in _validate(catalog, line, [v], ("Q6",))] == [V]  # today: a group term, so the HIGH
    assert [x.rule_id for x in _validate(catalog, line, [v], ("Q6", "G7"))] == ([V] if kept else [])


def test_d294_g7_holds_for_law_pack_rules(catalog, pack):
    from app.onboarding.lawpack import to_rules

    _, rec = _law_rule("HS-VULNERABLE", "vulnerable_groups")
    cat = _with_law_rules(catalog, *to_rules("law_x_v1", rec, pack.lang_pack.categories))
    for line, kept in (("Children can mix the drink by themselves.", False), ("Safe for children.", True)):
        v = {"span": line, "rule_id": "HS-VULNERABLE", "severity": "HIGH", "is_negated": False, "is_quoted": False,
             "say_instead": "x"}
        assert [x.rule_id for x in _validate(cat, line, [v], ("Q6", "G7"))] == (["HS-VULNERABLE"] if kept else [])
