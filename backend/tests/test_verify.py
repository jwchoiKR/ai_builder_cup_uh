from __future__ import annotations

from .conftest import make_settings  # D-278: the test data dir

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


PANTH = ("DL-CR-01#key-ingredients#panthenol", "Panthenol: 5%")
SQUAL = ("DL-CR-01#key-ingredients#squalane", "Squalane: 3%")


HYDRATION = ("DL-CR-01#in-house-test-results#skin-hydration-immediately-after-one-application",
             "Skin hydration immediately after one application: +38% versus before application.")
