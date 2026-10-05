"""D-134: the text guards take their language from the Lexicon they are handed (B-ready)."""
from __future__ import annotations

import re
from dataclasses import replace

import pytest

from app.logic.prefilter import prefilter
from app.logic.publish import verbal_check


def test_english_lexicon_from_the_packs(pack):
    lex = pack.lexicon
    assert lex.lang == "en"
    assert lex.content_words("up to twenty-four hours") == ["24", "hour"]
    assert lex.spoken_numbers("five point five") == {"5.5"}
    assert lex.is_unsure("I think it's thirty-six dollars")
    assert lex.is_qualified("in our in-house test")
    assert lex.phone.search("call me at +65 9123 4567")
    assert "lol" in lex.reactions


def test_guards_use_the_lexicon_they_are_handed(pack):
    """Another language or market only changes the Lexicon object, never a module global."""
    lex = pack.lexicon
    other = replace(lex, unsure=re.compile(r"\bmungkin\b"), phone=re.compile(r"\+60\d{9}"),
                    reactions=frozenset({"cantik"}))
    assert verbal_check("I think it is 36 dollars", "It is S$36.00.", lex) is not None
    assert verbal_check("I think it is 36 dollars", "It is S$36.00.", other) is None
    assert verbal_check("mungkin 36", "It is S$36.00.", other) is not None
    assert prefilter("call +601234567890", other).hide_category == "personal_info"
    assert prefilter("call +601234567890", lex).kind != "hide"
    assert prefilter("cantik", other).kind == "reaction"


@pytest.mark.parametrize("said, draft, held", [
    # D-174 (sealed verbal set): "twenty-one" was read as 20, and a duration in other units counted as a new number
    ("It's still twenty-one percent higher a day later.", "It is still 21% higher 24 hours after one application.", False),
    ("A week later it was twelve percent better.", "After 7 days it was 12% better.", False),
    ("After seven days it was twelve percent better.", "One week later it was 12% better.", False),
    ("Two weeks in, most people saw it.", "After 14 days, 26 of 30 participants saw it.", False),
    ("It's still twenty-two percent higher a day later.", "It is still 21% higher 24 hours after one application.", True),
    ("After three days it was twelve percent better.", "After 7 days it was 12% better.", True),
])
def test_d174_compound_numbers_and_equal_durations(pack, said, draft, held):
    assert (verbal_check(said, draft, pack.lexicon) is not None) is held


def test_d175_relink_candidate(pack):
    """D-175: the one waiting draft a line seems to answer, only as a trigger for a second judge call."""
    from app.logic.publish import relink_candidate

    lex = pack.lexicon
    drafts = {"g_set": "The Cream + Ampoule set is S$62 during this live.",
              "g_niacin": "The ampoule has 4% niacinamide."}
    assert relink_candidate("This ampoule has four percent niacinamide.", drafts, lex) == "g_niacin"
    assert relink_candidate("This ampoule has five percent niacinamide.", drafts, lex) is None  # a differing number
    assert relink_candidate("I think maybe it has four percent niacinamide?", drafts, lex) is None  # unsure
    assert relink_candidate("Let me show you the texture now.", drafts, lex) is None  # answers nothing
    twins = {"a": "The ampoule has 4% niacinamide.", "b": "Yes, the ampoule has 4% niacinamide."}
    assert relink_candidate("This ampoule has four percent niacinamide.", twins, lex) is None  # not one


@pytest.mark.parametrize("said, numbers", [
    ("one hundred nineteen ringgit", {"119"}),  # D-208: RM119 said aloud
    ("one hundred and nineteen", {"119"}),
    ("a hundred and five", {"105"}),
    ("two thousand five hundred", {"2500"}),
    ("one hundred", {"100"}),
    ("after one use", set()),
    ("fifty mils, thirty-six dollars", {"50", "36"}),
])
def test_d208_spoken_numbers_with_scale_words(pack, said, numbers):
    assert pack.lexicon.spoken_numbers(said) == numbers
