"""Product attribution of comments (DEV_SPEC §8.8 step 6)."""
from __future__ import annotations

from typing import Literal

from ..models.agent_io import CommentTriageOutput
from ..models.data import Intent
from .catalog import Catalog

Basis = Literal["explicit", "context", "content", "unknown", "operator"]
# Questions about the products together: the answer is on each product sheet (set price, which goes
# first), so "both products" falls back to the on-air product instead of "unresolved" (D-043).
SET_INTENTS = frozenset({"set_price", "order_of_use"})


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
    if intent is not None and intent.intent in SET_INTENTS:
        # D-147 (comment-flow CF10): the set is the same whichever product the comment names, so a set
        # question always uses one product: the one on air, else the first named (or first) in show order
        if context_product_id is not None:
            return context_product_id, "context"
        pid = next((p for p in catalog.order if p in named), catalog.order[0] if catalog.order else None)
        return pid, "explicit" if named else "unknown"
    if scope == "multi" and len(named) >= 2:
        return None, "explicit"  # both products named: the comparison stays product-less
    # D-213 (full review P3): triage decides the product; code only checks that the id is a product. The alias
    # matches are candidates, used when triage gave none ("Not the cream, how much is this?" is triage's call).
    if triage.product_basis in ("explicit", "content") and catalog.is_product(triage.product_id):
        return triage.product_id, triage.product_basis
    if len(named) == 1:
        return next(iter(named)), "explicit"
    if len(named) >= 2 and context_product_id in named:
        return context_product_id, "context"  # a word that fits several products: the one on air, if it is one
    # D-135 (comment-flow CF01, CF03): a comment that names no product is about the product on air
    # ("ml?", "SPF?", "dry skin here, suitable?"), whatever basis triage gave. Only before the broadcast
    # (no product on air) or when the named products leave it open does it stay unresolved ("Which product?").
    if context_product_id is not None and len(named) == 0:
        return context_product_id, "context"
    return None, "unknown"


def set_question(intent_name: str | None, text: str, catalog: Catalog) -> bool:
    """D-135 (comment-flow CF10): a price question that names both products asks for the set price
    ("cream and serum set price?", "price of cream with ampoule?"); a comparison has its own intent."""
    return intent_name in ("price", "promo") and len(catalog.products_meant(text)) >= 2
