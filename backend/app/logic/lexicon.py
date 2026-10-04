"""The language-dependent text helpers of one broadcast (JAPAC 0b, D-134).

Built from the language pack (`data/lang/<code>.json`: stopwords, number words, stemming, hedges,
test-qualifier and sentence patterns, reactions) and the market pack (phone numbers). Every guard gets
its Lexicon from the pack it is handed (DataPack.lexicon, Catalog.lexicon, Reflex.lexicon), never from a
module global, so a session can later hold its own (market, language).
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from ..models.data import LangPack, MarketPack
from .reflex import normalise


@dataclass(frozen=True)
class Lexicon:
    lang: str
    stopwords: frozenset[str]
    ones: dict[str, int]
    tens: dict[str, int]
    decimal_word: str
    skip_alone: frozenset[str]  # number words ignored when said alone ("after one use")
    stem_suffixes: tuple[str, ...]
    min_stem: int
    prefix_match: int  # two words match when they share this many first letters (speech-to-text slips)
    unsure: re.Pattern
    test_qualifier: re.Pattern
    in_house: re.Pattern
    sentence_end: re.Pattern
    sentence_split: re.Pattern
    clause_split: re.Pattern
    reactions: frozenset[str]
    exclusion: re.Pattern  # matches when a text ends with an exclusion cue ("..., not")
    fillers: frozenset[str]
    price_contrast: re.Pattern
    phone: re.Pattern  # from the market

    @classmethod
    def from_packs(cls, lang: LangPack, market: MarketPack) -> "Lexicon":
        lx, p = lang.lexicon, lang.lexicon.patterns
        return cls(
            lang=lang.lang, stopwords=frozenset(lx.stopwords), ones=dict(lx.number_words.ones),
            tens=dict(lx.number_words.tens), decimal_word=lx.number_words.decimal,
            skip_alone=frozenset(lx.number_words.skip_alone), stem_suffixes=tuple(lx.stem.suffixes),
            min_stem=lx.stem.min_stem, prefix_match=lx.prefix_match, unsure=re.compile(p.unsure),
            test_qualifier=re.compile(p.test_qualifier), in_house=re.compile(p.in_house),
            sentence_end=re.compile(p.sentence_end), sentence_split=re.compile(p.sentence_split),
            clause_split=re.compile(p.clause_split), reactions=frozenset(lx.reactions),
            fillers=frozenset(lx.fillers),
            price_contrast=re.compile(r"\b(?:" + "|".join(re.escape(c) for c in lx.price_contrast_cues) + r")\b", re.I),
            exclusion=re.compile(r"\b(?:" + "|".join(re.escape(c) for c in lx.exclusion_cues) + r")\s+(?:the\s+)?$"),
            phone=re.compile(market.phone_pattern),
        )

    # ---- words and numbers ----------------------------------------------------------------------

    def numbers(self, tokens: list[str]) -> list[str]:
        """Spoken numbers to digits ("twenty four" -> "24"); "4%" -> "4", "percent"."""
        out: list[str] = []
        i = 0
        while i < len(tokens):
            w = tokens[i]
            if w in self.tens:
                n = self.tens[w]
                if i + 1 < len(tokens) and tokens[i + 1] in self.ones and self.ones[tokens[i + 1]] < 10:
                    n += self.ones[tokens[i + 1]]
                    i += 1
                out.append(str(n))
            elif w in self.ones:
                out.append(str(self.ones[w]))
            elif w.endswith("%") and w[:-1]:
                out += [w[:-1], "percent"]
            else:
                out.append(w)
            i += 1
        return out

    def stem(self, w: str) -> str:
        for suffix in self.stem_suffixes:
            if w.endswith(suffix) and len(w) - len(suffix) >= self.min_stem:
                return w[: -len(suffix)]
        return w

    def content_words(self, text: str) -> list[str]:
        tokens = self.numbers(normalise(text).replace("$", " ").split())
        return [self.stem(w) for w in tokens if w not in self.stopwords]

    def same(self, a: str, b: str) -> bool:
        n = self.prefix_match
        return a == b or (len(a) >= n and len(b) >= n and a[:n] == b[:n])

    def coverage(self, phrase: Sequence[str], heard: Sequence[str]) -> float:
        """Share of the phrase's content words that appear among the heard words."""
        if not phrase:
            return 0.0
        return sum(1 for p in phrase if any(self.same(p, h) for h in heard)) / len(phrase)

    def claim_words(self, claim: str) -> list[str]:
        """Content words of an approved claim, without the '*' and the in-house-test qualifier."""
        return self.content_words(self.in_house.sub(" ", claim.replace("*", " ")))

    def spoken_numbers(self, text: str) -> set[str]:
        """Numbers as said or written: "fifty mils" -> {"50"}, "S$36.00" -> {"36"}, "4%" -> {"4"},
        "zero point two" -> {"0.2"}. A lone skip word ("one") is ignored."""
        tokens = [w for w in normalise(text).replace("$", " ").split() if w not in self.skip_alone]
        words = self.numbers(tokens)
        merged: list[str] = []  # D-116: spoken decimals, "five point five" -> "5.5"
        i = 0
        while i < len(words):
            if (i + 2 < len(words) and words[i + 1] == self.decimal_word and words[i].isdigit()
                    and words[i + 2].isdigit()):
                merged.append(f"{words[i]}.{words[i + 2]}")
                i += 3
            else:
                merged.append(words[i])
                i += 1
        out = set()
        for w in merged:
            if re.fullmatch(r"\d+(\.\d+)?", w):
                out.add(w.rstrip("0").rstrip(".") if "." in w else w)
        return out

    # ---- sentences and cues ---------------------------------------------------------------------

    def split_sentences(self, text: str) -> list[str]:
        parts, start = [], 0
        for m in self.sentence_end.finditer(text):
            parts.append(text[start:m.end()].strip())
            start = m.end()
        parts.append(text[start:].strip())
        return [p for p in parts if p]

    def is_qualified(self, text: str) -> bool:
        """The sentence names our own test ("in our in-house test", "our 48-hour patch test")."""
        return bool(self.test_qualifier.search(text))

    def is_unsure(self, text: str) -> bool:
        """D-110: the speaker hedges or takes it back."""
        return bool(self.unsure.search(text))
