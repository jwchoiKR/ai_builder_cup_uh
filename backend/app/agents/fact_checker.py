"""FactChecker agent (DEV_SPEC §7.4): checks product facts in one host sentence against the sheets."""
from __future__ import annotations

import re
from decimal import Decimal
from collections.abc import Sequence
from dataclasses import dataclass, field

from ..logic.catalog import Catalog
from ..logic.verify import number_set, quote_in_passage
from ..models.agent_io import FactCheckOutput
from ..models.data import Passage, Promo
from ..models.session import SwitchState
from ..providers.llm import AgentResult, LLMClient, LLMRequest
from ..providers.prompts import PromptTemplate
from ..providers.retriever import Retriever
from . import inputs

CLAIMS_SECTION = "Approved on-air claims"
ABSENT = "not in this product"  # D-121: correct_value of an ingredient the sheet never names
_NAME = re.compile(r"[a-z][a-z-]{3,}")
_NOT_NAMES = frozenset({"percent", "with", "and", "contains", "has", "the", "this", "ampoule", "cream", "product"})
_FREE_FROM = re.compile(r"\s*free from\s*:")


WORD_FIELDS = frozenset({"packaging", "texture", "fragrance", "origin"})
_UNIT_WORDS = frozenset({"ml", "mls", "milliliter", "milliliters", "g", "gram", "grams", "size"})


def _words_within(stated: str, correct: str | None) -> bool:
    """Every word the host said is part of the sheet's value: a less specific form, not a contradiction."""
    said = {w for w in _NAME.findall((stated or "").lower()) if w not in _UNIT_WORDS and w not in _NOT_NAMES}
    sheet = set(_NAME.findall((correct or "").lower()))
    return bool(said) and said <= sheet


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


def _on_sheet(stated: str, passages: Sequence[Passage], product_id: str) -> bool:
    """D-165: every ingredient word the host named is in the product's sheet (not only in its "Free from" list)."""
    names = [w for w in _NAME.findall(stated.lower()) if w not in _NOT_NAMES]
    sheet = " ".join(p.text.lower() for p in passages if p.product_id == product_id and not _FREE_FROM.match(p.text.lower()))
    return bool(names) and all(n in sheet for n in names)


def _absent_from_sheet(stated: str, passages: Sequence[Passage], product_id: str) -> bool:
    """D-121: every ingredient word the host named is missing from all of the product's sheet passages.
    D-156: a word the sheet names only in its "Free from:" list is missing too ("a little alcohol" against
    "Free from: ... ethanol (denatured alcohol)")."""
    names = [w for w in _NAME.findall(stated.lower()) if w not in _NOT_NAMES]
    mine = [p.text.lower() for p in passages if p.product_id == product_id]
    sheet = " ".join(t for t in mine if not _FREE_FROM.match(t))
    return bool(names) and bool(mine) and not any(n in sheet for n in names)
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
            c.verdict = "not_in_sources"
            continue
        said, right = number_set(c.stated_value or ""), number_set(c.correct_value or "")
        if (said and said == right) or (c.stated_value or "").strip().lower() == (c.correct_value or "").strip().lower():
            c.verdict = "not_in_sources"  # D-151: the "correction" restates what the host said
            continue
        if c.field in WORD_FIELDS and _words_within(c.stated_value, c.correct_value):
            c.verdict = "not_in_sources"  # D-123: "tube" is the "Airless pump tube", only less specific
            continue
        if (c.field == "ingredient" and _on_sheet(c.stated_value or "", passages, c.product_id)
                and not catalog.lexicon.absence.search(f"{c.stated_value or ''} {c.span or ''}")):
            # D-165 (local SEED1 replay): "The main ingredient is niacinamide." came back "Centella Asiatica Leaf
            # Water". An ingredient the product contains is never contradicted by another one ("main" is not a fact
            # the sheet settles); an absence of one it contains still is
            c.verdict = "not_in_sources"
            continue
        ok = False
        if (c.field in ("ingredient", "ingredient_amount") and c.passage_id is None
                and (c.correct_value or "").strip().lower() == ABSENT):
            # D-151 (sealed round 3): "No retinol in this one" came back contradicted with "not in this product":
            # the same thing. A stated absence is never contradicted by an absence.
            said_absent = catalog.lexicon.absence.search(f"{c.stated_value or ''} {c.span or ''}")
            ok = not said_absent and _absent_from_sheet(c.stated_value, passages, c.product_id)
        elif c.passage_id is not None:
            p = by_id.get(c.passage_id)
            ok = (p is not None and c.quote is not None and quote_in_passage(c.quote, p.text)
                  and c.correct_value is not None and number_set(c.correct_value) <= number_set(c.quote)
                  # Claim wording is compliance (the judge's job), never a product fact (D-048).
                  and p.section != CLAIMS_SECTION)
        elif c.field in PRICE_FIELDS and promo is not None and promo.changes_prices:
            ok = c.correct_value == catalog.price_display(c.product_id, promo) or (
                c.field == "promo" and _promo_term(c, promo))
        if not ok and c.field == "promo" and c.passage_id is None:
            ok = any(_offer_threshold(c, o) for o in offers)
        if not ok:
            c.verdict = "not_in_sources"
    return o


class FactChecker:
    name = "fact_checker"

    def __init__(self, llm: LLMClient, prompt: PromptTemplate, catalog: Catalog) -> None:
        self.llm = llm
        self.prompt = prompt
        self.prompt_version = prompt.version
        self.model = llm.fast.model
        self.catalog = catalog

    async def run(self, inp: FactInput, *, deadline_ms: int) -> AgentResult[FactCheckOutput]:
        user, prefix = self.prompt.render_cached({
            "current_product_compact_json": inputs.current_product_compact_json(self.catalog, inp.on_air),
            "switch_context_json": inputs.switch_context_json(self.catalog, inp.switch, inp.on_air),
            "active_promo_json_or_null": inputs.active_promo_json_or_null(self.catalog, inp.promo),
            "active_offers_json": inputs.active_offers_json(self.catalog, inp.offers),
            "set_offers_json": inputs.set_offers_json(self.catalog, inp.promo),
            "passages_json": inputs.passages_json(inp.passages),
            "last_two_final_transcripts_json": inp.previous[-2:],
            "utterance_text": inputs.utterance_text(inp.utterance),
        }, {"current_product_compact_json", "passages_json"})
        res = await self.llm.call(LLMRequest(
            agent=self.name, model=self.llm.facts.model, thinking_level=self.llm.facts.thinking_level,
            prompt_version=self.prompt_version, system_instruction=self.prompt.system_instruction,
            user_message=user, output_model=FactCheckOutput, deadline_ms=deadline_ms, session_id=inp.session_id,
            cache_prefix=prefix, cache_ttl_sec=sum(i.planned_duration_sec for i in self.catalog.runsheet.items),
            mock_primary_text=inp.utterance, mock_scenario=inp.scenario,
            mock_fallback=lambda _: {"claims": [], "reason": "rule-based: no fact check"}, preview=inp.utterance,
        ))
        if res.output is not None:
            res.output = post_validate(res.output, inp.passages, self.catalog, inp.promo, inp.utterance, inp.offers)
        return res
