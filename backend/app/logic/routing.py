"""Question routing from intents.json (DEV_SPEC §8.9.2). First match wins."""
from __future__ import annotations

from typing import Literal

from ..models.data import Intent

Route = Literal["AUTO", "HOST", "OPERATOR"]


def route_for(intent: Intent, product_id: str | None) -> tuple[Route, str]:
    # D-113: question cards go to the host, sensitive ones included; the host asks "Which product?"
    # when the product is unclear. General questions (shipping, returns, ...) keep their intent route.
    if product_id is None and intent.product_scope == "single":
        return "HOST", "unresolved_product"
    if intent.sensitive:
        return "HOST", "sensitive"
    return intent.route, "intent"


def is_composable(intent: Intent, product_id: str | None) -> bool:
    """§7.6: single-product intents with a resolved product, or multi-product intents."""
    return (intent.product_scope == "single" and product_id is not None) or intent.product_scope == "multi"
