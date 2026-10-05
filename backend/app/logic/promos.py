"""Promotions (DEV_SPEC §8.10). Promo prices are precomputed in promos.json and never computed here."""
from __future__ import annotations

from ..models.data import Passage, Promo
from .catalog import Catalog


def promo_passage(promo: Promo, catalog: Catalog) -> Passage:
    """The active promo as a citable pseudo-passage `PROMO#<promo_id>`."""
    names = {p.product_id: p.name for p in catalog.products} | {s.set_id: s.name for s in catalog.set_offers}
    runs = f" Runs for {round(promo.duration_sec / 60)} minutes." if promo.duration_sec else ""
    if not promo.changes_prices:  # D-168: an offer (a gift over a spend) in its own viewer wording
        return Passage(passage_id=f"PROMO#{promo.promo_id}", product_id="*", doc="", section="Active promotion",
                       text=f"{promo.viewer_text}.{runs}")
    if promo.kind == "time_sale" and promo.discount_pct_off_live_price is not None:
        label = f"Time sale price (extra {promo.discount_pct_off_live_price:g}% off the live price)"
    else:
        label = promo.title
    prices = "; ".join(f"{names[pid]} {catalog.money(v)}" for pid, v in promo.promo_prices.items())
    # D-164 (local SEED2 replay): "How long will the sale last?" had nothing to cite; the duration is promo data
    return Passage(passage_id=f"PROMO#{promo.promo_id}", product_id="*", doc="", section="Active promotion",
                   text=f"{label}: {prices}.{runs}")


def price_promo(promo: Promo | None) -> Promo | None:
    return promo if promo is not None and promo.changes_prices else None


def promo_state(promo: Promo | None) -> str:
    p = price_promo(promo)
    return p.promo_id if p else "none"
