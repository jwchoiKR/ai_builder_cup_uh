"""AnswerComposer agent (DEV_SPEC §7.6): short cited answer to a question group, verified by code."""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from ..logic.catalog import Catalog
from ..logic.promos import price_promo, promo_passage, promo_state
from ..models.agent_io import ComposerOutput
from ..models.data import Passage, Promo
from ..providers.llm import AgentResult, LLMClient, LLMRequest
from ..providers.prompts import PromptTemplate
from ..providers.retriever import Retriever
from . import arms, inputs

KEY_FACT_INTENTS = frozenset({"price", "set_price", "promo", "volume"})
# D-068: intents whose answer sits in a fixed section that BM25 may miss ("Where is it manufactured?"
# vs "Made in: ..."; "Does it sting?" vs "tingling"). Added on top of §7.6, never instead of it.
SECTION_INTENTS: dict[str, tuple[str, ...]] = {
    "origin": ("Key facts",), "packaging": ("Key facts",), "shelf_life": ("Key facts",),
    "texture": ("Key facts",), "fragrance": ("Key facts",), "ingredient_amount": ("Key ingredients",),
    "ingredients": ("Key ingredients",), "allergy_sensitivity": ("Cautions",),
    "pregnancy_breastfeeding": ("Cautions",), "medical_condition": ("Cautions",), "age_suitability": ("Cautions",),
    # D-153 (00007 show replays): "How many drops?" never retrieved "Apply two to three drops ..."
    "how_to_use": ("How to use",), "routine_order": ("How to use",),
    # D-190 (comment flow CF06: "will this ampoule remove wrinkles?" drafted nothing, because search found the
    # not-approved list but not the approved "Helps reduce the look of fine dryness lines"): an efficacy question is
    # answered from the approved claims
    "efficacy_claim": ("Approved on-air claims",),
}


@dataclass
class ComposeInput:
    product_id: str | None  # None for product_scope=multi
    intent: str
    slots: dict[str, str | None]
    canonical_question: str
    promo: Promo | None
    passages: list[Passage]
    session_id: str | None = None
    scenario: str = "default"
    sensitive: bool = False
    rules: bool = True  # D-192 arm F1: RULES only when the tool step fetched them


def compose_primary_text(product_id: str | None, canonical_question: str, promo: Promo | None) -> str:
    return f"{product_id or '*'}|{canonical_question}|{promo_state(promo)}"


async def gather_passages(
    retriever: Retriever,
    catalog: Catalog,
    prefetched: dict[str, list[Passage]],
    *,
    product_id: str | None,
    intent: str,
    canonical_question: str,
    promo: Promo | None,
    top_k: int,
    timeout_ms: int = 2000,
    offers: Sequence[Promo] = (),
    search: bool = True,
) -> list[Passage]:
    """§7.6 retrieval: top-k search filtered to the product (each product for multi), plus Key facts
    for price/volume intents, plus the promo passage while a price promo runs."""
    pids = [product_id] if product_id and search else [p.product_id for p in catalog.products] if search else []
    out: dict[str, Passage] = {}
    for pid in pids:
        query = f"{catalog.get_product(pid).name} {canonical_question}"
        for p in await retriever.search(query, product_filter=pid, top_k=top_k, timeout_ms=timeout_ms):
            out.setdefault(p.passage_id, p)
        sections = (("Key facts",) if intent in KEY_FACT_INTENTS else ()) + SECTION_INTENTS.get(intent, ())
        if sections:
            # D-190: a section outside the prefetched ones (the approved claims) is read from the index directly
            by_section = getattr(retriever, "sections", None)
            pool = (prefetched.get(pid) or await retriever.prefetch(pid)) + (
                by_section(pid, sections) if callable(by_section) else [])
            for p in pool:
                if p.section in sections:
                    out.setdefault(p.passage_id, p)
    active = price_promo(promo)
    if active is not None:
        pp = promo_passage(active, catalog)
        out[pp.passage_id] = pp
    if intent == "promo":  # D-168: a running offer's terms ("free pouch over how much?")
        for o in offers:
            op = promo_passage(o, catalog)
            out[op.passage_id] = op
    return list(out.values())


class AnswerComposer:
    name = "answer_composer"

    def __init__(self, llm: LLMClient, prompt: PromptTemplate, catalog: Catalog) -> None:
        self.llm = llm
        self.prompt = prompt
        self.prompt_version = prompt.version
        self.model = llm.composer.model
        self.catalog = catalog
        self.system_instruction = arms.system_instruction(prompt.system_instruction, self.name, llm.design_arm,
                                                          llm.prompts_path)  # D-191

    async def run(self, inp: ComposeInput, *, deadline_ms: int) -> AgentResult[ComposerOutput]:
        user = self.prompt.render({
            "product_compact_json": inputs.product_compact_json(self.catalog, inp.product_id),
            "active_promo_json_or_null": inputs.active_promo_json_or_null(self.catalog, inp.promo),
            "set_offers_json": inputs.set_offers_json(self.catalog, inp.promo),
            "canonical_question": inputs.canonical_question(inp.canonical_question),
            "condition_slots_json": inputs.condition_slots_json(inp.slots),
            "passages_json": inputs.passages_json(inp.passages),
            "avoid_saying_json": inputs.avoid_saying_json(self.catalog, inp.product_id),
        })
        if arms.agents_decide(self.llm.design_arm) and inp.rules:  # D-191 arms D to F2: the advertising rules, whole
            user += inputs.data_block("RULES", inputs.rules_compact_json(self.catalog))
        primary = compose_primary_text(inp.product_id, inp.canonical_question, inp.promo)
        return await self.llm.call(LLMRequest(
            agent=self.name, model=self.llm.composer.model, thinking_level=self.llm.composer.thinking_level,
            prompt_version=self.prompt_version, system_instruction=self.system_instruction,
            user_message=user, output_model=ComposerOutput, deadline_ms=deadline_ms,
            session_id=inp.session_id, mock_primary_text=primary, mock_scenario=inp.scenario,
            mock_fallback=lambda _: rule_based_answer(inp.passages, inp.sensitive),
            preview=f"{inp.product_id or 'multi'}: {inp.canonical_question}",
        ))


# ---- rule-based fallback for unit tests -----------------------------------------------------------


def rule_based_answer(passages: Sequence[Passage], sensitive: bool) -> dict:
    """Answer with the first sentence of the best passage (FAQ answers first), quoted verbatim."""
    ranked = sorted(passages, key=lambda p: (" A: " not in p.text, -p.score))
    for p in ranked:
        body = p.text.split(" A: ", 1)[1] if " A: " in p.text else p.text
        sentence = re.split(r"(?<=[.!?])\s+", body.strip())[0]
        if sentence:
            return ComposerOutput(answer=sentence, citations=[{"passage_id": p.passage_id, "quote": sentence}],
                                  grounded=True, needs_human=sensitive, reason="rule-based").model_dump()
    return ComposerOutput(answer="", citations=[], grounded=False, needs_human=True,
                          reason="rule-based: no passage").model_dump()
