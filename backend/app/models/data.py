"""Models of the data pack files (data/). The pack is the source of truth; these only type it."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

# ---- data/products/products.json -------------------------------------------------------------


class PrompterPoint(BaseModel):
    point_id: str
    text: str
    required: bool


class Product(BaseModel):
    product_id: str
    code: str
    name: str
    short_name: str
    eyebrow: str
    tagline: str
    doc: str
    volume: str
    list_price: float
    live_price: float
    hero_badge: str
    aliases: list[str]
    key_facts: dict[str, str]
    prompter_points: list[PrompterPoint]
    approved_claims: list[str]
    not_approved_claims: list[str]


class SetOffer(BaseModel):
    set_id: str
    name: str
    short_name: str | None = None  # screen label (D-085); the full name stays in promo passages
    product_ids: list[str]
    live_price: float


class ProductsFile(BaseModel):
    brand: str
    currency: str
    currency_symbol: str
    set_offers: list[SetOffer]
    products: list[Product]


# ---- data/products/passages.jsonl (also the retriever's Passage, §9.1) -----------------------


class Passage(BaseModel):
    passage_id: str
    product_id: str
    doc: str
    section: str
    text: str
    score: float = 0


# ---- data/runsheets/*.json -------------------------------------------------------------------


class RunsheetItem(BaseModel):
    order: int
    product_id: str
    planned_duration_sec: int
    required_point_ids: list[str]


class Runsheet(BaseModel):
    runsheet_id: str
    title: str
    brand: str
    language: str
    market: str
    items: list[RunsheetItem]
    promo_ids: list[str]


# ---- data/promos/promos.json -----------------------------------------------------------------


class Promo(BaseModel):
    promo_id: str
    kind: str
    title: str
    duration_sec: int
    applies_to: list[str]
    discount_pct_off_live_price: float | None = None
    promo_prices: dict[str, float] = {}
    viewer_text: str
    host_text: str
    changes_prices: bool


class PromoRules(BaseModel):
    max_active_price_promos: int
    promo_prices_are_final: bool


class PromosFile(BaseModel):
    promos: list[Promo]
    rules: PromoRules


# ---- data/policy/claim_rules.json ------------------------------------------------------------


class PolicySource(BaseModel):
    source_id: str
    title: str
    file: str
    publisher_url: str | None = None
    note: str | None = None


class Rule(BaseModel):
    rule_id: str
    source_id: str
    source_ref: str
    title: str
    description: str
    severity: Literal["HIGH", "MEDIUM"]
    unacceptable_examples: list[str]
    say_instead_hint: str
    reflex_phrases: list[str]


class ClaimRulesFile(BaseModel):
    policy_id: str
    market: str
    category: str
    sources: list[PolicySource]
    severity_display: dict[str, str]
    rules: list[Rule]
    negation_cues: list[str]
    quote_cues: list[str]


# ---- data/policy/intents.json ----------------------------------------------------------------


class Intent(BaseModel):
    intent: str
    group: Literal["product", "general"]
    route: Literal["AUTO", "HOST", "OPERATOR"]
    sensitive: bool
    purchase_impact: int
    product_scope: Literal["single", "multi", "none"]


class RankingWeights(BaseModel):
    W_VIEWERS: float
    W_PURCHASE_IMPACT: float
    CURRENT_PRODUCT_BONUS: float
    WAIT_TIEBREAK_PER_MIN: float
    WAIT_TIEBREAK_MAX_MIN: float


class IntentsFile(BaseModel):
    version: str
    intents: list[Intent]
    condition_slots: dict[str, list[str]]
    ranking_weights: RankingWeights


# ---- data/templates/notices.json -------------------------------------------------------------


class NoticeTemplate(BaseModel):
    template_id: str
    use_when: str
    text: str
    placeholders: list[str]


class QuickReply(BaseModel):
    reply_id: str
    intent: str
    text: str


class CuePreset(BaseModel):
    cue_id: str
    label: str
    text: str


class NoticesFile(BaseModel):
    correction_notices: list[NoticeTemplate]
    field_labels: dict[str, str]
    operator_quick_replies: list[QuickReply]
    host_cue_presets: list[CuePreset]
