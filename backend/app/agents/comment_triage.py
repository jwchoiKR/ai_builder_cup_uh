"""CommentTriage agent (DEV_SPEC §7.5): classifies one viewer comment. Code decides route,
purchase impact and sensitivity from intents.json."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..config import Settings
from ..logic.catalog import Catalog
from ..logic.grouping import normalise_question
from ..models.agent_io import SLOT_KEYS, CommentTriageOutput, ConditionSlots
from ..models.session import QuestionGroup
from ..providers.llm import AgentResult, LLMClient, LLMRequest
from ..providers.prompts import PromptTemplate
from . import inputs

GROUP_REF = "@group:"
MAX_CANONICAL_FALLBACK = 120


@dataclass
class TriageInput:
    text: str  # full comment text; truncated to MAX_COMMENT_CHARS for the model
    context_product_id: str | None
    open_groups: list[QuestionGroup] = field(default_factory=list)
    session_id: str | None = None
    scenario: str = "default"


def post_validate(out: CommentTriageOutput, catalog: Catalog, text: str, open_group_ids: set[str]) -> CommentTriageOutput:
    o = out.model_copy(deep=True)
    if o.product_id is not None and not catalog.is_product(o.product_id):
        o.product_id, o.product_basis = None, "unknown"
    if o.product_id is None and o.product_basis in ("explicit", "content"):
        o.product_basis = "unknown"
    intents = catalog.pack.intents_by_name
    if o.intent is not None and o.intent not in intents:
        o.intent = "other"
    if o.kind == "question" and o.intent is None:
        o.intent = "other"
    allowed = catalog.pack.intents.condition_slots
    for key in SLOT_KEYS:
        value = getattr(o.condition_slots, key)
        if value is not None and value not in allowed.get(key, []):
            setattr(o.condition_slots, key, None)
    if o.group_candidate_id not in open_group_ids:
        o.group_candidate_id = None
    if o.kind == "question" and not o.canonical_question.strip():
        o.canonical_question = text.strip()[:MAX_CANONICAL_FALLBACK]
    if o.kind == "hide" and o.hide_category is None:
        o.hide_category = "spam"
    return o


class CommentTriage:
    name = "comment_triage"

    def __init__(self, llm: LLMClient, prompt: PromptTemplate, catalog: Catalog, settings: Settings) -> None:
        self.llm = llm
        self.prompt = prompt
        self.prompt_version = prompt.version
        self.model = llm.fast.model
        self.catalog = catalog
        self.settings = settings

    async def run(self, inp: TriageInput, *, deadline_ms: int) -> AgentResult[CommentTriageOutput]:
        groups = inputs.open_groups_json(inp.open_groups, self.settings.TRIAGE_MAX_OPEN_GROUPS)
        group_ids = {g["group_id"] for g in groups}
        by_question = {normalise_question(g["canonical_question"]): g["group_id"] for g in groups}
        id_to_question = {g["group_id"]: normalise_question(g["canonical_question"]) for g in groups}

        def encode(data: dict) -> dict:
            gid = data.get("group_candidate_id")
            if gid in id_to_question:
                data["group_candidate_id"] = GROUP_REF + id_to_question[gid]
            return data

        def decode(data: dict) -> dict:
            ref = data.get("group_candidate_id")
            if isinstance(ref, str) and ref.startswith(GROUP_REF):
                data["group_candidate_id"] = by_question.get(ref[len(GROUP_REF):])
            return data

        user = self.prompt.render({
            "products_compact_json": inputs.products_compact_json(self.catalog),
            "product_id_at_comment_time_minus_grace": inputs.product_id_at_comment_time_minus_grace(inp.context_product_id),
            "intent_names_json": inputs.intent_names_json(self.catalog),
            "condition_slots_json": inputs.condition_slots_json(self.catalog.pack.intents.condition_slots),
            "open_groups_json": groups,
            "comment_text": inputs.comment_text(inp.text, self.settings.MAX_COMMENT_CHARS),
        })
        res = await self.llm.call(LLMRequest(
            agent=self.name, model=self.llm.fast.model, thinking_level=self.llm.fast.thinking_level,
            prompt_version=self.prompt_version, system_instruction=self.prompt.system_instruction,
            user_message=user, output_model=CommentTriageOutput, deadline_ms=deadline_ms,
            session_id=inp.session_id, mock_primary_text=inp.text, mock_scenario=inp.scenario,
            mock_fallback=lambda _: rule_based_triage(inp.text, inp.context_product_id, self.catalog),
            fixture_encode=encode, fixture_decode=decode, preview=inp.text,
        ))
        if res.output is not None:
            res.output = post_validate(res.output, self.catalog, inp.text, group_ids)
        return res


# ---- rule-based fallback for unit tests (mock provider without a fixture) -----------------------

_INTENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("pregnancy_breastfeeding", ("pregnan", "breastfeed")),
    ("medical_condition", ("eczema", "dermatitis", "rosacea")),
    ("efficacy_claim", ("wrinkle", "scar")),
    ("allergy_sensitivity", ("sting", "tingl", "allerg", "irritat")),
    ("shipping", ("ship", "deliver")),
    ("returns", ("return", "refund")),
    ("payment", ("paynow", "payment", "pay ")),
    ("set_price", ("set price", "the set", "set with")),
    ("promo", ("time sale", "promo", "discount")),
    ("ingredient_amount", ("how much niacinamide", "percent", "%")),
    ("price", ("price", "how much", "cost")),
    ("volume", (" ml", "how big", "size")),
    ("fragrance", ("fragrance", "scent", "smell")),
    ("makeup_compatibility", ("makeup", "foundation")),
    ("skin_type_suitability", ("oily", "dry skin", "combination skin", "sensitive skin")),
    ("how_to_use", ("vitamin c", "morning", "night", "how to use", "drops", "mix")),
    ("texture", ("sticky", "texture", "heavy", "greasy")),
    ("origin", ("made",)),
    ("ingredients", ("ingredient", "niacinamide")),
]
_QUESTION_HINT = re.compile(r"\?|\b(how|what|can|is|does|do|will|which|where|when|pls|please)\b", re.IGNORECASE)


def rule_based_triage(text: str, context_product_id: str | None, catalog: Catalog) -> dict:
    t = f" {text.lower()} "
    empty_slots = ConditionSlots(skin_type=None, life_stage=None, condition=None, combined_with=None, time_of_day=None)
    if not _QUESTION_HINT.search(text):
        return CommentTriageOutput(kind="reaction", hide_category=None, product_id=None, product_basis="unknown",
                                   intent=None, condition_slots=empty_slots, canonical_question="",
                                   group_candidate_id=None, reason="rule-based: no question").model_dump()
    intent = next((name for name, keys in _INTENT_RULES if any(k in t for k in keys)), "other")
    slots = empty_slots.model_copy()
    for skin in ("oily", "dry", "combination", "sensitive"):
        if skin in t:
            slots.skin_type = skin
    if "pregnan" in t:
        slots.life_stage = "pregnant"
    elif "breastfeed" in t:
        slots.life_stage = "breastfeeding"
    if "vitamin c" in t:
        slots.combined_with = "vitamin_c"
    named = catalog.product_by_alias(text)
    scope = catalog.pack.intents_by_name[intent].product_scope
    if scope == "none":
        pid, basis = None, "unknown"
    elif named:
        pid, basis = named, "explicit"
    else:
        pid, basis = context_product_id, "context" if context_product_id else "unknown"
    return CommentTriageOutput(kind="question", hide_category=None, product_id=pid, product_basis=basis,
                               intent=intent, condition_slots=slots, canonical_question=text.strip()[:120],
                               group_candidate_id=None, reason="rule-based").model_dump()
