"""Reflex scan (DEV_SPEC §8.3): fast word-boundary match of rule reflex phrases.

Reflex never raises a full-screen alert by itself; it creates provisional alerts for the judge to
confirm, and it guards AI answers (§8.9.4), operator replies (§8.13) and prompter drafts (§7.7).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..models.data import ClaimRulesFile

_QUOTES = str.maketrans({"‘": "'", "’": "'", "‛": "'", "′": "'",
                         "“": '"', "”": '"', "‟": '"'})
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def normalise(text: str) -> str:
    """Lowercase, straight quotes, punctuation stripped except apostrophes, %, $ and '.' inside
    numbers, whitespace collapsed."""
    t = text.lower().translate(_QUOTES)
    out = []
    for i, ch in enumerate(t):
        if ch.isalnum() or ch.isspace() or ch in "'%$":
            out.append(ch)
        elif ch == "." and 0 < i < len(t) - 1 and t[i - 1].isdigit() and t[i + 1].isdigit():
            out.append(ch)
        else:
            out.append(" ")
    return re.sub(r"\s+", " ", "".join(out)).strip()


@dataclass(frozen=True)
class ReflexHit:
    rule_id: str
    severity: str
    phrase: str
    sentence: int  # index of the sentence in the text
    start: int  # offsets in the normalised sentence
    end: int
    negated: bool  # negation cue within the 4 tokens before the hit
    quoted: bool  # quote cue earlier in the same sentence


class Reflex:
    def __init__(self, policy: ClaimRulesFile) -> None:
        self._phrases: list[tuple[str, str, str, re.Pattern]] = []
        for rule in policy.rules:
            for phrase in rule.reflex_phrases:
                norm = normalise(phrase)
                self._phrases.append((rule.rule_id, rule.severity, norm, re.compile(rf"\b{re.escape(norm)}\b")))
        self._negations = [re.compile(rf"\b{re.escape(normalise(c))}\b") for c in policy.negation_cues]
        self._quotes = [re.compile(rf"\b{re.escape(normalise(c))}\b") for c in policy.quote_cues]

    def scan(self, text: str) -> list[ReflexHit]:
        hits: list[ReflexHit] = []
        for si, sentence in enumerate(s for s in _SENTENCE_SPLIT.split(text) if s.strip()):
            norm = normalise(sentence)
            for rule_id, severity, phrase, rx in self._phrases:
                for m in rx.finditer(norm):
                    before = norm[: m.start()]
                    window = " ".join(before.split()[-4:])
                    hits.append(ReflexHit(
                        rule_id=rule_id, severity=severity, phrase=phrase, sentence=si,
                        start=m.start(), end=m.end(),
                        negated=any(n.search(window) for n in self._negations),
                        quoted=any(q.search(before) for q in self._quotes),
                    ))
        return hits

    def first_hit(self, text: str) -> ReflexHit | None:
        hits = self.scan(text)
        return hits[0] if hits else None

    def has_negation(self, text: str) -> bool:
        """Any negation cue of the policy anywhere in the text."""
        norm = normalise(text)
        return any(n.search(norm) for n in self._negations)
