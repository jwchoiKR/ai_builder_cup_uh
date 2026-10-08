"""Prompter point coverage (DEV_SPEC §8.7.1). Covered points are never removed."""
from __future__ import annotations

import re
from collections.abc import Sequence

from ..models.data import Passage, PrompterPoint
from ..models.session import Segment, Session
from .catalog import Catalog


def points_of(catalog: Catalog, product_id: str, overrides: dict[str, list[PrompterPoint]] | None = None) -> list[PrompterPoint]:
    return (overrides or {}).get(product_id) or catalog.get_product(product_id).prompter_points


def apply_coverage(
    covered_ids: Sequence[str], segment: Segment, session: Session, catalog: Catalog,
    overrides: dict[str, list[PrompterPoint]] | None = None,
) -> tuple[list[str], dict[str, list[str]]]:
    """Add covered points: on-air product -> segment; next product -> session.pre_covered.
    Returns (newly covered on air, newly pre-covered by product)."""
    on_air = segment.product_id
    nxt = catalog.next_product(on_air)
    on_air_ids = {p.point_id for p in points_of(catalog, on_air, overrides)}
    next_ids = {p.point_id for p in points_of(catalog, nxt, overrides)} if nxt else set()
    added_on_air: list[str] = []
    added_next: dict[str, list[str]] = {}
    for pid in covered_ids:
        if pid in on_air_ids and pid not in segment.covered_point_ids:
            segment.covered_point_ids.append(pid)
            added_on_air.append(pid)
        elif pid in next_ids:
            pre = session.pre_covered.setdefault(nxt, [])
            if pid not in pre:
                pre.append(pid)
                added_next.setdefault(nxt, []).append(pid)
    return added_on_air, added_next


def required_ids(catalog: Catalog, product_id: str) -> list[str]:
    return list(catalog.runsheet_item(product_id).required_point_ids)


def missing_required(catalog: Catalog, segment: Segment) -> list[str]:
    return [p for p in required_ids(catalog, segment.product_id) if p not in segment.covered_point_ids]


def prompter_view(catalog: Catalog, segment: Segment | None,
                  overrides: dict[str, list[PrompterPoint]] | None = None) -> dict:
    """Payload of `prompter.updated` and the /state `prompter` block."""
    if segment is None:
        return {"product_id": None, "segment_id": None, "next_product_id": catalog.next_product(None), "points": [],
                "covered_point_ids": [], "required_total": 0, "required_covered": 0}
    required = required_ids(catalog, segment.product_id)
    covered = list(segment.covered_point_ids)
    return {
        "product_id": segment.product_id,
        "segment_id": segment.segment_id,
        "next_product_id": catalog.next_product(segment.product_id),
        "points": [{"point_id": p.point_id, "text": p.text, "required": p.point_id in required,
                    "covered": p.point_id in covered} for p in points_of(catalog, segment.product_id, overrides)],
        "covered_point_ids": covered,
        "required_total": len(required),
        "required_covered": sum(1 for p in required if p in covered),
    }


# ---- D-360: the prompter's display snapshot, the fact checker's only source ---------------------------------------

SHOWN_AMOUNT = re.compile(r"^\d+(\.\d+)?\s*(%|mg|mcg|µg|g|iu)$", re.IGNORECASE)  # the host screen's PERCENT
SHOWN_INGREDIENTS = 4  # the host screen's MAX_INGREDIENTS
SHOWN_CAUTIONS = 4  # the host screen's CAUTIONS_SHOWN (the rest sit behind "+N more", not shown)


def _ingredient_name(key: str) -> str:
    return " ".join(w.upper() if len(w) <= 2 else w[0].upper() + w[1:] for w in key.split("_"))


def prompter_passages(catalog: Catalog, product_id: str, overrides: dict[str, list[PrompterPoint]] | None = None,
                      promo=None) -> list[Passage]:
    """What the host prompter shows for this product, as passages (the same rules as the host screen's
    ProductPanel): the price (a time-sale price while a price promo runs), the list or live price, the set price,
    the first ingredient amounts, the points (minus a price point that is not required) and the first cautions. D-361:
    exactly what it renders: no caution behind "+N more", no test result (the prompter shows none). Nothing else of
    the record reaches the fact checker."""
    from ..agents.fact_checker import CLAIMS_SECTION

    p = catalog.get_product(product_id)
    out: list[Passage] = []

    def add(section: str, key: str, text: str) -> None:
        out.append(Passage(passage_id=f"{p.code}#prompter#{key}", product_id=product_id, doc="prompter",
                           section=section, text=text))

    sale = promo is not None and product_id in getattr(promo, "promo_prices", {})
    if sale:
        add("Price & offers", "sale-price", f"Time sale price: {catalog.price_display(product_id, promo)}")
        add("Price & offers", "live-price", f"Live price: {catalog.money(p.live_price)}")
    else:
        add("Price & offers", "live-price", f"Live price: {catalog.money(p.live_price)}")
        add("Price & offers", "list-price", f"List price: {catalog.money(p.list_price)}")
    for s in catalog.set_offers:
        if product_id in s.product_ids:
            value = promo.promo_prices.get(s.set_id) if sale and s.set_id in promo.promo_prices else s.live_price
            add("Price & offers", f"set-{s.set_id}", f"Set {s.name}: {catalog.money(value)}")
    shown = [(k, v) for k, v in p.key_facts.items() if SHOWN_AMOUNT.match(v.strip())][:SHOWN_INGREDIENTS]
    for k, v in shown:
        add("Ingredients", f"ingredient-{k}", f"{_ingredient_name(k)}: {v}")
    symbol = catalog.pack.products.currency_symbol
    for pt in points_of(catalog, product_id, overrides):
        if pt.required or not symbol or symbol not in pt.text:
            add(CLAIMS_SECTION, f"point-{pt.point_id}", pt.text)  # D-338: never a correction source
    for i, c in enumerate(p.cautions[:SHOWN_CAUTIONS], 1):
        add("Cautions", f"caution-{i}", c)
    return out
