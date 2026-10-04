"""D-134: the text guards take their language from the Lexicon they are handed (B-ready)."""
from __future__ import annotations

import re
from dataclasses import replace

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
    assert verbal_check("I think it is 36 dollars", "It is S$36.00.", [], lex) is not None
    assert verbal_check("I think it is 36 dollars", "It is S$36.00.", [], other) is None
    assert verbal_check("mungkin 36", "It is S$36.00.", [], other) is not None
    assert prefilter("call +601234567890", other).hide_category == "personal_info"
    assert prefilter("call +601234567890", lex).kind != "hide"
    assert prefilter("cantik", other).kind == "reaction"
