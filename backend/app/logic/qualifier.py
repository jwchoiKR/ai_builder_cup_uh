"""BRAND-TEST-QUALIFIER (D-105, PLANNING 5.1.3): an in-house test number said without "in our
in-house test". The judge decides the meaning; this module keeps the rule's alert safe:

- a sentence that already names our own test never gets this alert;
- "Say this instead" is always approved wording (`Product.qualified_results`), never the model's;
- the same result alerts once per product segment (fewer yellow banners, interview #2).
"""
from __future__ import annotations

import re
from collections.abc import Sequence

from ..models.data import Product, QualifiedResult
from ..models.session import Alert
from .corrections import _claim_words, content_words, coverage

RULE_ID = "BRAND-TEST-QUALIFIER"
MIN_COVERAGE = 0.4  # without a matching number, this share of the approved wording must be heard

# "in our in-house test", "in-house study", "in our 48-hour patch test", "our own study showed"
_QUALIFIED = re.compile(r"\bin-house\b|\bour\b(?:\s+[\w-]+){0,4}?\s+(?:tests?|study|studies|trials?)\b", re.I)


def is_qualified(text: str) -> bool:
    return bool(_QUALIFIED.search(text))


def approved_replacement(text: str, on_air: Product, others: Sequence[Product] = ()) -> QualifiedResult | None:
    """The approved result the sentence is about: most matching numbers, then the product on air,
    then most matching words. None when nothing matches well enough (no wording is invented)."""
    heard = content_words(text)
    numbers = {w for w in heard if w.isdigit()}
    best, best_key = None, None
    for rank, product in enumerate([on_air, *others]):
        for r in product.qualified_results:
            hits = len(numbers & set(r.numbers))
            cov = coverage(_claim_words(r.say), heard)
            if hits == 0 and cov < MIN_COVERAGE:
                continue
            key = (hits, -rank, cov)
            if best_key is None or key > best_key:
                best, best_key = r, key
    return best


def is_repeat(say_instead: str | None, alerts: Sequence[Alert], product_id: str, since: int) -> bool:
    """An alert of this rule with the same approved wording already exists in this product segment."""
    return say_instead is not None and any(
        a.kind == "compliance" and a.rule_id == RULE_ID and a.product_id == product_id
        and a.say_instead == say_instead and a.created_at >= since and a.status != "cleared"
        for a in alerts)
