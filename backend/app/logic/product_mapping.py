"""Product attribution of comments (DEV_SPEC §8.8 step 6)."""
from __future__ import annotations

from typing import Literal

from ..models.agent_io import CommentTriageOutput
from ..models.data import Intent
from .catalog import Catalog

Basis = Literal["explicit", "context", "content", "unknown", "operator"]
# Questions about the products together: the answer is on each product sheet (set price, which goes
# first), so "both products" falls back to the on-air product instead of "unresolved" (D-043).
SET_INTENTS = frozenset({"set_price", "routine_order"})


def attribute_product(
    text: str,
    triage: CommentTriageOutput,
    context_product_id: str | None,
    catalog: Catalog,
    intent: Intent | None,
) -> tuple[str | None, Basis]:
    scope = intent.product_scope if intent else "single"
    if scope == "none":
        return None, "unknown"  # general question: product null by design, not "unresolved"
    named = catalog.products_meant(text)
    if scope == "multi" and len(named) >= 2:
        return None, "explicit"  # both products named: the comparison stays product-less
    if len(named) == 1:
        return next(iter(named)), "explicit"  # code alias match wins
    if triage.product_basis in ("explicit", "content") and catalog.is_product(triage.product_id):
        return triage.product_id, triage.product_basis
    # D-135 (comment-flow CF01, CF03): a comment that names no product is about the product on air
    # ("ml?", "SPF?", "dry skin here, suitable?"), whatever basis triage gave. Only before the broadcast
    # (no product on air) or when two products are named does it stay unresolved ("Which product?").
    if context_product_id is not None and len(named) == 0:
        return context_product_id, "context"
    if intent is not None and intent.intent in SET_INTENTS and context_product_id is not None:
        return context_product_id, "context"  # D-043: both products named, the set is on each sheet
    if intent is not None and intent.intent in SET_INTENTS and len(named) >= 2:
        # D-135: before the first product is on air: the set is on each sheet, take the first in show order
        return next(p for p in catalog.order if p in named), "explicit"
    return None, "unknown"


def set_question(intent_name: str | None, text: str, catalog: Catalog) -> bool:
    """D-135 (comment-flow CF10): a price question that names both products asks for the set price
    ("cream and serum set price?", "price of cream with ampoule?"); a comparison has its own intent."""
    return intent_name in ("price", "promo") and len(catalog.products_meant(text)) >= 2
