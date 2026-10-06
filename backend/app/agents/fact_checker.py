"""FactChecker agent (DEV_SPEC §7.4): checks product facts in one host sentence against the sheets."""
from __future__ import annotations

import contextvars
import logging
import re
from decimal import Decimal
from collections.abc import Sequence
from dataclasses import dataclass, field

from ..logic.catalog import Catalog
from ..logic.verify import number_set, quote_in_file, quote_in_passage
from ..models.agent_io import FactCheckOutput
from ..onboarding.numwords import numbers_in_text, plain as plain_number
from ..models.data import Passage, Promo
from ..models.session import SwitchState
from ..providers.llm import AgentResult, LLMClient, LLMRequest
from ..providers.prompts import PromptTemplate
from ..providers.retriever import Retriever
from . import inputs

log = logging.getLogger(__name__)

CLAIMS_SECTION = "Approved on-air claims"
SOURCE_FILE = "Source file"  # D-247/D-253: a release file's passage (onboarding/sources.py), checked tolerantly
ABSENT = "not in this product"  # D-121: correct_value of an ingredient the sheet never names
_NAME = re.compile(r"[a-z][a-z-]{3,}")
_BASE_NOT_NAMES = frozenset({"percent", "with", "and", "contains", "has", "the", "this", "product"})
# D-278: the show's own product words ("the kettle", "this serum") are never a substance name; set per post_validate
# from the catalog, in place of a fixed list of the demo products' words
_PRODUCT_WORDS: contextvars.ContextVar[frozenset] = contextvars.ContextVar("product_words", default=frozenset())


def _not_names() -> frozenset:
    return _BASE_NOT_NAMES | _PRODUCT_WORDS.get()
_FREE_FROM = re.compile(r"\s*free from\s*:")


WORD_FIELDS = frozenset({"packaging", "texture", "fragrance", "origin"})
_UNIT_WORDS = frozenset({"ml", "mls", "milliliter", "milliliters", "g", "gram", "grams", "size"})


def _words_within(stated: str, correct: str | None) -> bool:
    """Every word the host said is part of the sheet's value: a less specific form, not a contradiction."""
    said = {w for w in _NAME.findall((stated or "").lower()) if w not in _UNIT_WORDS and w not in _not_names()}
    sheet = set(_NAME.findall((correct or "").lower()))
    return bool(said) and said <= sheet


# words that frame a statement ("it does contain", "no claim is made", "is given"), not the value it states
_FRAME = frozenset({"does", "contain", "includes", "include", "included", "made", "given", "claim", "claims", "stated",
                    "states", "listed", "there", "have", "from", "that", "which", "only", "also", "said", "says"})


_FLIP = {"gt": "le", "ge": "lt", "lt": "ge", "le": "gt"}


def _negated_threshold(lex, text: str) -> bool:
    """D-271: a negation before the threshold and before any number negates the threshold itself ("Not suitable for
    children under 4" is a range of 4 and up; "no more than 2" is at most 2). In "S$40 does not qualify (above S$40)"
    a number comes first, so the negation is about the number, not the threshold.
    ponytail: digits only; a number in words before the negation still counts as no number."""
    first = min((m.start() for rx in lex.comparison_kinds.values() if (m := rx.search(text))), default=None)
    if first is None:
        return False
    before = text[:first].lower()
    at = [m.start() for n in lex.negation_words if (m := re.search(rf"(?<!\w){re.escape(n)}(?!\w)", before))]
    return bool(at) and not re.search(r"\d", before[:min(at)])


def _range_kind(lex, text: str) -> str | None:
    """The threshold kind a text states, with a negated threshold turned round (D-271)."""
    kind = lex.comparison_kind(text)
    return _FLIP.get(kind, kind) if kind and _negated_threshold(lex, text) else kind


def _polarity_differs(lex, host: str, correct: str | None) -> bool:
    """D-260: "exactly S$40 qualifies" against "Exactly S$40 does not qualify": the same number, the opposite fact.
    D-261: with a strict threshold on either side, "S$40 does not qualify" and "above S$40" agree.
    D-271: a negated threshold is compared as its range (`_threshold_differs`), not as a polarity."""
    if _negated_threshold(lex, host) or _negated_threshold(lex, correct or ""):
        return False
    if {lex.comparison_kind(host), lex.comparison_kind(correct or "")} & {"gt", "lt"}:
        return False
    neg = lambda t: any(re.search(rf"(?<!\w){re.escape(n)}(?!\w)", (t or "").lower())  # noqa: E731
                        for n in lex.negation_words)
    return neg(host) != neg(correct)


def _latin(text: str | None) -> bool:
    return bool(re.search(r"[a-z]{2}", (text or "").lower()))


def _same_substance(stated: str | None, correct: str | None, quote: str | None = None) -> bool:
    """Every name word the host gave for the substance is in the correction ("zinc gluconate" vs "zinc": no).
    D-262 (pool 3: "10% by weight" quoting "shea butter: 10% by weight" was dropped): a correction that names none of
    the host's substance words leaves the name to its quote, which must then hold them."""
    names = lambda t: set(_NAME.findall((t or "").lower())) - _not_names() - _UNIT_WORDS  # noqa: E731
    said, right = names(stated), names(correct)
    if not said:
        return True
    if said & right:
        return said <= right
    return said <= names(quote) or not names(quote)

def _from_quote(correct: str, quote: str, share: float = 0.5) -> bool:
    """D-244 L1/L8: the correction rests on the quote. Latin script: at least half of its value words are in the
    quote (by their first five letters, so "resistant" meets "resistance"); other scripts: two letters in a row.
    "not disclosed" or "No expiry period is given" states no value the quote holds, so it is no correction."""
    q = quote.lower()
    latin = set(_NAME.findall(correct.lower())) - _not_names() - _FRAME
    if latin:
        stems = {w[:5] for w in _NAME.findall(q)}
        return sum(w[:5] in stems for w in latin) >= share * len(latin)
    other = re.sub(r"[\W\d_a-z]", "", correct.lower())
    return any(other[i:i + 2] in q for i in range(len(other) - 1))


# D-250: the eval collects the drops of one case here (a list set by the caller; tasks inherit it)
DROPS: contextvars.ContextVar[list | None] = contextvars.ContextVar("fact_drops", default=None)


def _drop(c, why: str) -> None:
    """D-248 (sealed FR run: 3 of 4 right model corrections dropped in silence): code may overrule the model, but
    never silently; the reason is logged with the claim."""
    log.info("fact claim dropped by code: %s | field=%s stated=%r correct=%r passage=%s", why, c.field,
             c.stated_value, c.correct_value, c.passage_id)
    if (sink := DROPS.get()) is not None:
        sink.append({"reason": why, "field": c.field, "stated": c.stated_value, "correct": c.correct_value,
                     "passage_id": c.passage_id, "quote": c.quote})
    c.verdict = "not_in_sources"


def _threshold_differs(lex, host: str, c, said: set) -> bool:
    """D-248: "> SGD 90" or "exceeds S$90" is a threshold; "exactly S$90" is not the same value. D-259: the kind of
    threshold counts too ("at least S$40" is not "above S$40"). True when the correction or the quote words the number
    as a threshold of another kind than the host's (no word: exact)."""
    kind = _range_kind(lex, c.correct_value or "")  # D-271: a negated threshold is its range
    if kind is None:
        q = c.quote or ""
        for m in re.finditer(r"\d[\d,]*(?:\.\d+)?", q):
            if number_set(m.group()) & said:
                kind = _range_kind(lex, q[max(0, m.start() - 20):m.end() + 15])
                if kind is not None:
                    break
    if kind is None:
        return False
    host_kind = _range_kind(lex, host)
    if host_kind is None and lex.comparison.search(host):
        return False  # a language without kinds: any threshold word is the same threshold (D-248)
    return host_kind != kind


def _term_dispute(c, p, said: set, passages: Sequence[Passage]) -> bool:
    """D-251 (sealed: "S$36 per tube already includes delivery" -> "delivery is not included in this price"): the
    stated number is right and the correction is about a term attached to it (tax, delivery, per unit, validity).
    The number is right when the quote's passage states it, or, for a price, any passage of the product."""
    stated = lambda t: number_set(t) | {plain_number(v) for v in numbers_in_text(t)}  # noqa: E731
    if said <= stated(p.text):
        return True
    return c.field in PRICE_FIELDS and said <= stated(" ".join(x.text for x in passages if x.product_id == c.product_id))


def _promo_term(c, promo) -> bool:
    """D-148: a wrong discount or duration of the active promo ("an extra 20% off" for 10%). Code checks that
    the right value is one of the promo's own terms and that the host said a different number."""
    terms = {format(Decimal(str(v)).normalize(), "f") for v in
             (promo.discount_pct_off_live_price, round(promo.duration_sec / 60)) if v is not None}
    right, said = number_set(c.correct_value or ""), number_set(c.stated_value or "")
    return bool(right) and right <= terms and bool(said) and not said <= right


def _offer_threshold(c, offer) -> bool:
    """D-149: a wrong spend threshold of a running gift offer: the right value is the offer's own min spend and the
    host said another amount."""
    if offer.min_spend is None:
        return False
    right, said = number_set(c.correct_value or ""), number_set(c.stated_value or "")
    return right == number_set(f"{offer.min_spend}") and bool(said) and not said <= right


# D-207: a section that lists every ingredient ("Ingredients", "Full ingredients", "Ingredients (INCI)"); a "Key
# ingredients" table is not one
_COMPLETE_LIST = re.compile(r"^(?:full |complete )?ingredients?(?: list)?(?: \(inci\))?$", re.IGNORECASE)
_UNIT_ALIASES = {"ml": "ml", "mls": "ml", "milliliter": "ml", "milliliters": "ml", "millilitre": "ml",
                 "millilitres": "ml", "g": "g", "gram": "g", "grams": "g", "%": "%", "percent": "%",
                 "year": "year", "years": "year", "month": "month", "months": "month", "week": "week",
                 "weeks": "week", "day": "day", "days": "day", "hour": "hour", "hours": "hour",
                 "s$": "SGD", "sgd": "SGD", "rm": "MYR", "myr": "MYR"}
_QUANTITY = re.compile(r"(s\$|sgd|rm|myr)?\s*(\d+(?:\.\d+)?)\s*(%|[a-z]+)?", re.IGNORECASE)


def _units(text: str) -> set[str]:
    """D-207: the units and currencies next to the numbers of a value ("12 months" -> {"month"}, "RM36" -> {"MYR"})."""
    out = set()
    for cur, _, unit in _QUANTITY.findall(text or ""):
        for u in (cur, unit):
            if u and u.lower() in _UNIT_ALIASES:
                out.add(_UNIT_ALIASES[u.lower()])
    return out


def _proven_absent(stated: str, passages: Sequence[Passage], product_id: str) -> bool:
    """D-207 (full review P2): an absence is a fact only when the sheet proves it: the product's "Free from" list names
    the ingredient, or the sheet has a complete ingredient list. A partial sheet ("full INCI list on the carton")
    settles nothing, and the claim stays not_in_sources."""
    names = [w for w in _NAME.findall(stated.lower()) if w not in _not_names()]
    mine = [p for p in passages if p.product_id == product_id]
    free_from = " ".join(p.text.lower() for p in mine if _FREE_FROM.match(p.text.lower()))
    return bool(names) and (any(n in free_from for n in names) or any(_COMPLETE_LIST.match(p.section) for p in mine))


def _on_sheet(stated: str, passages: Sequence[Passage], product_id: str) -> bool:
    """D-165: every ingredient word the host named is in the product's sheet (not only in its "Free from" list)."""
    names = [w for w in _NAME.findall(stated.lower()) if w not in _not_names()]
    sheet = " ".join(p.text.lower() for p in passages if p.product_id == product_id and not _FREE_FROM.match(p.text.lower()))
    return bool(names) and all(n in sheet for n in names)


def _absent_from_sheet(stated: str, passages: Sequence[Passage], product_id: str) -> bool:
    """D-121: every ingredient word the host named is missing from all of the product's sheet passages.
    D-156: a word the sheet names only in its "Free from:" list is missing too ("a little alcohol" against
    "Free from: ... ethanol (denatured alcohol)")."""
    names = [w for w in _NAME.findall(stated.lower()) if w not in _not_names()]
    mine = [p.text.lower() for p in passages if p.product_id == product_id]
    sheet = " ".join(t for t in mine if not _FREE_FROM.match(t))
    # D-259 (sealed pool 2: "pear juice" was not absent because "juice" was on the sheet): absent when any of
    # its words is missing; the complete list or "Free from" still has to prove it (D-207)
    return bool(names) and bool(mine) and not all(n in sheet for n in names)
PRICE_FIELDS = ("price", "set_price", "promo")
# D-100: a test result is checked only when the host cites a test. A time or number inside a benefit
# claim ("it whitens your skin in two weeks") is compliance wording, not a test result.
TEST_CITED = re.compile(r"\b(?:tests?|tested|testing|study|studies|trials?|clinical(?:ly)?|participants?|"
                        r"people|users|women|men|subjects|percent)\b|%", re.IGNORECASE)


@dataclass
class FactInput:
    utterance: str
    on_air: str
    switch: SwitchState
    promo: Promo | None
    passages: list[Passage]
    previous: list[str] = field(default_factory=list)
    offers: list[Promo] = field(default_factory=list)  # D-149: running offers that change no price
    parts: list[str] = field(default_factory=list)  # D-167: the finals a merged utterance joins, oldest first
    session_id: str | None = None
    scenario: str = "default"


async def gather_fact_passages(
    retriever: Retriever,
    catalog: Catalog,
    prefetched: dict[str, list[Passage]],
    *,
    utterance: str,
    on_air: str,
    switch: SwitchState,
    search_timeout_ms: int,
) -> list[Passage]:
    """Full sheets, retaining original citation IDs, without search or network prefetch.

    Keep the existing call signature for runtime/evaluation callers. Explicitly mentioned products
    remain available for comparisons, alongside the on-air product and a counting/pending target.
    Local uploaded sheets take precedence over the shipped catalog.
    """
    others = catalog.products_mentioned(utterance) - {on_air}
    if switch.status in ("counting", "pending"):
        others.add(switch.target_product_id or catalog.next_product(on_air) or on_air)
    others.discard(on_air)
    out: dict[str, Passage] = {}
    local_sheets = getattr(retriever, "passages_of", None)
    for pid in [on_air, *sorted(others)]:
        sheet = (local_sheets(pid) if callable(local_sheets) else
                 [p for p in catalog.pack.passages if p.product_id == pid])
        for p in sheet:
            out.setdefault(p.passage_id, p)
    return list(out.values())


def post_validate(out: FactCheckOutput, passages: Sequence[Passage], catalog: Catalog, promo: Promo | None,
                  utterance: str | None = None, offers: Sequence[Promo] = ()) -> FactCheckOutput:
    """A contradiction stands only when its correction is backed by a quoted passage, or by the
    active promo price; otherwise it is downgraded to not_in_sources (§7.4).

    D-100: never on field `other` (no value to compare, e.g. "prescription cream" -> "cosmetic
    product": that is the compliance judge's job), and on `test_result` only when the host cites a test."""
    o = out.model_copy(deep=True)
    words = " ".join(" ".join([p.name, p.short_name, *p.aliases]) for p in catalog.products).lower()
    # a word of an ingredient passage stays a substance name ("vitamin" in a "Vitamin C Serum")
    used = " ".join(p.text.lower() for p in [*passages, *catalog.pack.passages] if "ingredient" in p.section.lower())
    token = _PRODUCT_WORDS.set(frozenset(w for w in _NAME.findall(words) if w not in used))
    try:
        return _post_validate(o, passages, catalog, promo, utterance, offers)
    finally:
        _PRODUCT_WORDS.reset(token)


def _post_validate(o: FactCheckOutput, passages: Sequence[Passage], catalog: Catalog, promo: Promo | None,
                   utterance: str | None, offers: Sequence[Promo]) -> FactCheckOutput:
    by_id = {p.passage_id: p for p in passages}
    set_ids = {s.set_id for s in catalog.set_offers}
    for c in o.claims:
        # D-148 (sealed show replay): during a time sale the live price said as the price now is stale, even when
        # the model calls it supported ("It's $36, very cheap"); "normally $36" or "after the sale" is fine
        if (c.verdict == "supported" and c.field == "price" and promo is not None and promo.changes_prices
                and c.product_id in promo.promo_prices and utterance is not None
                and not catalog.lexicon.price_contrast.search(utterance)
                and number_set(c.stated_value or "") == number_set(catalog.money(catalog.live_price_value(c.product_id)))):
            c.verdict, c.field, c.passage_id, c.quote = "contradicted", "promo", None, None
            c.correct_value = catalog.price_display(c.product_id, promo)
        # A set's price is a fact about the set offer, not about one product (holdout H046).
        if not catalog.is_product(c.product_id) and not (c.field in PRICE_FIELDS and c.product_id in set_ids):
            c.verdict = "not_in_sources"
            continue
        if c.verdict != "contradicted":
            continue
        if c.field == "other" or (c.field == "test_result" and utterance is not None
                                  and not TEST_CITED.search(utterance)):
            _drop(c, "field other, or a test result the line does not cite")
            continue
        lex = catalog.lexicon
        # D-250: numbers in digits or words ("twelve months after opening" states 12)
        # D-251: and numbers written in other scripts' words ("영 점 오 퍼센트" states 0.5; onboarding's numwords)
        nums = lambda t: (number_set(t or "") | lex.spoken_numbers(t or "")  # noqa: E731
                          | {plain_number(v) for v in numbers_in_text(t or "")} | lex.times_numbers(t or ""))
        said, right = nums(c.stated_value), nums(c.correct_value)
        # D-207: the same number in another unit or currency ("12 years" vs "12 months", "RM36" vs "S$36") is a
        # real contradiction, not a restatement
        units_differ = bool(_units(c.stated_value) and _units(c.correct_value)
                            and _units(c.stated_value) != _units(c.correct_value))
        host = f"{c.stated_value or ''} {c.span or ''}"
        threshold = _threshold_differs(lex, host, c, said) or _polarity_differs(lex, host, c.correct_value)
        if (((said and said == right and not units_differ)
                or (c.stated_value or "").strip().lower() == (c.correct_value or "").strip().lower())
                and not threshold):
            _drop(c, "D-151: the correction restates what the host said")
            continue
        if (not right and _words_within(c.correct_value, host) and not _polarity_differs(lex, host, c.correct_value)):
            # D-261 (candidate 947084e: "available online only" corrected by "Online only"): every value word of a
            # word correction is already in the line, with the same polarity: a restatement
            _drop(c, "D-261: the line already says the correction")
            continue
        if (c.field in WORD_FIELDS and _words_within(c.stated_value, c.correct_value)
                # D-248: "contains fragrance" against "No fragrance is added" (or the other way) is the opposite
                # fact, not a less specific one
                and bool(lex.absence.search(host)) == bool(lex.absence.search(c.correct_value or ""))):
            _drop(c, "D-123: the host's words are a less specific form of the source value")
            continue
        if (c.field == "ingredient" and _on_sheet(c.stated_value or "", passages, c.product_id)
                and not catalog.lexicon.absence.search(f"{c.stated_value or ''} {c.span or ''}")):
            # D-165 (local SEED1 replay): "The main ingredient is niacinamide." came back "Centella Asiatica Leaf
            # Water". An ingredient the product contains is never contradicted by another one ("main" is not a fact
            # the sheet settles); an absence of one it contains still is
            _drop(c, "D-165: an ingredient the product contains")
            continue
        ok = False
        if (c.field in ("ingredient", "ingredient_amount") and c.passage_id is None
                and (c.correct_value or "").strip().lower() == ABSENT):
            # D-151 (sealed round 3): "No retinol in this one" came back contradicted with "not in this product":
            # the same thing. A stated absence is never contradicted by an absence.
            said_absent = catalog.lexicon.absence.search(f"{c.stated_value or ''} {c.span or ''}")
            ok = (not said_absent and _absent_from_sheet(c.stated_value, passages, c.product_id)
                  and _proven_absent(c.stated_value or "", passages, c.product_id))  # D-207
        elif c.passage_id is not None:
            p = by_id.get(c.passage_id)
            # D-250: each check names itself, so a drop says which one failed
            checks = (
                ("unknown passage", lambda: p is not None),
                ("quote not in the passage", lambda: c.quote is not None and (
                    quote_in_file(c.quote, p.text) if p.section == SOURCE_FILE else quote_in_passage(c.quote, p.text))),
                ("a number of the correction is not in the quote",
                 lambda: c.correct_value is not None and right <= nums(c.quote)),
                # D-244 L1: the correction is a value the quote states (a number, or the quote's words);
                # "not disclosed" or "not specified" is no source value, so the claim is unverifiable
                ("L1: the correction states no value of the quote",
                 lambda: bool(right) or _from_quote(c.correct_value, c.quote)
                 # D-259: a correction translated from a quote in another script is not compared word by word; an
                 # absence-worded one still needs its absence in the quote (below)
                 or (_latin(c.correct_value) != _latin(c.quote) and not lex.absence.search(c.correct_value or ""))),
                # D-244 L1 (sealed FR run): a stated number "corrected" by words is a value SOURCE does not give
                # ("lasts 24 months" -> "No period after opening is given"); presence of an ingredient is the
                # exception ("2% retinol" -> "free from retinol")
                # D-252 (sealed: "reapply after swimming" -> "No water-resistance claim is made"): an absence the
                # quote does not state is the model's note, not a source value; presence fields may infer it from
                # a complete list
                ("L1: an absence the quote does not state",
                 lambda: c.field in ("ingredient", "fragrance") or not lex.absence.search(c.correct_value or "")
                 or (bool(lex.absence.search(c.quote or "")) and _from_quote(c.correct_value, c.quote, 0.75))),
                # D-255 (sealed FD: "3 mg zinc gluconate" contradicted by "2.5 mg zinc"): a salt is not its element;
                # the correction must be about the substance the host named
                ("another substance than the host named",
                 lambda: c.field != "ingredient_amount"
                 or _same_substance(c.stated_value, c.correct_value, c.quote)),
                ("L1: a stated number corrected without a number",
                 lambda: c.field == "ingredient" or not said or bool(right) or _term_dispute(c, p, said, passages)),
                # Claim wording is compliance (the judge's job), never a product fact (D-048).
                ("an approved-claims passage", lambda: p.section != CLAIMS_SECTION),
            )
            failed = next((name for name, check in checks if not check()), None)
            ok = failed is None
        elif c.field in PRICE_FIELDS and promo is not None and promo.changes_prices:
            ok = c.correct_value == catalog.price_display(c.product_id, promo) or (
                c.field == "promo" and _promo_term(c, promo))
        if not ok and c.field == "promo" and c.passage_id is None:
            ok = any(_offer_threshold(c, o) for o in offers)
        if not ok:
            _drop(c, (failed if c.passage_id is not None and failed else "no source check passed"))
        elif c.quote and ((not right
                           and (c.correct_value or "").strip().lower() in host.lower())
                          or (said and said == right and threshold)):
            # D-244 L8: a bare field word the host already said ("fragrance" for "no fragrance") is no line to say;
            # D-248: nor is the threshold's number alone ("S$90" for "more than S$90"); the source's own words are
            c.correct_value = c.quote
    return o


class FactChecker:
    name = "fact_checker"

    def __init__(self, llm: LLMClient, prompt: PromptTemplate, catalog: Catalog) -> None:
        self.llm = llm
        self.prompt = prompt
        self.prompt_version = prompt.version
        self.model = llm.facts.model
        self.catalog = catalog
        # D-242 arm FR: how to read a release's record facts; D-247 arm FD: the release's files on top
        from . import arms
        settings = getattr(llm, "settings", None)
        mode = getattr(settings, "FACT_MODE", "sheet")
        layers = {"record": ["FR"], "docs": ["FR", "FD"]}.get(mode, [])
        addenda = arms._addenda(str(llm.prompts_path)) if layers else {}
        extras = [addenda.get((layer, self.name)) for layer in layers]
        self.system_instruction = "\n\n".join([prompt.system_instruction, *(x for x in extras if x)])
        lang = getattr(getattr(catalog, "pack", None), "lang", None)
        if lang:  # D-259: the host reads the correction aloud in the show's language
            self.system_instruction += (f"\n\nThe show's language is {lang}. Write `correct_value` in it (translate a "
                                        "value SOURCE writes in another language); keep `quote` verbatim.")
        # D-279: each product's release files (one release, or each release of a multi-release show)
        self.files: dict[str, tuple[tuple, tuple]] = {}
        releases = dict(getattr(getattr(catalog, "pack", None), "releases", None) or {})
        release_id = getattr(getattr(catalog, "runsheet", None), "runsheet_id", "")
        if not releases and release_id.startswith("rel_"):
            releases = {p.product_id: release_id for p in catalog.products}
        if mode == "docs":
            from ..onboarding.sources import release_sources

            self.files = {pid: release_sources(str(settings.onboarding_path), rid) for pid, rid in releases.items()}
        first = next(iter(self.files.values()), ((), ()))
        self.file_parts, self.file_passages = first  # the first product's (one-release shows, the eval)
        self.all_file_passages = tuple(x for _, ps in self.files.values() for x in ps)

    def _parts(self, on_air: str) -> tuple:
        return self.files.get(on_air, (self.file_parts,))[0]

    def _request(self, user: str, prefix: str, deadline_ms: int, session_id: str | None, parts: tuple = (),
                 **mock) -> LLMRequest:
        # D-247: with files, the cache holds the system instruction, the files and the product and full-sheet blocks
        # (the same on every line of a one-product release)
        return LLMRequest(
            agent=self.name, model=self.llm.facts.model, thinking_level=self.llm.facts.thinking_level,
            prompt_version=self.prompt_version, system_instruction=self.system_instruction,
            user_message=user, output_model=FactCheckOutput, deadline_ms=deadline_ms, session_id=session_id,
            cache_prefix=prefix, cache_parts=parts,
            cache_ttl_sec=sum(i.planned_duration_sec for i in self.catalog.runsheet.items), **mock)

    async def warm_cache(self, inp: FactInput) -> None:
        """D-247: the files' context cache is made at session start (with the first line's static blocks), not on
        the first line."""
        if parts := self._parts(inp.on_air):
            _, prefix = self._render(inp)
            await self.llm.warm_cache(self._request(prefix, prefix, 60_000, inp.session_id, parts))

    def _render(self, inp: FactInput) -> tuple[str, str]:
        return self.prompt.render_cached({
            "current_product_compact_json": inputs.current_product_compact_json(self.catalog, inp.on_air),
            "switch_context_json": inputs.switch_context_json(self.catalog, inp.switch, inp.on_air),
            "active_promo_json_or_null": inputs.active_promo_json_or_null(self.catalog, inp.promo),
            "active_offers_json": inputs.active_offers_json(self.catalog, inp.offers),
            "set_offers_json": inputs.set_offers_json(self.catalog, inp.promo),
            "passages_json": inputs.passages_json(inp.passages),
            "last_two_final_transcripts_json": inp.previous[-2:],
            # D-167: a merged utterance shows where speech-to-text split it ("A / B")
            "utterance_text": inputs.utterance_text(" / ".join(inp.parts) if len(inp.parts) > 1 else inp.utterance),
        }, {"current_product_compact_json", "passages_json"})

    async def run(self, inp: FactInput, *, deadline_ms: int) -> AgentResult[FactCheckOutput]:
        user, prefix = self._render(inp)
        res = await self.llm.call(self._request(
            user, prefix, deadline_ms, inp.session_id, self._parts(inp.on_air), mock_primary_text=inp.utterance,
            mock_scenario=inp.scenario,
            mock_fallback=lambda _: {"claims": [], "reason": "rule-based: no fact check"}, preview=inp.utterance,
        ))
        if res.output is not None:
            for c in res.output.claims:  # D-247: "file:<name>#<locator>" names the file; the quote is checked in it
                if c.passage_id and c.passage_id.startswith("file:"):
                    c.passage_id = c.passage_id.split("#", 1)[0]
            res.output = post_validate(res.output, [*inp.passages, *self.all_file_passages], self.catalog, inp.promo,
                                       inp.utterance, inp.offers)
        return res
