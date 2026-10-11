"""An onboarded product with several priced options: every option reaches the show's product and the host prompter
(the fact checker's snapshot), and the first option is the main price. Made-up product."""
from __future__ import annotations

from app.logic.catalog import Catalog
from app.logic.prompter import prompter_items

from .test_d448 import CREAM, _pack


def test_every_price_option_reaches_the_prompter():
    info = CREAM | {"variants": [{"label": "50 mL", "list_price": "42.00", "live_price": "36.00"},
                                 {"label": "100 mL", "list_price": None, "live_price": "60.00"}]}
    pack, key = _pack(info, "102")
    [p] = pack.products.products
    assert [(v.label, v.live_price, v.list_price) for v in p.variants] == [("50 mL", 36.0, 42.0), ("100 mL", 60.0, 60.0)]
    assert (p.live_price, p.list_price) == (36.0, 42.0)
    catalog = Catalog(pack, key)
    texts = [i["text"] for i in prompter_items(catalog, p.product_id) if i["kind"] == "price"]
    assert len(texts) == 3 and any("100 mL" in t and "60" in t for t in texts)  # 100 mL has no separate list price


def test_one_unnamed_price_shows_as_before():
    info = CREAM | {
        "variants": [{"label": "", "list_price": "42.00", "live_price": "36.00"}]}
    pack, _ = _pack(info, "103")
    [p] = pack.products.products
    assert (p.variants, p.live_price, p.list_price) == ([], 36.0, 42.0)
