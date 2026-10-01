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
    named = catalog.products_mentioned(text)
    if scope == "multi" and len(named) >= 2:
        return None, "explicit"  # both products named: the comparison stays product-less
    if len(named) == 1:
        return next(iter(named)), "explicit"  # code alias match wins
    if triage.product_basis in ("explicit", "content") and catalog.is_product(triage.product_id):
        return triage.product_id, triage.product_basis
    if triage.product_basis == "context" and context_product_id is not None:
        return context_product_id, "context"
    if intent is not None and intent.intent in SET_INTENTS and context_product_id is not None:
        return context_product_id, "context"
    return None, "unknown"
