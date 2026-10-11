"""Prompter point coverage (DEV_SPEC §8.7.1). Covered points are never removed."""
from __future__ import annotations

import re
from collections.abc import Sequence

from ..models.data import Ingredient, Passage, PrompterPoint
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
                  overrides: dict[str, list[PrompterPoint]] | None = None, promo=None) -> dict:
    """Payload of `prompter.updated` and the /state `prompter` block. D-423: with the item list the host renders as is
    (the fact checker's snapshot is the same list)."""
    if segment is None:  # before the show: the first product's items (the host sees it before the start)
        first = catalog.next_product(None)
        return {"product_id": None, "segment_id": None, "next_product_id": first, "points": [],
                "covered_point_ids": [], "ticked_item_ids": [], "required_total": 0, "required_covered": 0,
                "items": prompter_items(catalog, first, overrides, promo) if first else []}
    required = required_ids(catalog, segment.product_id)
    covered = list(segment.covered_point_ids)
    return {
        "product_id": segment.product_id,
        "segment_id": segment.segment_id,
        "next_product_id": catalog.next_product(segment.product_id),
        "points": [{"point_id": p.point_id, "text": p.text, "required": p.point_id in required,
                    "covered": p.point_id in covered} for p in points_of(catalog, segment.product_id, overrides)],
        "covered_point_ids": covered,
        "ticked_item_ids": list(segment.ticked_item_ids),  # D-372
        "required_total": len(required),
        "required_covered": sum(1 for p in required if p in covered),
        "items": prompter_items(catalog, segment.product_id, overrides, promo),  # D-423
    }


# ---- D-360: the prompter's display snapshot, the fact checker's only source ---------------------------------------

# D-423: the shipped demo catalog keeps its ingredient amounts among other key facts (volume, prices, pH); an amount
# (a share or a mass) marks an ingredient there. Onboarded products list their ingredients (Product.ingredients).
AMOUNT = re.compile(r"^\d+(\.\d+)?\s*(%|mg|mcg|µg|g|iu)$", re.IGNORECASE)


def _ingredient_name(key: str) -> str:
    return " ".join(w.upper() if len(w) <= 2 else w[0].upper() + w[1:] for w in key.split("_"))


def prompter_items(catalog: Catalog, product_id: str, overrides: dict[str, list[PrompterPoint]] | None = None,
                   promo=None) -> list[dict]:
    """D-423 (user): the host prompter's item list, built once. The host renders it as is and the fact checker's
    snapshot is the same list (`prompter_passages`). Each item: `id` (the snapshot passage id, stable for ticks; a
    promo's items carry its id, D-372), `key`, `section`, `kind` (price, set, ingredient, point, caution), `text` (the
    passage text) and the parts the screen shows. Nothing is cut: every set offer of the product, every ingredient
    (one without an amount shows its name only), every point (D-388) and every caution; no test result."""
    from ..agents.fact_checker import CLAIMS_SECTION

    p = catalog.get_product(product_id)
    out: list[dict] = []

    def add(section: str, kind: str, key: str, text: str, **show) -> None:
        out.append({"id": f"{p.code}#prompter#{key}", "key": key, "product_id": product_id, "section": section,
                    "kind": kind, "text": text, **show})

    price = "Price & offers"
    sale = promo is not None and product_id in getattr(promo, "promo_prices", {})
    if sale:
        now = catalog.price_display(product_id, promo)
        add(price, "price", f"sale-price-{promo.promo_id}", f"Time sale price: {now}", label="TIME SALE", value=now,
            main=True)
        add(price, "price", "live-price", f"Live price: {catalog.money(p.live_price)}", label="Live price",
            value=catalog.money(p.live_price))
    elif p.variants:  # every priced option, each with its own live price (and list price when it differs)
        for i, v in enumerate(p.variants, 1):
            live, lst = catalog.money(v.live_price), catalog.money(v.list_price)
            add(price, "price", f"live-price-{i}", f"Live price ({v.label}): {live}", label=v.label, value=live,
                main=True)
            if v.list_price != v.live_price:
                add(price, "price", f"list-price-{i}", f"List price ({v.label}): {lst}", label="List price", value=lst)
    else:
        add(price, "price", "live-price", f"Live price: {catalog.money(p.live_price)}", label="LIVE PRICE",
            value=catalog.money(p.live_price), main=True)
        add(price, "price", "list-price", f"List price: {catalog.money(p.list_price)}", label="List price",
            value=catalog.money(p.list_price))
    for s in (x for x in catalog.set_offers if product_id in x.product_ids):  # every set offer
        promo_set = sale and s.set_id in promo.promo_prices
        value = catalog.money(promo.promo_prices[s.set_id] if promo_set else s.live_price)
        add(price, "set", f"set-{s.set_id}-{promo.promo_id}" if promo_set else f"set-{s.set_id}",
            f"Set {s.name}: {value}", label=s.short_name or s.name, value=value)
    # D-426: an onboarded product's ingredient keys can repeat (a name with no Latin letters slugs to "item"; two
    # ingredients can share a name), so its item key carries the ingredient's position in the release, stable for the
    # same release; the shipped demo's key_facts keys are unique already
    ingredients = ([i.model_copy(update={"key": f"{n}-{i.key}"}) for n, i in enumerate(p.ingredients, 1)]
                   or [Ingredient(key=k, name=_ingredient_name(k), amount=v.strip())
                       for k, v in p.key_facts.items() if AMOUNT.match(v.strip())])
    for i in ingredients:
        add("Ingredients", "ingredient", f"ingredient-{i.key}", f"{i.name}: {i.amount}" if i.amount else i.name,
            name=i.name, value=i.amount)
    for pt in points_of(catalog, product_id, overrides):
        add(CLAIMS_SECTION, "point", f"point-{pt.point_id}", pt.text)
    for i, c in enumerate(p.cautions, 1):
        add("Cautions", "caution", f"caution-{i}", c)
    return out


def prompter_passages(catalog: Catalog, product_id: str, overrides: dict[str, list[PrompterPoint]] | None = None,
                      promo=None) -> list[Passage]:
    """D-360/D-423: the fact checker's snapshot: the prompter's item list, as passages. Nothing else of the record
    reaches the fact checker."""
    return [Passage(passage_id=i["id"], product_id=product_id, doc="prompter", section=i["section"], text=i["text"])
            for i in prompter_items(catalog, product_id, overrides, promo)]


def tick_item(passage_id: str | None) -> bool:
    """D-372: a snapshot item the fact checker's verdict ticks: a price line, an ingredient amount or a caution (the
    points to say stay with the context judge)."""
    return bool(passage_id) and "#prompter#" in passage_id and "#prompter#point-" not in passage_id
