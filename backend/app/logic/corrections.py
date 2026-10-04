"""Compliance correction check (D-089).

The judge lists the alerts an utterance corrects (§8.4.5). An apology alone ("I'm sorry", "let me
correct that") is not a correction: the host must actually fix what was said. A correction counts
only when the utterance
  1. says an approved statement instead: the alert's say_instead or one of the product's approved
     claims, with at least CLAIM_MIN of its content words heard (speech-to-text slips allowed), or
  2. retracts the claim: a negation cue plus at least RETRACT_MIN of the flagged span's content words
     ("it won't make your wrinkles disappear"), or a negated trigger phrase of the alert's own rule
     ("cosmetic results are not permanent" after "permanently fixed for good", D-104).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..models.session import Alert
from .reflex import Reflex

CLAIM_MIN = 0.6
RETRACT_MIN = 0.5
def says_claim(text: str, claim: str, reflex: Reflex) -> bool:
    """The host said this approved wording: CLAIM_MIN of its content words in one clause, every number
    it has, not negated in that clause, and its "in our in-house test" qualifier when it has one
    (D-117 B2: word overlap alone let "it does NOT keep skin hydrated ..." count)."""
    lex = reflex.lexicon
    words = lex.claim_words(claim)
    if len(words) < 2:
        return False
    numbers = {w for w in words if w.isdigit()}
    needs_qualifier = "*" in claim or bool(lex.in_house.search(claim))
    for clause in lex.clause_split.split(text):
        heard = lex.content_words(clause)
        if lex.coverage(words, heard) < CLAIM_MIN or not numbers <= set(heard):
            continue
        if reflex.has_negation(clause) and not reflex.has_negation(claim):
            continue
        if needs_qualifier and not lex.is_qualified(text):
            continue
        return True
    return False


def says_the_replacement(text: str, alert: Alert, reflex: Reflex) -> bool:
    """D-098: the host said the alert's "Say this instead" wording (the screen's own instruction).
    This corrects the alert even when the judge did not list it."""
    return says_claim(text, alert.say_instead or "", reflex)


@dataclass(frozen=True)
class CorrectionCheck:
    ok: bool
    reason: str  # "approved_statement", "retraction" or "no_correcting_content"


def check_correction(text: str, alert: Alert, approved_claims: Sequence[str], reflex: Reflex) -> CorrectionCheck:
    lex = reflex.lexicon
    heard = lex.content_words(text)
    for claim in [alert.say_instead or "", *approved_claims]:
        if says_claim(text, claim, reflex):
            return CorrectionCheck(True, "approved_statement")
    span = lex.content_words(alert.span or "")
    if span and reflex.has_negation(text) and lex.coverage(span, heard) >= RETRACT_MIN:
        return CorrectionCheck(True, "retraction")
    if any(h.rule_id == alert.rule_id and h.negated for h in reflex.scan(text)):
        return CorrectionCheck(True, "retraction")
    return CorrectionCheck(False, "no_correcting_content")
