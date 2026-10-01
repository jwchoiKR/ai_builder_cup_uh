"""Compliance correction check (D-089).

The judge lists the alerts an utterance corrects (§8.4.5). An apology alone ("I'm sorry", "let me
correct that") is not a correction: the host must actually fix what was said. A correction counts
only when the utterance
  1. says an approved statement instead: the alert's say_instead or one of the product's approved
     claims, with at least CLAIM_MIN of its content words heard (speech-to-text slips allowed), or
  2. retracts the claim: a negation cue plus at least RETRACT_MIN of the flagged span's content words
     ("it won't make your wrinkles disappear").
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from ..models.session import Alert
from .reflex import Reflex, normalise

CLAIM_MIN = 0.6
RETRACT_MIN = 0.5
_IN_HOUSE = re.compile(r"\b(in our )?in-house (test|study)\b", re.I)

STOPWORDS = frozenset("""
a an the it its it's this that these those is are was were be been being to of for and or but in on at by from
with as so just very up out your you you're our we my me i i'm im oh sorry apologies apologise apologize let let's
correct correction mean meant actually what said say saying help helps helped can will would should could
do does did get gets also more all any some there here now then than one ones really please okay ok yeah yes well
""".split())

_ONES = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
         "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
         "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
         "ninety": 90}


def _numbers(tokens: list[str]) -> list[str]:
    """Spoken numbers to digits ("twenty four" -> "24"); "4%" -> "4", "percent"."""
    out: list[str] = []
    i = 0
    while i < len(tokens):
        w = tokens[i]
        if w in _TENS:
            n = _TENS[w]
            if i + 1 < len(tokens) and tokens[i + 1] in _ONES and _ONES[tokens[i + 1]] < 10:
                n += _ONES[tokens[i + 1]]
                i += 1
            out.append(str(n))
        elif w in _ONES:
            out.append(str(_ONES[w]))
        elif w.endswith("%") and w[:-1]:
            out += [w[:-1], "percent"]
        else:
            out.append(w)
        i += 1
    return out


def _stem(w: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 4:
            return w[: -len(suffix)]
    return w


def content_words(text: str) -> list[str]:
    tokens = _numbers(normalise(text).replace("$", " ").split())
    return [_stem(w) for w in tokens if w not in STOPWORDS]


def _same(a: str, b: str) -> bool:
    return a == b or (len(a) >= 5 and len(b) >= 5 and a[:5] == b[:5])


def coverage(phrase: Sequence[str], heard: Sequence[str]) -> float:
    """Share of the phrase's content words that appear among the heard words."""
    if not phrase:
        return 0.0
    return sum(1 for p in phrase if any(_same(p, h) for h in heard)) / len(phrase)


def _claim_words(claim: str) -> list[str]:
    """Content words of an approved claim, without the '*' and the in-house-test qualifier."""
    return content_words(_IN_HOUSE.sub(" ", claim.replace("*", " ")))


@dataclass(frozen=True)
class CorrectionCheck:
    ok: bool
    reason: str  # "approved_statement", "retraction" or "no_correcting_content"


def check_correction(text: str, alert: Alert, approved_claims: Sequence[str], reflex: Reflex) -> CorrectionCheck:
    heard = content_words(text)
    for claim in [alert.say_instead or "", *approved_claims]:
        words = _claim_words(claim)
        if len(words) >= 2 and coverage(words, heard) >= CLAIM_MIN:
            return CorrectionCheck(True, "approved_statement")
    span = content_words(alert.span or "")
    if span and reflex.has_negation(text) and coverage(span, heard) >= RETRACT_MIN:
        return CorrectionCheck(True, "retraction")
    return CorrectionCheck(False, "no_correcting_content")
