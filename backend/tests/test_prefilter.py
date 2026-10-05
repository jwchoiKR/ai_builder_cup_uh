from __future__ import annotations

import pytest

from app.logic.prefilter import prefilter

from app.config import get_settings as _settings  # noqa: E402
from app.logic.catalog import DataPack as _DataPack  # noqa: E402

LEX = _DataPack.load(_settings().data_path).lexicon  # D-134: English (SG) lexicon



@pytest.mark.parametrize(
    "text, category",
    [
        ("https://x.y/z", "link"),  # D-234: only a bare link is hidden here
        ("www.deal-cosmetics.example !!", "link"),
        ("my email is jane.tan@example.com send me codes", "personal_info"),
        ("call me 9123 4567 for wholesale", "personal_info"),
        ("Message me on WhatsApp 8123 4567 for wholesale", "personal_info"),
        ("DM me for 50% codes, call 9123 4567", "personal_info"),
        ("+65 6123 4567 office", "personal_info"),
        ("+6591234567", "personal_info"),
        ("what the fuck is this", "profanity"),
        ("SHIT that's pricey", "profanity"),
    ],
)
def test_hide(text, category):
    v = prefilter(text, LEX)
    assert (v.kind, v.hide_category) == ("hide", category)


@pytest.mark.parametrize("text", ["Cheap creams here >>> www.deal-cosmetics.example", "price for the 50ml bit.ly/x",
                                  "this one can use for kids or not? see daonlab.sg"])
def test_d234_a_link_with_words_goes_to_triage(text):
    assert prefilter(text, LEX).kind is None  # triage tells spam from a question


@pytest.mark.parametrize("text", ["😍😍", "😍😍😍", "👏👏", "!!!", "ok", "So pretty! 💜", "wow", "hi hi", "yesss",
                                  "LOL", "+1", "love it!!", "  same  ", "??", "?!"])
def test_reaction_without_llm(text):
    assert prefilter(text, LEX).kind == "reaction"


@pytest.mark.parametrize("text", [
    "this host is stupid",  # mild insult: left to the LLM (harassment)
    "this host talks way too much, so annoying",
    "How much is the cream?",
    "price pls",
    "lol same",
    "love the packaging",
    "S$36.00 is a good price",  # a price is not a phone number
    "is it 30 mL or 50 mL",
    "scunthorpe is a town",  # word boundaries
    "hello from Jurong!",
    "ml?",  # short questions are not dropped as reactions
    "SPF?",
])
def test_needs_llm(text):
    assert prefilter(text, LEX).kind is None


@pytest.mark.parametrize("text, kind", [("what the fuck is this", None), ("ml", None), ("ok", None), ("가격", None),
                                        ("call me 9123 4567 for wholesale", "hide"), ("https://x.y/z", "hide")])
def test_d237_pii_only_keeps_only_what_must_never_show(text, kind):
    assert prefilter(text, LEX, "pii_only").kind == kind
