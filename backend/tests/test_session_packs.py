"""D-142 (JAPAC B): each session holds its own (market, language) pack; the runtime takes it from there."""
from __future__ import annotations

import json
import shutil

import pytest

from app.pipelines.runtime import ActionError, create_session

from .helpers import make_ctx


async def test_a_session_takes_the_settings_pair_by_default():
    ctx = make_ctx()
    s = await create_session(ctx, "daon_skincare_demo")
    assert (s.market, s.lang) == ("SG", "en")
    rt = await ctx.runtimes.get(s.session_id)
    assert rt.pack is ctx.pack and rt.reflex is ctx.reflex
    ctx.runtimes.shutdown()


async def test_a_language_the_market_does_not_offer_is_refused():
    ctx = make_ctx()
    with pytest.raises(ActionError, match="unknown_market_language|does not offer|en|ko"):
        await create_session(ctx, "daon_skincare_demo", lang="ko")


async def test_two_sessions_two_languages_on_one_service(tmp_path, settings):
    """A second broadcast language of the same market: its own pack, reflex and STT code per session."""
    data = tmp_path / "data"
    shutil.copytree(settings.data_path, data)
    sg = json.loads((data / "markets" / "sg.json").read_text(encoding="utf-8"))
    sg["languages"].append({"lang": "en2", "stt_language": "en-GB", "tier": "preview"})
    (data / "markets" / "sg.json").write_text(json.dumps(sg), encoding="utf-8")
    en2 = json.loads((data / "lang" / "en.json").read_text(encoding="utf-8"))
    en2["lang"] = "en2"
    en2["lexicon"]["patterns"]["unsure"] = r"(?i)\bmungkin\b"
    (data / "lang" / "en2.json").write_text(json.dumps(en2), encoding="utf-8")

    ctx = make_ctx(DATA_DIR=str(data))
    a = await ctx.runtimes.get((await create_session(ctx, "daon_skincare_demo")).session_id)
    b = await ctx.runtimes.get((await create_session(ctx, "daon_skincare_demo", lang="en2")).session_id)
    assert (a.pack.lang, b.pack.lang) == ("en", "en2")
    assert (a.pack.stt_language, b.pack.stt_language) == ("en-US", "en-GB")
    assert a.reflex.lexicon.is_unsure("I think so") and not b.reflex.lexicon.is_unsure("I think so")
    assert b.catalog.lexicon.is_unsure("mungkin") and b.utterances.compliance.reflex is b.reflex
    assert ctx.pack_for("SG", "en2")[0] is b.pack  # loaded once
    ctx.runtimes.shutdown()


def test_d150_the_malaysia_pack_builds_in_rm(settings, tmp_path):
    """D-150 (JAPAC step 1, option c): Malaysia's rules (ASEAN base + NPRA) build with English wording. D-179: the
    pack loads with the RM prices of products.json; without them it still refuses (D-129)."""
    from app.logic.catalog import DataPack, DataPackError, claim_rules
    from app.models.data import LangPack, MarketPack

    data = settings.data_path
    my = MarketPack.model_validate(json.loads((data / "markets" / "my.json").read_text(encoding="utf-8")))
    en = LangPack.model_validate(json.loads((data / "lang" / "en.json").read_text(encoding="utf-8")))
    rules = claim_rules(my, en)
    assert my.tier == "preview" and len(rules.rules) == 19  # D-278: the demo brand's 4 rules left the market pack
    assert not any(r.rule_id.startswith("BRAND-") or r.source_id == "PRODUCT_SHEET" for r in rules.rules)
    assert {"MY-HALAL-UNVERIFIED", "MY-AUTHORITY-APPROVAL"} <= {r.rule_id for r in rules.rules}
    pack = DataPack.load(data, "MY", "en")
    assert pack.products.currency_symbol == "RM"
    products = json.loads((data / "products" / "products.json").read_text(encoding="utf-8"))
    del products["market_prices"]
    bare = tmp_copy(data, products, tmp_path)
    with pytest.raises(DataPackError, match=r"priced in S\$, market MY uses RM"):
        DataPack.load(bare, "MY", "en")


def tmp_copy(data, products, tmp_path):
    """The data folder with another products.json."""
    import shutil

    out = tmp_path / "data"
    shutil.copytree(data, out)
    (out / "products" / "products.json").write_text(json.dumps(products), encoding="utf-8")
    return out


def test_d179_malaysia_uses_the_rm_prices_everywhere(settings, tmp_path):
    """D-179 (user decision 10/5, demo values): an MY session gets RM prices in the products, the sheets' passages,
    the prompter points and the promos (time sale RM107.10 / RM94.50 / RM184.50, gift over RM200); S$ is left
    nowhere. A promo without MY values is left out, not converted."""
    from app.logic.catalog import Catalog, DataPack
    from app.logic.promos import promo_passage

    pack = DataPack.load(settings.data_path, "MY", "en")
    cat = Catalog(pack)
    cream = cat.get_product("cream_hydra_barrier")
    assert (cream.list_price, cream.live_price, cream.key_facts["set_price"]) == (159.0, 119.0, "RM205.00")
    assert cat.price_display("ampoule_deep_hydration") == "RM105.00" and cat.live_price_value("set_cream_ampoule") == 205.0
    texts = {p.passage_id: p.text for p in pack.passages}
    assert texts["DL-CR-01#key-facts#live-broadcast-price"].startswith("Live broadcast price: RM119.00")
    assert texts["DL-AM-01#key-facts#list-price"] == "List price: RM139.00"
    assert any("RM119 (list RM159)" in pt.text for pt in cream.prompter_points)
    assert "RM205" in pack.promos_by_id["promo_set_reminder"].viewer_text
    sale, gift = pack.promos_by_id["promo_time_sale_10"], pack.promos_by_id["promo_gift_pouch"]
    assert cat.price_display("set_cream_ampoule", sale) == "RM184.50"
    assert promo_passage(sale, cat).text.startswith("Time sale price (extra 10% off the live price): Hydra Barrier "
                                                    "Cream RM107.10; Deep Hydration Ampoule RM94.50;")
    assert (gift.min_spend, gift.host_text, gift.viewer_text) == (
        200.0, "GIFT OVER RM200", "Free DAON LAB travel pouch with orders over RM200")
    assert pack.runsheets["daon_skincare_demo"].promo_ids == ["promo_time_sale_10", "promo_gift_pouch", "promo_set_reminder"]
    dump = pack.products.model_dump_json(exclude={"market_prices"}) + "".join(texts.values())
    assert "S$" not in dump + pack.promos.model_dump_json()
    assert pack.lexicon.spoken_numbers("It is RM119.00 today") == {"119"}
    sg = DataPack.load(settings.data_path, "SG", "en")
    assert Catalog(sg).price_display("cream_hydra_barrier") == "S$36.00"  # the default market is unchanged
    products = json.loads((settings.data_path / "products" / "products.json").read_text(encoding="utf-8"))
    del products["market_prices"]["MY"]["promos"]["promo_gift_pouch"]
    no_gift = DataPack.load(tmp_copy(settings.data_path, products, tmp_path), "MY", "en")
    assert "promo_gift_pouch" not in no_gift.promos_by_id
    assert no_gift.runsheets["daon_skincare_demo"].promo_ids == ["promo_time_sale_10", "promo_set_reminder"]


async def test_d150_a_preview_language_posts_nothing_by_itself(tmp_path, settings):
    """Preview (no sealed eval yet): host cards only. An AUTO price question goes to the host, nothing is posted."""
    from .helpers import live_runtime, say

    data = tmp_path / "data"
    shutil.copytree(settings.data_path, data)
    sg = json.loads((data / "markets" / "sg.json").read_text(encoding="utf-8"))
    sg["languages"][0]["tier"] = "preview"
    (data / "markets" / "sg.json").write_text(json.dumps(sg), encoding="utf-8")
    ctx = make_ctx(DATA_DIR=str(data))
    rt = await live_runtime(ctx)
    try:
        assert not rt.live and (await rt.snapshot("host"))["market"]["tier"] == "preview"
        await say(rt, "Lee", "How much is the cream?")
        [g] = await rt.groups()
        assert (g.route, g.route_reason, g.status) == ("HOST", "preview", "ready")
        from app.models.session import Message
        assert await rt.ctx.store.query(rt.path("messages"), Message) == []
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()


async def test_d179_an_rm_session_needs_a_server_in_that_market():
    """D-179: the sheets' index and /catalog follow the server's market, so an MY session runs on a MARKET=MY server;
    an SG server refuses it instead of mixing S$ sheets with RM prices."""
    from app.pipelines.runtime import ActionError, create_session

    from .helpers import make_ctx

    sg = make_ctx()
    with pytest.raises(ActionError, match="MARKET=MY"):
        await create_session(sg, "daon_skincare_demo", market="MY")
    my = make_ctx(MARKET="MY")
    s = await create_session(my, "daon_skincare_demo")
    rt = await my.runtimes.get(s.session_id)
    assert (s.market, rt.catalog.price_display("cream_hydra_barrier")) == ("MY", "RM119.00")
    assert any(p.text.startswith("Live broadcast price: RM119.00") for p in await my.retriever.prefetch("cream_hydra_barrier"))
    sg.runtimes.shutdown()
    my.runtimes.shutdown()
