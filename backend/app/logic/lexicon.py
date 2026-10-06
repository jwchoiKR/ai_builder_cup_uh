"""The language-dependent text helpers of one broadcast (JAPAC 0b, D-134).

Built from the language pack (`data/lang/<code>.json`: stopwords, number words, stemming, hedges,
test-qualifier and sentence patterns, reactions) and the market pack (phone numbers). Every guard gets
its Lexicon from the pack it is handed (DataPack.lexicon, Catalog.lexicon, Reflex.lexicon), never from a
module global, so a session can later hold its own (market, language).
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

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
    absence: re.Pattern
    comparison: re.Pattern  # D-248: "> 90", "more than 90", "at least 60": a threshold
    duration_hours: dict[str, float]  # D-174
    phone: re.Pattern  # from the market
    currency: re.Pattern  # D-179: the market's currency symbol before a number ("s$", "rm"), from the market
    scales: dict[str, int] = field(default_factory=dict)  # D-208
    and_word: str | None = None
    affirmation: re.Pattern | None = None  # D-252
    negation_words: tuple[str, ...] = ()
    comparison_kinds: dict[str, re.Pattern] = field(default_factory=dict)  # D-259
    multiplicatives: dict[str, int] = field(default_factory=dict)  # D-262  # D-252: the language's negation cues, to read "I don't agree"

    @classmethod
    def from_packs(cls, lang: LangPack, market: MarketPack) -> "Lexicon":
        lx, p = lang.lexicon, lang.lexicon.patterns
        return cls(
            lang=lang.lang, stopwords=frozenset(lx.stopwords), ones=dict(lx.number_words.ones),
            tens=dict(lx.number_words.tens), decimal_word=lx.number_words.decimal,
            scales=dict(lx.number_words.scales), and_word=lx.number_words.and_word,
            skip_alone=frozenset(lx.number_words.skip_alone), stem_suffixes=tuple(lx.stem.suffixes),
            min_stem=lx.stem.min_stem, prefix_match=lx.prefix_match, unsure=re.compile(p.unsure),
            test_qualifier=re.compile(p.test_qualifier), in_house=re.compile(p.in_house),
            sentence_end=re.compile(p.sentence_end), sentence_split=re.compile(p.sentence_split),
            clause_split=re.compile(p.clause_split), reactions=frozenset(lx.reactions),
            fillers=frozenset(lx.fillers),
            absence=re.compile(r"\b(?:" + "|".join(re.escape(c) for c in lx.absence_cues) + r")\b|\w-free\b", re.I),
            price_contrast=re.compile(r"\b(?:" + "|".join(re.escape(c) for c in lx.price_contrast_cues) + r")\b", re.I),
            comparison=re.compile("|".join([r"[<>≤≥]", *(r"\b" + re.escape(c) + r"\b" for c in lx.comparison_cues)]),
                                  re.I),
            duration_hours=dict(lx.duration_hours),
            exclusion=re.compile(r"\b(?:" + "|".join(re.escape(c) for c in lx.exclusion_cues) + r")\s+(?:the\s+)?$"),
            affirmation=(re.compile(r"\b(?:" + "|".join(re.escape(c) for c in lx.affirmation_cues) + r")\b", re.I)
                         if lx.affirmation_cues else None),
            negation_words=tuple(c.lower() for c in lang.negation_cues),
            multiplicatives={k.lower(): v for k, v in lx.multiplicatives.items()},
            comparison_kinds={k: re.compile("|".join(r"\b" + re.escape(w) + r"\b" for w in ws), re.I)
                              for k, ws in lx.comparison_kinds.items() if ws},
            phone=re.compile(market.phone_pattern),
            currency=re.compile(r"(?<![a-z])" + re.escape(market.currency.symbol.lower().replace("$", "")) + r"\$?(?=\d)"),
        )

    # ---- words and numbers ----------------------------------------------------------------------

    def _below_100(self, tokens: list[str], j: int) -> tuple[int, int] | None:
        w = tokens[j] if j < len(tokens) else None
        if w in self.tens:
            if j + 1 < len(tokens) and tokens[j + 1] in self.ones and self.ones[tokens[j + 1]] < 10:
                return self.tens[w] + self.ones[tokens[j + 1]], j + 2
            return self.tens[w], j + 1
        if w in self.ones:
            return self.ones[w], j + 1
        return None

    def _spoken(self, tokens: list[str], i: int) -> tuple[int, int] | None:
        """D-208 (full review P2: "one hundred nineteen" read as 19): one spoken number from tokens[i], with its
        scale words ("one hundred and nineteen" -> 119, "a hundred" -> 100, "two thousand five hundred" -> 2500).
        Two numbers said one after the other stay two ("five five")."""
        first = self._below_100(tokens, i)
        if first is None:
            if tokens[i] in ("a", "an") and i + 1 < len(tokens) and tokens[i + 1] in self.scales:
                first = (1, i + 1)
            else:
                return None
        total, (cur, j) = 0, first
        while j < len(tokens) and tokens[j] in self.scales:
            scale = self.scales[tokens[j]]
            j += 1
            if scale >= 1000:
                total, cur = total + cur * scale, 0
            else:
                cur *= scale
            k = j + 1 if j < len(tokens) and tokens[j] == self.and_word else j
            nxt = self._below_100(tokens, k)
            if nxt is None:
                break
            cur, j = cur + nxt[0], nxt[1]
        return total + cur, j

    def numbers(self, tokens: list[str]) -> list[str]:
        """Spoken numbers to digits ("twenty four" -> "24", "one hundred nineteen" -> "119"); "4%" -> "4", "percent"."""
        out: list[str] = []
        i = 0
        while i < len(tokens):
            w = tokens[i]
            spoken = self._spoken(tokens, i)
            if spoken is not None:
                out.append(str(spoken[0]))
                i = spoken[1]
                continue
            if w.endswith("%") and w[:-1]:
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
        """Numbers as said or written: "fifty mils" -> {"50"}, "S$36.00" or "RM119.00" -> {"36"}/{"119"}, "4%" -> {"4"},
        "zero point two" -> {"0.2"}. A lone skip word ("one") is ignored."""
        raw = self.currency.sub(" ", normalise(text).replace("$", " ")).split()
        # D-174: "twenty-one" kept its "one": a skip word is dropped only when it stands alone
        tokens = [w for i, w in enumerate(raw) if w not in self.skip_alone or (i > 0 and raw[i - 1] in self.tens)
                  or (i + 1 < len(raw) and raw[i + 1] in self.scales)]  # D-208: "one hundred" is not "one"
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

    def durations(self, text: str) -> list[tuple[str | None, float]]:
        """D-174: each duration said, as (its number as said, or None for "a day", hours): "24 hours" ->
        ("24", 24), "a day" -> (None, 24), "two weeks" -> ("2", 336)."""
        words = self.numbers(normalise(text).split())
        out = []
        for i in range(len(words) - 1):
            unit = self.duration_hours.get(words[i + 1])
            if unit is None:
                continue
            w = words[i]
            if re.fullmatch(r"\d+(\.\d+)?", w):
                out.append((w, float(w) * unit))
            elif w in ("a", "an"):
                out.append((None, unit))
        return out

    # ---- sentences and cues ---------------------------------------------------------------------

    def split_sentences(self, text: str) -> list[str]:
        parts, start = [], 0
        for m in self.sentence_end.finditer(text):
            parts.append(text[start:m.end()].strip())
            start = m.end()
        parts.append(text[start:].strip())
        return [p for p in parts if p]

    def times_numbers(self, text: str) -> set[str]:
        """D-262: multiplicative words as numbers ("twice daily" -> {"2"})."""
        words = set(re.findall(r"\w+", text.lower()))
        return {str(v) for k, v in self.multiplicatives.items() if k in words}

    def comparison_kind(self, text: str) -> str | None:
        """D-259: the kind of threshold a text words ("gt" for "above 40" or "> 40", "ge" for "at least 40").
        D-271: the longest phrase wins, so "40 and above" is "ge", not the "gt" of "above"."""
        for sym, kind in (("≥", "ge"), (">=", "ge"), ("≤", "le"), ("<=", "le"), (">", "gt"), ("<", "lt")):
            if sym in text:
                return kind
        found = [(len(m.group()), kind) for kind, rx in self.comparison_kinds.items() for m in rx.finditer(text)]
        return max(found)[1] if found else None

    def affirms(self, text: str) -> bool:
        """D-252: the line endorses something ("and yes, that's what it does", "I fully agree"); "I don't agree" is
        no endorsement."""
        if self.affirmation is None:
            return False
        for m in self.affirmation.finditer(text):
            before = " ".join(text[:m.start()].lower().split()[-3:])
            if not any(re.search(rf"(?<!\w){re.escape(n)}(?!\w)", before) for n in self.negation_words):
                return True
        return False

    def is_qualified(self, text: str) -> bool:
        """The sentence names our own test ("in our in-house test", "our 48-hour patch test")."""
        return bool(self.test_qualifier.search(text))

    def is_unsure(self, text: str) -> bool:
        """D-110: the speaker hedges or takes it back."""
        return bool(self.unsure.search(text))
