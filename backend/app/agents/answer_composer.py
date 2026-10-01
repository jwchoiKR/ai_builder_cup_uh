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
from . import inputs

KEY_FACT_INTENTS = frozenset({"price", "set_price", "promo", "volume"})


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
) -> list[Passage]:
    """§7.6 retrieval: top-k search filtered to the product (each product for multi), plus Key facts
    for price/volume intents, plus the promo passage while a price promo runs."""
    pids = [product_id] if product_id else [p.product_id for p in catalog.products]
    out: dict[str, Passage] = {}
    for pid in pids:
        query = f"{catalog.get_product(pid).name} {canonical_question}"
        for p in await retriever.search(query, product_filter=pid, top_k=top_k, timeout_ms=timeout_ms):
            out.setdefault(p.passage_id, p)
        if intent in KEY_FACT_INTENTS:
            key_facts = [p for p in prefetched.get(pid) or await retriever.prefetch(pid) if p.section == "Key facts"]
            for p in key_facts:
                out.setdefault(p.passage_id, p)
    active = price_promo(promo)
    if active is not None:
        pp = promo_passage(active, catalog)
        out[pp.passage_id] = pp
    return list(out.values())


class AnswerComposer:
    name = "answer_composer"

    def __init__(self, llm: LLMClient, prompt: PromptTemplate, catalog: Catalog) -> None:
        self.llm = llm
        self.prompt = prompt
        self.prompt_version = prompt.version
        self.model = llm.quality.model
        self.catalog = catalog

    async def run(self, inp: ComposeInput, *, deadline_ms: int) -> AgentResult[ComposerOutput]:
        user = self.prompt.render({
            "product_compact_json": inputs.product_compact_json(self.catalog, inp.product_id),
            "active_promo_json_or_null": inputs.active_promo_json_or_null(self.catalog, inp.promo),
            "set_offers_json": inputs.set_offers_json(self.catalog, inp.promo),
            "canonical_question": inputs.canonical_question(inp.canonical_question),
            "condition_slots_json": inputs.condition_slots_json(inp.slots),
            "passages_json": inputs.passages_json(inp.passages),
        })
        primary = compose_primary_text(inp.product_id, inp.canonical_question, inp.promo)
        return await self.llm.call(LLMRequest(
            agent=self.name, model=self.llm.quality.model, thinking_level=self.llm.quality.thinking_level,
            prompt_version=self.prompt_version, system_instruction=self.prompt.system_instruction,
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
