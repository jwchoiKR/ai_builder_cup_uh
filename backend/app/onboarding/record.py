"""Typed product record produced by onboarding (P0, docs/research/onboarding-spec.md section 1).

Every extracted value carries its evidence (which file, where in it, a short quote). Money is stored per market in
minor units with its ISO currency code; sizes are a number and a unit. Nothing here is specific to one brand, market,
language or category: those come from the documents.

Decimal numbers are strings as written ("30", "0.2"): Gemini's JSON mode can loop on a float ("30.000000..."), so
code normalises the strings instead. Every field is required in the JSON schema (nullable or an empty list when the
documents do not give it): with optional fields the model skipped whole sections.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def _all_required(schema: dict) -> None:
    schema["required"] = list(schema.get("properties", {}))


class _Model(BaseModel):
    model_config = ConfigDict(json_schema_extra=_all_required)


class Evidence(_Model):
    file: str  # the uploaded file's name
    locator: str  # "page 2", "sheet Prices row 7", "image", "paragraph 4"
    quote: str  # a short verbatim quote from the file


class Text(_Model):
    """A statement taken from the documents, as written."""
    text: str
    evidence: list[Evidence]


# D-243: ISO 4217 currencies without a minor unit: their "minor" amount is the whole amount (29,000 won is 29000)
ZERO_DECIMAL = frozenset({"BIF", "CLP", "DJF", "GNF", "ISK", "JPY", "KMF", "KRW", "PYG", "RWF", "UGX", "UYI", "VND",
                          "VUV", "XAF", "XOF", "XPF"})


def money_value(currency: str, minor: int):
    """The amount of a Money in its currency (3600 SGD minor -> 36, 29000 KRW -> 29000)."""
    from decimal import Decimal

    return Decimal(minor) if currency.upper() in ZERO_DECIMAL else Decimal(minor) / 100


def to_minor(currency: str, amount) -> int:
    from decimal import Decimal

    return int(Decimal(amount) if currency.upper() in ZERO_DECIMAL else Decimal(amount) * 100)


class Money(_Model):
    currency: str  # ISO 4217, e.g. "SGD", "MYR"
    minor: int  # 3600 for S$36.00; 29000 for 29,000 won (a currency without a minor unit, D-243)
    kind: Literal["list", "live", "promo", "other"]
    market: str | None = None  # "SG", "MY"; None when the document does not say
    evidence: list[Evidence]


class Variant(_Model):
    variant_id: str  # stable id from the document (code, SKU) or derived from name and size
    name: str
    size_value: str | None = None  # "30"
    size_unit: str | None = None  # "ml", "g", "pcs"
    market: str | None = None  # where this variant is sold ("SG"); None when the documents do not say
    prices: list[Money] = []
    evidence: list[Evidence]


class Offer(_Model):
    offer_id: str
    kind: Literal["percent_off", "amount_off", "fixed_price", "buy_x_get_y", "spend_threshold_gift", "bundle", "other"]
    title: str
    variant_ids: list[str] = []  # the variants it applies to (a bundle lists its members)
    percent: str | None = None  # "10"
    amount: Money | None = None  # amount off, fixed price or the spend threshold
    buy: int | None = None
    get: int | None = None
    gift: str | None = None
    rounding: str | None = None  # as stated ("rounded to the nearest 10 cents"); None when not stated
    starts: str | None = None  # ISO date or datetime as stated
    ends: str | None = None
    duration_min: int | None = None
    evidence: list[Evidence]


class Ingredient(_Model):
    name: str
    amount_value: str | None = None  # "0.2"
    amount_unit: str | None = None  # "%", "mg"
    purpose: str | None = None
    evidence: list[Evidence]


class QualifiedResult(_Model):
    """A test or study result that may be said only with its qualifier."""
    statement: str  # the result as written ("29 of 32 participants said their skin felt less dry after 2 weeks")
    numbers: list[str] = []  # the numbers in it, as digits
    provenance: Literal["in_house", "third_party_lab", "certifier", "clinical", "consumer_panel", "other"]
    qualifier: str  # the wording the host must say with it ("in our in-house test", "tested by <lab>")
    marker: str | None = None  # "*", "†", "※" when the document marks it
    evidence: list[Evidence]


class AvoidSaying(_Model):
    say_not: str
    say: str
    evidence: list[Evidence]


class Conflict(_Model):
    field: str  # dotted path, e.g. "variants[0].prices"
    values: list[str]
    evidence: list[Evidence]
    effective_dates: list[str | None] = []
    note: str = ""


class ProductRecord(_Model):
    brand: str
    product_name: str
    short_names: list[str] = []  # names viewers and hosts use ("barrier cream")
    generic_word: str | None = None  # the category word ("cream", "serum"), never an alias on its own
    category: str  # "cosmetic", "food_supplement", "haircare", ...: selects the law pack
    category_evidence: list[Evidence] = []
    language: str  # the documents' main language, BCP-47
    variants: list[Variant]
    offers: list[Offer] = []
    ingredients: list[Ingredient] = []
    ingredient_list_complete: bool = False  # True only when a document lists every ingredient (D-207)
    approved_claims: list[Text] = []
    not_approved_claims: list[Text] = []
    avoid_saying: list[AvoidSaying] = []
    qualified_results: list[QualifiedResult] = []
    cautions: list[Text] = []
    how_to_use: list[Text] = []
    key_facts: list[Text] = []  # other facts: origin, texture, fragrance, shelf life, packaging, ...
    missing: list[str] = []  # fields the documents do not give
    conflicts: list[Conflict] = []


class OnboardingResult(BaseModel):
    record: ProductRecord
    files: list[dict] = Field(default_factory=list)  # name, sha256, media type, bytes
    method: str  # EXTRACT_METHOD
    models: dict[str, str] = {}  # step -> model id ("read": "gemini-3.8-flash")
    seconds: float
    notes: list[str] = []  # what normalisation changed or dropped
    caution_pass_added: list[str] = []  # D-236: cautions only the caution pass found
    verify_mode: str = "full"  # D-236
    checks: list[dict] = []  # D-236: what a person must check, each with its group
    check_summary: dict = {}
