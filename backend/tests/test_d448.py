"""D-448: the approved product's brand and category reach the show's product and the judges' inputs: CURRENT_PRODUCT
carries both when present, and the context judge's run sheet carries each product's category as its type word (so a
move to the next product said by its category, "next, the ampoule", can be recognised). Made-up products."""
from __future__ import annotations

from app.agents import inputs
from app.logic.catalog import Catalog
from app.onboarding.product_show import product_pack, show_key

from .helpers import make_ctx

CREAM = {"brand": "Lunelle", "product_name": "Hydra Calm Cream", "category": "face cream", "currency": "SGD",
         "variants": [{"label": "", "list_price": "42.00", "live_price": "36.00"}], "points": [{"text": "5% panthenol.", "required": True}]}


def _pack(info: dict, n: str = "101"):
    ctx = make_ctx()
    try:
        key = show_key(f"prd_000000000{n}", f"reg_000000000{n}")
        return product_pack(ctx.pack_for(ctx.settings.MARKET, ctx.settings.BROADCAST_LANGUAGE)[0], info, key), key
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()


def test_d448_the_pack_carries_the_brand_and_the_category():
    pack, _ = _pack(CREAM)
    [p] = pack.products.products
    assert (p.brand, p.category) == ("Lunelle", "face cream")
    no_category, _ = _pack({k: v for k, v in CREAM.items() if k != "category"})
    assert no_category.products.products[0].category == ""  # optional: absent is left out


def test_d448_current_product_and_the_run_sheet_name_them():
    pack, key = _pack(CREAM)
    catalog = Catalog(pack, key)
    pid = catalog.order[0]
    cur = inputs.current_product_json(catalog, pid)
    assert (cur["brand"], cur["category"]) == ("Lunelle", "face cream")
    [row] = inputs.run_sheet_compact_json(catalog, pid, {})  # as the live path builds it
    assert (row["status"], row["type"]) == ("on_air", "face cream")
    bare, bare_key = _pack({k: v for k, v in CREAM.items() if k != "category"}, "102")
    bare_catalog = Catalog(bare, bare_key)
    assert "category" not in inputs.current_product_json(bare_catalog, bare_catalog.order[0])
    assert inputs.run_sheet_compact_json(bare_catalog, bare_catalog.order[0], {})[0]["type"] is None
