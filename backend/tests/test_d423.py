"""D-423 (user: "ㅇㅇ ㄱ"): one prompter item list, built once; the host renders it as is and the fact checker's
snapshot is the same list. No cuts: every ingredient (one without an amount by name), every set offer, every caution."""
from __future__ import annotations

from app.logic.prompter import prompter_items, prompter_passages
from app.models.data import Ingredient

from .helpers import live_runtime, make_ctx
from .judge_fakes import AMPOULE, CREAM, close_env, events


def test_d423_the_snapshot_is_the_item_list(catalog):
    items = prompter_items(catalog, AMPOULE)
    assert [(p.passage_id, p.section, p.text) for p in prompter_passages(catalog, AMPOULE)] == [
        (i["id"], i["section"], i["text"]) for i in items]
    # the demo ampoule's fifth ingredient (Panthenol 1%) is on the list now
    assert "Panthenol: 1%" in [i["text"] for i in items if i["kind"] == "ingredient"]


def test_d423_an_onboarded_product_lists_every_ingredient_and_a_name_without_an_amount(catalog):
    class View:
        def __getattr__(self, name):
            return getattr(catalog, name)

        def get_product(self, pid):
            return catalog.get_product(pid).model_copy(update={"ingredients": [
                Ingredient(key=f"i{n}", name=f"Ing {n}", amount=f"{n}%") for n in range(1, 7)]
                + [Ingredient(key="water", name="Water")]})

    ing = [i for i in prompter_items(View(), CREAM) if i["kind"] == "ingredient"]
    assert [i["text"] for i in ing] == [f"Ing {n}: {n}%" for n in range(1, 7)] + ["Water"]
    assert ing[-1]["value"] == "" and ing[0]["id"].endswith("#prompter#ingredient-1-i1")  # D-426: with its position


async def test_d423_the_host_gets_the_items_and_a_price_promo_updates_them():
    rt = await live_runtime(make_ctx())
    try:
        view = await rt.prompter_view_now(await rt.current_segment())
        assert [i["key"] for i in view["items"] if i["kind"] == "price"] == ["live-price", "list-price"]
        sale = next(p for p in rt.catalog.runsheet.promo_ids if (rt.promo(p) and rt.promo(p).changes_prices
                                                                 and CREAM in rt.promo(p).promo_prices))
        await rt.start_promo(sale)
        last = (await events(rt, "prompter.updated"))[-1].payload
        assert [i["key"] for i in last["items"] if i["kind"] == "price"] == [f"sale-price-{sale}", "live-price"]
    finally:
        await close_env(rt)


# ---- D-426: unique item ids; prices back after a promo; the key_facts fallback --------------------------------------


def test_d426_every_item_id_is_unique_with_non_latin_and_repeated_names(catalog):
    from app.models.data import SetOffer

    class View:
        def __getattr__(self, name):
            return getattr(catalog, name)

        @property
        def set_offers(self):
            return [SetOffer(set_id="s1", name="Duo", product_ids=[CREAM], live_price=50.0),
                    SetOffer(set_id="s2", name="Duo", product_ids=[CREAM], live_price=60.0)]

        def get_product(self, pid):
            return catalog.get_product(pid).model_copy(update={
                "cautions": ["Same caution.", "Same caution."],
                "ingredients": [Ingredient(key="item", name="나이아신아마이드", amount="4%"),
                                Ingredient(key="item", name="烟酰胺", amount="2%"),
                                Ingredient(key="glycerin", name="Glycerin"), Ingredient(key="glycerin", name="Glycerin")]})

    ids = [i["id"] for i in prompter_items(View(), CREAM)]
    assert len(ids) == len(set(ids))
    p = [x.passage_id for x in prompter_passages(View(), CREAM)]
    assert p == ids  # the snapshot cites the same unique ids


def test_d426_a_product_without_an_ingredient_list_falls_back_to_key_facts_on_both_sides(catalog):
    from app.models.data import Product

    raw = catalog.get_product(CREAM).model_dump()
    raw.pop("ingredients", None)  # a stored product written before D-423
    bare = Product.model_validate(raw)

    class View:
        def __getattr__(self, name):
            return getattr(catalog, name)

        def get_product(self, pid):
            return bare

    items = prompter_items(View(), CREAM)
    assert [i["key"] for i in items if i["kind"] == "ingredient"] == [
        "ingredient-panthenol", "ingredient-squalane", "ingredient-ceramide_np", "ingredient-sodium_hyaluronate",
        "ingredient-allantoin"]
    assert [(x.passage_id, x.text) for x in prompter_passages(View(), CREAM)] == [(i["id"], i["text"]) for i in items]


async def test_d426_the_prices_come_back_when_a_promo_ends_or_runs_out():
    rt = await live_runtime(make_ctx())
    try:
        sale = next(p for p in rt.catalog.runsheet.promo_ids if (rt.promo(p) and rt.promo(p).changes_prices
                                                                 and CREAM in rt.promo(p).promo_prices))
        prices = lambda ev: [i["key"] for i in ev.payload["items"] if i["kind"] == "price"]  # noqa: E731
        for end in ("operator", "timer"):
            await rt.start_promo(sale)
            assert prices((await events(rt, "prompter.updated"))[-1])[0] == f"sale-price-{sale}"
            if end == "operator":
                await rt.stop_promo(sale)
            else:
                await rt.ctx.scheduler.advance(rt.promo(sale).duration_sec * 1000 + 1000)
            assert prices((await events(rt, "prompter.updated"))[-1]) == ["live-price", "list-price"]
    finally:
        await close_env(rt)


def test_d426_before_the_show_the_view_carries_the_first_product_s_items(catalog):
    from app.logic.prompter import prompter_view

    view = prompter_view(catalog, None)
    first = catalog.next_product(None)
    assert view["items"] and {i["product_id"] for i in view["items"]} == {first}
