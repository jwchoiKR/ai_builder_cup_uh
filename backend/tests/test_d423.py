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
    assert ing[-1]["value"] == "" and ing[0]["id"].endswith("#prompter#ingredient-i1")


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
