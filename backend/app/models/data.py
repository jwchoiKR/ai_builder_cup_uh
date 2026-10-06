"""Models of the data pack files (data/). The pack is the source of truth; these only type it."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

# ---- data/products/products.json -------------------------------------------------------------


class PrompterPoint(BaseModel):
    point_id: str
    text: str
    required: bool


class QualifiedResult(BaseModel):
    """Approved wording of one in-house test number, with its qualifier (TEST-QUALIFIER, D-105)."""
    result_id: str
    numbers: list[str]  # digits as heard after normalisation: "45", "0", "32"
    say: str


class AvoidSaying(BaseModel):
    """Host card hint (D-106): wording to avoid, and an approved claim to say instead (verbatim)."""
    say_not: str
    say: str


class ProductVariant(BaseModel):
    """D-281: one priced size or variant of an onboarded product."""
    label: str  # the variant's name and size as the documents write them ("Eau de Parfum 100 mL")
    list_price: float
    live_price: float


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
    qualified_results: list[QualifiedResult] = []
    target_group: list[str] = []  # D-256: who the product is made for (onboarded products), for the judges
    cautions: list[str] = []  # short host lines from the sheet's Cautions section (D-106)
    avoid_saying: list[AvoidSaying] = []
    variants: list[ProductVariant] = []  # D-281: every priced variant, the first is the main one (volume, live_price)


class SetOffer(BaseModel):
    set_id: str
    name: str
    short_name: str | None = None  # screen label (D-085); the full name stays in promo passages
    product_ids: list[str]
    live_price: float


class MarketPromo(BaseModel):
    """D-179: a promo's own amounts in another market (precomputed, never computed in code)."""
    promo_prices: dict[str, float] = {}
    min_spend: float | None = None


class MarketPrices(BaseModel):
    """D-179: the same products' prices in another market's currency (MY: demo values, user decision 10/5)."""
    currency: str
    currency_symbol: str
    products: dict[str, dict[Literal["list_price", "live_price"], float]]
    set_offers: dict[str, float]
    promos: dict[str, MarketPromo] = {}


class ProductsFile(BaseModel):
    brand: str
    currency: str
    currency_symbol: str
    set_offers: list[SetOffer]
    products: list[Product]
    market_prices: dict[str, MarketPrices] = {}  # D-179: by market code; used when the market's currency differs


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
    min_spend: float | None = None  # D-149: a gift's spend threshold, in the market's currency


class PromoRules(BaseModel):
    max_active_price_promos: int
    promo_prices_are_final: bool


class PromosFile(BaseModel):
    promos: list[Promo]
    rules: PromoRules


# ---- data/markets/<code>.json + data/lang/<code>.json (D-129) ---------------------------------
# A market pack holds the law (regulator, sources, rules by category with their legal reference and
# severity, currency, offered broadcast languages); a language pack holds the wording (reflex phrases,
# examples, say-instead hints, negation and quote cues). Together they make the ClaimRulesFile below.


class PolicySource(BaseModel):
    source_id: str
    title: str
    file: str | None = None  # a local copy; None for an online-only source (D-150)
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
    required_terms: list[str] = []  # D-290 Q6 (from the language pack's category wording)
    # D-294: the fix that switches the term check on ("G4" for the test-result and evidence categories)
    terms_fix: str = "Q6"
    # D-294 G7: a line with a direction to the group ("on their own") and no promise to it is a usage line
    direction_terms: list[str] = []
    promise_terms: list[str] = []


class Currency(BaseModel):
    code: str
    symbol: str
    minor_units: int


class MarketLanguage(BaseModel):
    lang: str
    stt_language: str  # a chirp_3 code checked by a direct call (docs/research/japac-regulators.md)
    tier: Literal["live", "preview", "not_yet"]
    note: str | None = None


class MarketRule(BaseModel):
    rule_id: str
    category: str  # stable across markets; the language pack's wording is keyed by it
    source_id: str
    source_ref: str
    title: str
    description: str
    severity: Literal["HIGH", "MEDIUM"]


class MarketPack(BaseModel):
    market: str
    phone_pattern: str  # local phone numbers, hidden from chat (prefilter)
    name: str
    regulator: str
    policy_id: str
    category: str
    covers: list[str] = []  # D-227: product categories this law pack also covers ("skincare", "haircare", ...)
    tier: Literal["live", "preview", "not_yet"]
    currency: Currency
    languages: list[MarketLanguage]
    sources: list[PolicySource]
    severity_display: dict[str, str]
    softening_guidance: dict
    rules: list[MarketRule]


class CategoryWording(BaseModel):
    unacceptable_examples: list[str]
    say_instead_hint: str
    reflex_phrases: list[str]
    # D-290 Q6: a line breaks a rule of this category only if it holds one of these (a group or condition for the
    # vulnerable-group rule, a permanence word for the permanent-results rule); empty = no such check
    required_terms: list[str] = []
    # D-294: the fix that switches the term check on ("G4" for the test-result and evidence categories)
    terms_fix: str = "Q6"
    # D-294 G7: a line with a direction to the group ("on their own") and no promise to it is a usage line
    direction_terms: list[str] = []
    promise_terms: list[str] = []


class NumberWords(BaseModel):
    ones: dict[str, int]
    tens: dict[str, int]
    decimal: str
    skip_alone: list[str]
    scales: dict[str, int] = {}  # D-208: "hundred" -> 100, "thousand" -> 1000
    and_word: str | None = None  # D-208: "one hundred and nineteen"


class Stemming(BaseModel):
    suffixes: list[str]
    min_stem: int


class LexiconPatterns(BaseModel):
    unsure: str
    test_qualifier: str
    in_house: str
    sentence_end: str
    sentence_split: str
    clause_split: str


class LexiconData(BaseModel):
    """D-134: what the text guards need of a language (compiled by logic.lexicon.Lexicon)."""
    stopwords: list[str]
    number_words: NumberWords
    stem: Stemming
    prefix_match: int
    patterns: LexiconPatterns
    reactions: list[str]
    exclusion_cues: list[str]  # "not cream", "without the ampoule": the product is excluded, not meant
    fillers: list[str]  # D-148: hesitation and yes/no words that carry no claim ("um", "no no")
    price_contrast_cues: list[str]  # D-148: "normally $36": the live price named as not the price now
    absence_cues: list[str]  # D-151: "no retinol", "retinol-free": the host says an ingredient is absent
    comparison_cues: list[str] = []  # D-248: "more than", "at least": a threshold, not the number alone
    affirmation_cues: list[str] = []
    comparison_kinds: dict[str, list[str]] = {}
    multiplicatives: dict[str, int] = {}  # D-262: "twice" is 2 ("brush twice daily")  # D-259: gt, ge, lt, le, eq: "above 40" is not "at least 40"  # D-252: "and yes", "I agree": the host endorses what they just quoted
    contrast_cues: list[str] = []  # D-294 G2: "4.5 mL, not 45 mL": the value after one is not claimed
    homophones: dict[str, int] = {}  # D-294 G6: speech-to-text sound-alikes of numbers ("too" for 2)
    duration_hours: dict[str, float] = {}  # D-174: "day": 24, "week": 168: "a day later" is "24 hours after"


class LangPack(BaseModel):
    lang: str
    name: str
    categories: dict[str, CategoryWording]
    negation_cues: list[str]
    quote_cues: list[str]
    lexicon: LexiconData


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
    # D-135: no verified answer, said honestly. The _solo lines promise no chat reply: a solo host does not
    # type during a show (planning session); in a team show the operator replies from the list.
    host_deferrals: dict[Literal["general", "sensitive", "general_solo", "sensitive_solo"], str]
