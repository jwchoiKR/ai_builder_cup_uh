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


def _left(ms: int) -> str:
    return f"{-(-ms // 60_000)} min" if ms >= 60_000 else f"{max(0, ms) // 1000} s"


def promo_cue(promo: Promo, catalog: Catalog, active_price: Promo | None, ends_at: int, now: int,
              offers: list[Promo] | tuple = ()) -> str | None:
    """D-210 (full review P2): the AI PD's promo card text, built from the live state every time: the promo's own
    prices and the time left, never the stored "for the next 10 minutes". Any other promo text (a notice) is shown
    only when every number in it is a current price or offer term; "Set: S$62" during a time sale is dropped."""
    from .verify import number_set

    left = _left(ends_at - now)
    if promo.changes_prices:
        names = {p.product_id: p.name for p in catalog.products} | {s.set_id: s.name for s in catalog.set_offers}
        prices = "; ".join(f"{names[pid]} {catalog.money(v)}" for pid, v in promo.promo_prices.items() if pid in names)
        pct = (f"extra {promo.discount_pct_off_live_price:g}% off now: "
               if promo.discount_pct_off_live_price is not None else "now: ")
        return f"{promo.title}: {pct}{prices}. {left} left."
    if promo.min_spend is not None:
        return f"{promo.viewer_text}. {left} left."
    ids = [p.product_id for p in catalog.products] + [s.set_id for s in catalog.set_offers]
    allowed = set().union(*(number_set(catalog.price_display(pid, active_price)) for pid in ids),
                          *(number_set(f"{o.min_spend}") for o in offers if o.min_spend is not None))
    return promo.viewer_text if number_set(promo.viewer_text) <= allowed else None


def price_promo(promo: Promo | None) -> Promo | None:
    return promo if promo is not None and promo.changes_prices else None


def promo_state(promo: Promo | None) -> str:
    p = price_promo(promo)
    return p.promo_id if p else "none"
