"""BRAND-TEST-QUALIFIER (D-105, PLANNING 5.1.3): an in-house test number said without "in our
in-house test". The judge decides the meaning; this module keeps the rule's alert safe:

- a sentence that already names our own test never gets this alert;
- "Say this instead" is always approved wording (`Product.qualified_results`), never the model's;
- the same result does not show twice while its alert is still active; after a correction a repeat
  alerts again (D-108).
"""
from __future__ import annotations

from collections.abc import Sequence

from ..models.data import Product, QualifiedResult
from ..models.session import Alert
from .lexicon import Lexicon

RULE_ID = "BRAND-TEST-QUALIFIER"
MIN_COVERAGE = 0.4  # without a matching number, this share of the approved wording must be heard

def result_numbers(r: QualifiedResult, lex: Lexicon) -> set[str]:
    """D-261 (candidate 947084e: a release result held "8.0", or no numbers, so "eight hours" matched nothing): the
    result's numbers normalised, plus every number its statement says (the say line before the qualifier)."""
    from .verify import number_set

    statement = r.say[:r.say.rfind("(")] if "(" in r.say else r.say
    return number_set(" ".join(r.numbers)) | number_set(statement) | lex.spoken_numbers(statement)


def approved_replacement(text: str, on_air: Product, others: Sequence[Product], lex: Lexicon) -> QualifiedResult | None:
    """The approved result the sentence is about: most matching numbers, then the product on air,
    then most matching words. None when nothing matches well enough (no wording is invented)."""
    heard = lex.content_words(text)
    # D-260 (candidate aa995d1: "non-transferring for eight hours" matched no result, so the judge's alert was dropped)
    numbers = {w for w in heard if w.isdigit()} | lex.spoken_numbers(text)
    best, best_key = None, None
    for rank, product in enumerate([on_air, *others]):
        for r in product.qualified_results:
            hits = len(numbers & result_numbers(r, lex))
            cov = lex.coverage(lex.claim_words(r.say), heard)
            if hits == 0 and cov < MIN_COVERAGE:
                continue
            key = (hits, -rank, cov)
            if best_key is None or key > best_key:
                best, best_key = r, key
    return best


def is_repeat(say_instead: str | None, alerts: Sequence[Alert], product_id: str) -> bool:
    """An alert of this rule with the same approved wording is still on the host's screen: no second
    card. Once it is corrected or has ended, a repeat is a new alert (user, 10/5)."""
    return say_instead is not None and any(
        a.kind == "compliance" and a.rule_id == RULE_ID and a.product_id == product_id
        and a.say_instead == say_instead and a.status in ("provisional", "active")
        for a in alerts)
