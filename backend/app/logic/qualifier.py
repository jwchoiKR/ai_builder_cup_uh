"""TEST-QUALIFIER (D-105, PLANNING 5.1.3; D-278: was BRAND-TEST-QUALIFIER, a demo brand rule in the market packs):
a test result said without its qualifier. The rule comes with a product's qualified results (its own documents),
never from a market or a demo brand. The judge decides the meaning; this module keeps the rule's alert safe:

- a sentence that already names our own test never gets this alert;
- "Say this instead" is always approved wording (`Product.qualified_results`), never the model's;
- the same result does not show twice while its alert is still active; after a correction a repeat
  alerts again (D-108).
"""
from __future__ import annotations

from collections.abc import Sequence

from ..models.data import LangPack, Product, QualifiedResult, Rule
from ..models.session import Alert
from .lexicon import Lexicon

RULE_ID = "TEST-QUALIFIER"
SOURCE_ID = "PRODUCT_RESULTS"


def rule(lang: LangPack) -> Rule:
    """D-278: the rule for a product that has qualified results; its wording is the language pack's
    "test_qualifier" category (language, not a product's data)."""
    return Rule(rule_id=RULE_ID, source_id=SOURCE_ID, source_ref="the product's test results and their qualifiers",
                title="Test result without its qualifier",
                description=("A result of a test, study or certification (a percentage, a count of participants "
                             "such as '21 of 24', or a measured time such as '12 hours') is said together with its "
                             "qualifier from the product's data: who ran or certified it. This applies whoever ran "
                             "the test."),
                severity="MEDIUM", **lang.categories["test_qualifier"].model_dump())
MIN_COVERAGE = 0.4  # without a matching number, this share of the approved wording must be heard

def result_numbers(r: QualifiedResult, lex: Lexicon) -> set[str]:
    """D-261 (candidate 947084e: a release result held "8.0", or no numbers, so "eight hours" matched nothing): the
    result's numbers normalised, plus every number its statement says (the say line before the qualifier)."""
    from .verify import number_set

    statement = r.say[:r.say.rfind("(")] if "(" in r.say else r.say
    return number_set(" ".join(r.numbers)) | number_set(statement) | lex.spoken_numbers(statement)


def matches_result(text: str, products: Sequence[Product], lex: Lexicon) -> bool:
    """D-295 G4: the line is about a qualified result by the result's own words (tear-free, water-resistant, the
    measured property; numbers left out on both sides), or by two or more of its numbers ("zero out of thirty-two").
    One number alone is no match: "zinc at 2 percent" is not "2 times faster"."""
    heard = lex.content_words(text)
    words_heard = [w for w in heard if not any(ch.isdigit() for ch in w)]
    numbers = {w for w in heard if w.isdigit()} | lex.spoken_numbers(text)
    for p in products:
        for r in p.qualified_results:
            statement = r.say[:r.say.rfind("(")] if "(" in r.say else r.say
            words = [w for w in lex.claim_words(statement) if not any(ch.isdigit() for ch in w)]
            hits = numbers & result_numbers(r, lex)
            # D-299: one decimal number is as specific as two ("SPF 22.5"); one whole number is not ("2 percent")
            if (words and lex.coverage(words, words_heard) >= MIN_COVERAGE) or len(hits) >= 2 or any("." in n for n in hits):
                return True
    return False


def approved_replacement(text: str, on_air: Product, others: Sequence[Product], lex: Lexicon,
                         statement_only: bool = False) -> QualifiedResult | None:
    """The approved result the sentence is about: most matching numbers, then the product on air,
    then most matching words. None when nothing matches well enough (no wording is invented).
    D-295 G4 (`statement_only`): the words are the result's statement without its qualifier; "tear-free" met only 2 of
    the 7 words of "Tear-free formula (tested by Ardent Dental Institute)", so a headline result said bare was
    dropped as matching no result."""
    heard = lex.content_words(text)
    # D-260 (candidate aa995d1: "non-transferring for eight hours" matched no result, so the judge's alert was dropped)
    numbers = {w for w in heard if w.isdigit()} | lex.spoken_numbers(text)
    best, best_key = None, None
    for rank, product in enumerate([on_air, *others]):
        for r in product.qualified_results:
            hits = len(numbers & result_numbers(r, lex))
            say = r.say[:r.say.rfind("(")] if statement_only and "(" in r.say else r.say
            cov = lex.coverage(lex.claim_words(say), heard)
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
