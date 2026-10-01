from __future__ import annotations

import pytest

from app.logic.reflex import Reflex, normalise


@pytest.fixture(scope="module")
def reflex(pack):
    return Reflex(pack.rules)


def rules(hits):
    return [h.rule_id for h in hits]


def test_normalise():
    assert normalise("It’s “100% safe” — S$36.00!") == "it's 100% safe s$36.00"
    assert normalise("No. 1 cream") == "no 1 cream"


def test_word_boundaries(reflex):
    assert reflex.scan("I'm scared of heavy creams, but this one is light.") == []
    assert rules(reflex.scan("It even removes your old acne scars.")) == ["ASEAN-3-SKIN-SCARS"]
    assert reflex.scan("It is curable? no, curated.") == []


def test_multi_word_phrases(reflex):
    hits = reflex.scan("Use it every night and your wrinkles will disappear overnight.")
    assert rules(hits) == ["ASEAN-3-SKIN-AGEING"]
    assert hits[0].phrase == "wrinkles will disappear"
    assert rules(reflex.scan("You'll look ten years younger after one bottle.")) == ["ASEAN-3-SKIN-AGEING"]
    assert reflex.scan("your wrinkles  will\ndisappear") != []  # whitespace collapses


def test_hyphenated_phrase(reflex):
    assert "ASEAN-3-SKIN-ACNE" in rules(reflex.scan("Your skin will be acne-free!"))


def test_negation_within_four_tokens(reflex):
    hit = reflex.scan("Just to be clear, it does not treat acne. It's a moisturiser.")
    assert rules(hit) == ["ASEAN-3-SKIN-ACNE"] and hit[0].negated  # S08: provisional only, judge clears
    hit = reflex.scan("It definitely does not cure eczema.")
    assert {h.rule_id for h in hit} == {"ASEAN-2D-DISEASE"} and all(h.negated for h in hit)
    far = reflex.scan("No, I promise you that this lovely product cures eczema.")
    assert any(not h.negated for h in far)  # "no" is more than 4 tokens before


def test_negation_does_not_cross_sentences(reflex):
    hits = reflex.scan("No. It cures eczema.")
    assert hits and not any(h.negated for h in hits)


def test_quote_cues(reflex):
    hits = reflex.scan("Someone asked if it cures eczema. No, it's a cosmetic.")
    assert hits and all(h.quoted for h in hits)
    hits = reflex.scan("Someone asked a question. It cures eczema.")
    assert hits and not any(h.quoted for h in hits)  # quote cue in another sentence
