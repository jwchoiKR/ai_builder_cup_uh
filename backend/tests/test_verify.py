from __future__ import annotations

import pytest

from app.logic.promos import promo_passage
from app.logic.reflex import Reflex
from app.logic.verify import number_set, verify_answer
from app.models.agent_io import ComposerOutput

from app.config import get_settings as _settings  # noqa: E402
from app.logic.catalog import DataPack as _DataPack  # noqa: E402

LEX = _DataPack.load(_settings().data_path).lexicon  # D-134: English (SG) lexicon


CREAM, AMPOULE = "cream_hydra_barrier", "ampoule_deep_hydration"


@pytest.fixture(scope="module")
def reflex(pack):
    return Reflex(pack.rules, pack.lexicon)


@pytest.fixture
def passages(pack, catalog):
    ps = [p for p in pack.passages if p.product_id in (CREAM, AMPOULE)]
    return ps + [promo_passage(pack.promos_by_id["promo_time_sale_10"], catalog)]


def out(answer, cites, grounded=True):
    return ComposerOutput(answer=answer, citations=[{"passage_id": p, "quote": q} for p, q in cites],
                          grounded=grounded, needs_human=False, reason="")


def check(o, passages, catalog, reflex, pid=CREAM, multi=False):
    return verify_answer(o, passages, pid, multi=multi, reflex=reflex,
                         not_approved_claims=catalog.not_approved_claims(pid) if pid else [])


PRICE = ("DL-CR-01#key-facts#live-broadcast-price", "Live broadcast price: S$36.00")
LIST = ("DL-CR-01#key-facts#list-price", "List price: S$48.00")
SET = ("DL-CR-01#key-facts#live-set-price", "S$62.00 for Hydra Barrier Cream 50 mL + Deep Hydration Ampoule 30 mL")


def test_sentence_split_keeps_prices_together():
    assert LEX.split_sentences("It is S$36.00 today. The set is S$62.00!") == ["It is S$36.00 today.", "The set is S$62.00!"]
    assert len(LEX.split_sentences("Yes. It absorbs quickly. Use less.")) == 3


def test_numbers_normalise():
    assert number_set("S$36 or S$36.00 or 32.40, 4%") == {"36", "32.4", "4"}


def test_valid_price_answer(passages, catalog, reflex):
    o = out("The Hydra Barrier Cream is S$36.00 during this live (list price S$48.00). The set with the ampoule is S$62.00.",
            [PRICE, LIST, SET])
    assert check(o, passages, catalog, reflex) == (True, [])


def test_rule1_grounded_length_sentences(passages, catalog, reflex):
    assert not check(out("It is S$36.", [PRICE], grounded=False), passages, catalog, reflex)[0]
    assert "empty answer" in check(out("", [PRICE]), passages, catalog, reflex)[1]
    long = "It is S$36.00. " + "x" * 240
    assert any("240" in e for e in check(out(long, [PRICE]), passages, catalog, reflex)[1])
    three = "Yes. It is light. It is S$36.00."
    assert any("sentences" in e for e in check(out(three, [PRICE]), passages, catalog, reflex)[1])


def test_rule2_citations(passages, catalog, reflex):
    assert "no citation" in check(out("It is light.", []), passages, catalog, reflex)[1]
    assert any("unknown passage" in e for e in check(out("It is S$36.00.", [("NOPE", "x")]), passages, catalog, reflex)[1])
    bad_quote = check(out("It is S$36.00.", [("DL-CR-01#key-facts#live-broadcast-price", "price: S$30.00")]),
                      passages, catalog, reflex)
    assert any("quote not found" in e for e in bad_quote[1])
    spaced = out("It is S$36.00.", [("DL-CR-01#key-facts#live-broadcast-price", "live   BROADCAST price: S$36.00")])
    assert check(spaced, passages, catalog, reflex)[0]  # whitespace and case are normalised


def test_rule3_passages_of_the_product(passages, catalog, reflex):
    other = out("It has 4% niacinamide.", [("DL-AM-01#key-ingredients#niacinamide", "Niacinamide: 4%")])
    assert any("another product" in e for e in check(other, passages, catalog, reflex)[1])
    assert check(other, passages, catalog, reflex, pid=None, multi=True)[0]
    set_from_ampoule = out("The set is S$62.00.", [("DL-AM-01#key-facts#live-set-price", "Live set price: S$62.00")])
    assert check(set_from_ampoule, passages, catalog, reflex)[0]
    promo = out("With the time sale it's S$32.40 for the Hydra Barrier Cream right now.",
                [("PROMO#promo_time_sale_10", "Hydra Barrier Cream S$32.40")])
    assert check(promo, passages, catalog, reflex)[0]


def test_rule4_numbers_must_be_quoted(passages, catalog, reflex):
    o = out("It is S$30.00 today.", [PRICE])
    assert check(o, passages, catalog, reflex)[1] == ["number 30 not in a cited quote"]
    assert check(out("It is S$36 today.", [PRICE]), passages, catalog, reflex)[0]  # S$36 = S$36.00


def test_rule5_restricted_wording(passages, catalog, reflex):
    o = out("It does not cure eczema, but it helps relieve the feeling of dryness.",
            [("DL-CR-01#key-ingredients#panthenol", "Helps relieve the feeling of dryness.")])
    ok, errors = check(o, passages, catalog, reflex)
    assert not ok and any("restricted phrase" in e for e in errors)  # even negated
    claim = out("It removes wrinkles or reverses skin ageing.", [PRICE])
    assert any("not-approved claim" in e for e in check(claim, passages, catalog, reflex)[1])


def test_promo_passage_text(pack, catalog):
    p = promo_passage(pack.promos_by_id["promo_time_sale_10"], catalog)
    assert p.passage_id == "PROMO#promo_time_sale_10" and p.section == "Active promotion"
    assert p.text == ("Time sale price (extra 10% off the live price): Hydra Barrier Cream S$32.40; "
                      "Deep Hydration Ampoule S$28.80; Hydra Barrier Cream + Deep Hydration Ampoule set S$55.80.")


PANTH = ("DL-CR-01#key-ingredients#panthenol", "Panthenol: 5%")
SQUAL = ("DL-CR-01#key-ingredients#squalane", "Squalane: 3%")


@pytest.mark.parametrize("answer, ok", [
    ("It has 5% panthenol and 3% squalane.", True),
    ("Panthenol is 5% and squalane is 3%.", True),
    ("It has 3% panthenol and 5% squalane.", False),  # review B8: values swapped between subjects
    ("Panthenol is 3% and squalane is 5%.", False),
])
def test_rule6_each_number_belongs_to_its_subject(passages, catalog, reflex, answer, ok):
    """D-117 B8: subject/value pairs, not only "the number appears in some quote"."""
    good, errors = check(out(answer, [PANTH, SQUAL]), passages, catalog, reflex)
    assert good is ok, errors


def test_rule6_ignores_words_that_are_not_in_the_quotes(passages, catalog, reflex):
    vol = ("DL-CR-01#key-facts#volume", "Volume: 50 mL")
    good, errors = check(out("It comes in a 50 mL tube.", [vol]), passages, catalog, reflex)
    assert good, errors


def test_rule6_keeps_good_drafts_whose_labels_contain_numbers():
    """D-117 B8 follow-up: label words next to another number ("(3 molecular weights)", "48-hour patch
    test") are not subjects; every good draft of the verifier gate set verifies."""
    import json
    from pathlib import Path

    from app.config import get_settings
    from app.logic.catalog import Catalog, DataPack

    pack = DataPack.load(get_settings().data_path)
    catalog, rfx = Catalog(pack), Reflex(pack.rules, pack.lexicon)
    path = Path(get_settings().data_path) / "eval" / "draft_verifier_cases.jsonl"
    blocked = []
    for line in path.read_text(encoding="utf-8").splitlines():
        c = json.loads(line)
        if c["label"] != "good":
            continue
        o = ComposerOutput.model_validate(c["composer_output"])
        pid = c.get("product_id")
        ok, errors = verify_answer(o, pack.passages, pid, multi=pid is None, reflex=rfx,
                                   not_approved_claims=catalog.not_approved_claims(pid) if pid else [])
        if not ok:
            blocked.append((c["draft_id"], errors))
    assert blocked == []


HYDRATION = ("DL-CR-01#in-house-test-results#skin-hydration-immediately-after-one-application",
             "Skin hydration immediately after one application: +38% versus before application.")


def test_rule7_in_house_numbers_need_the_qualifier(passages, catalog, reflex):
    """D-126 (gate D007): an in-house test number without "in-house" / "our test" is not posted."""
    bare = out("Skin hydration increases by 38% immediately after application.", [HYDRATION])
    assert check(bare, passages, catalog, reflex)[1] == ["in-house test result without 'in-house test'"]
    said = out("In our in-house test, skin hydration was 38% higher right after one application.", [HYDRATION])
    assert check(said, passages, catalog, reflex)[0]


@pytest.mark.parametrize("text", [
    "The Hydra Barrier Cream is S$36.00 during this live (list price S$48.00). The set with the ampoule is S$62.00.",
    "The live broadcast price is S$36.00 and list price S$48.00.",
])
def test_rule6_stays_in_its_clause_and_accepts_any_matching_subject(passages, catalog, reflex, text):
    """D-135 (comment-flow CF05, CF09, CF11): correct price answers were blocked as "48 is not the value
    of 'set'" and "36 is not the value of 'list'"."""
    ok, errors = check(out(text, [PRICE, LIST, SET]), passages, catalog, reflex)
    assert ok, errors
