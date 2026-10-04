from __future__ import annotations

import json

import pytest

from app.logic.catalog import Catalog, DataPack, DataPackError

CREAM, AMPOULE = "cream_hydra_barrier", "ampoule_deep_hydration"


def test_pack_loads_with_expected_sizes(pack):
    assert len(pack.passages) == 76
    assert len(pack.rules.rules) == 15  # 14 + BRAND-TEST-QUALIFIER (D-105)
    assert {p.product_id for p in pack.products.products} == {CREAM, AMPOULE}
    assert "daon_skincare_demo" in pack.runsheets


def test_run_sheet_order_and_next_product(catalog):
    assert catalog.order == [CREAM, AMPOULE]
    assert catalog.next_product(None) == CREAM
    assert catalog.next_product(CREAM) == AMPOULE
    assert catalog.next_product(AMPOULE) is None


@pytest.mark.parametrize(
    "text, expected",
    [
        ("How much is the cream?", CREAM),
        ("does the ampoule sting", AMPOULE),
        ("is the HYDRA BARRIER CREAM ok for oily skin", CREAM),
        ("niacinamide serum price?", AMPOULE),
        ("is the ampoule a cream?", AMPOULE),  # bare "cream" ignored when "ampoule" is present
        ("can I use the gel-cream at night", CREAM),
        ("barrier cream or hydration ampoule?", AMPOULE),  # longest alias wins
        ("creamy texture?", None),  # word boundary
        ("price pls", None),
    ],
)
def test_product_by_alias(catalog, text, expected):
    assert catalog.product_by_alias(text) == expected


def test_products_mentioned_has_no_cream_suppression(catalog):
    assert catalog.products_mentioned("the cream and the ampoule, which first?") == {CREAM, AMPOULE}
    assert catalog.products_mentioned("so pretty") == set()


def test_price_display_reads_prices_and_promo_prices(catalog, pack):
    time_sale = pack.promos_by_id["promo_time_sale_10"]
    gift = pack.promos_by_id["promo_gift_pouch"]
    assert catalog.price_display(CREAM) == "S$36.00"
    assert catalog.price_display(AMPOULE) == "S$32.00"
    assert catalog.price_display("set_cream_ampoule") == "S$62.00"
    assert catalog.price_display(CREAM, time_sale) == "S$32.40"
    assert catalog.price_display(AMPOULE, time_sale) == "S$28.80"
    assert catalog.price_display("set_cream_ampoule", time_sale) == "S$55.80"
    assert catalog.price_display(CREAM, gift) == "S$36.00"  # non-price promo


def test_claims(catalog):
    assert catalog.approved_claims(CREAM)[0] == "Helps keep skin hydrated for up to 24 hours.*"
    assert any("whitens" in c.lower() for c in catalog.not_approved_claims(AMPOULE))


def test_lookups(pack):
    assert pack.rules_by_id["BRAND-SUPERLATIVE"].severity == "MEDIUM"
    assert pack.intents_by_name["pregnancy_breastfeeding"].sensitive is True
    with pytest.raises(DataPackError):
        pack.runsheet("nope")


def test_inconsistent_pack_fails_fast(tmp_path, settings):
    import shutil

    data = tmp_path / "data"
    shutil.copytree(settings.data_path, data)
    rs_path = data / "runsheets" / "demo_runsheet.json"
    rs = json.loads(rs_path.read_text(encoding="utf-8"))
    rs["items"][0]["required_point_ids"].append("cr-p99")
    rs_path.write_text(json.dumps(rs), encoding="utf-8")
    with pytest.raises(DataPackError, match="cr-p99"):
        DataPack.load(data)


def test_catalog_unknown_product(catalog):
    with pytest.raises(KeyError):
        catalog.get_product("nope")
    assert isinstance(catalog, Catalog)


def test_d129_market_and_language_packs_make_the_rules(pack):
    """Singapore law + English wording: every rule has its category's phrases; STT code from the pack."""
    assert pack.rules.market == "SG" and pack.market.regulator.startswith("Health Sciences Authority")
    assert pack.stt_language == "en-US"  # chirp_3 rejects en-SG
    disease = pack.rules_by_id["ASEAN-2D-DISEASE"]
    assert disease.severity == "HIGH" and "eczema" in disease.reflex_phrases
    assert "does not" in pack.rules.negation_cues


def _copy(tmp_path, settings):
    import shutil

    data = tmp_path / "data"
    shutil.copytree(settings.data_path, data)
    return data


def test_d129_language_must_be_offered_and_complete(tmp_path, settings):
    data = _copy(tmp_path, settings)
    with pytest.raises(FileNotFoundError):
        DataPack.load(data, lang="ko")  # no Korean pack yet
    (data / "lang" / "ko.json").write_text((data / "lang" / "en.json").read_text(encoding="utf-8")
                                           .replace('"lang": "en"', '"lang": "ko"'), encoding="utf-8")
    with pytest.raises(DataPackError, match="does not offer language ko"):
        DataPack.load(data, lang="ko")
    en = json.loads((data / "lang" / "en.json").read_text(encoding="utf-8"))
    del en["categories"]["whitening"]
    (data / "lang" / "en.json").write_text(json.dumps(en), encoding="utf-8")
    with pytest.raises(DataPackError, match="whitening"):
        DataPack.load(data)


def test_d129_products_priced_in_the_market_currency(tmp_path, settings):
    data = _copy(tmp_path, settings)
    sg = json.loads((data / "markets" / "sg.json").read_text(encoding="utf-8"))
    sg["currency"]["symbol"] = "RM"
    (data / "markets" / "sg.json").write_text(json.dumps(sg), encoding="utf-8")
    with pytest.raises(DataPackError, match="priced in S\$"):
        DataPack.load(data)
