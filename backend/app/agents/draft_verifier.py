"""DraftVerifier agent (proof-plan item 3, D-126): an LLM check of a composed answer against the passages
it cites, after the code checks of `verify_answer`. It catches what code cannot: reversed meaning, invented
facts and policies, overstated results, weakened cautions and replies that answer another question."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..logic.catalog import Catalog
from ..models.agent_io import DraftCheckOutput
from ..models.data import Passage, Promo
from ..providers.llm import AgentResult, LLMClient, LLMRequest
from ..providers.prompts import PromptTemplate
from . import arms, inputs


@dataclass
class DraftCheckInput:
    product_id: str | None
    question: str
    answer: str
    promo: Promo | None
    passages: list[Passage]  # the cited passages (D-191 arms D and E: the whole sheet)
    session_id: str | None = None
    scenario: str = "default"


def cited_passages(cited_ids: Sequence[str], passages: Sequence[Passage]) -> list[Passage]:
    by_id = {p.passage_id: p for p in passages}
    return [by_id[pid] for pid in dict.fromkeys(cited_ids) if pid in by_id]


class DraftVerifier:
    name = "draft_verifier"

    def __init__(self, llm: LLMClient, prompt: PromptTemplate, catalog: Catalog) -> None:
        self.llm = llm
        self.prompt = prompt
        self.prompt_version = prompt.version
        self.model = llm.fast.model
        self.catalog = catalog
        self.system_instruction = arms.system_instruction(prompt.system_instruction, self.name, llm.design_arm,
                                                          llm.prompts_path)  # D-191

    async def run(self, inp: DraftCheckInput, *, deadline_ms: int) -> AgentResult[DraftCheckOutput]:
        user = self.prompt.render({
            "product_compact_json": inputs.product_compact_json(self.catalog, inp.product_id),
            "active_promo_json_or_null": inputs.active_promo_json_or_null(self.catalog, inp.promo),
            "passages_json": inputs.passages_json(inp.passages),
            "canonical_question": inputs.canonical_question(inp.question),
            "draft_answer_json": inputs.draft_answer_json(inp.answer),
        })
        if arms.agents_decide(self.llm.design_arm):  # D-191 arms D and E: the advertising rules, whole
            user += inputs.data_block("RULES", inputs.rules_compact_json(self.catalog))
        return await self.llm.call(LLMRequest(
            agent=self.name, model=self.llm.fast.model, thinking_level=self.llm.fast.thinking_level,
            prompt_version=self.prompt_version, system_instruction=self.system_instruction,
            user_message=user, output_model=DraftCheckOutput, deadline_ms=deadline_ms,
            session_id=inp.session_id, mock_primary_text=f"{inp.product_id or '*'}|{inp.answer}",
            mock_scenario=inp.scenario,
            # unit tests without fixtures: the code checks alone decide
            mock_fallback=lambda _: {"verdict": "pass", "problems": [], "reason": "rule-based: no LLM check"},
            preview=f"{inp.product_id or 'multi'}: {inp.answer[:80]}",
        ))
