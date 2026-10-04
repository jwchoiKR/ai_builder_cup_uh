"""ComplianceJudge and ContextJudge (`JUDGE_MODE=split3`, the default, D-099): the UtteranceJudge's
jobs in two parallel calls with the same wording.

- ComplianceJudge (jobs 1-2): advertising-rule violations and corrections of active alerts. Its
  verdict alone decides the red alerts, so it is applied as soon as it arrives.
- ContextJudge (jobs 3-4): answer linking, prompter points and cues, product switch.

Both read the same input values as the UtteranceJudge (`build_judge_values`) and get the same checks.
"""
from __future__ import annotations

from ..logic.catalog import Catalog
from ..logic.reflex import Reflex
from ..models.agent_io import ComplianceOutput, ContextOutput
from ..providers.llm import AgentResult, LLMClient, LLMRequest
from ..providers.prompts import PromptTemplate
from .utterance_judge import (
    STATIC_JUDGE_KEYS, JudgeInput, build_judge_values, rule_based_compliance, rule_based_context, symbolic_ids, validate_compliance,
    validate_context,
)


class _SplitJudge:
    name: str
    output_model: type

    def __init__(self, llm: LLMClient, prompts: dict[str, PromptTemplate], catalog: Catalog, reflex: Reflex) -> None:
        self.llm = llm
        self.prompt = prompts[self.name]
        self.prompt_version = self.prompt.version
        self.model = llm.fast.model
        self.catalog = catalog
        self.reflex = reflex

    def fallback(self, inp: JudgeInput, values: dict) -> dict:
        raise NotImplementedError

    def validate(self, out, values: dict):
        raise NotImplementedError

    async def run(self, inp: JudgeInput, *, deadline_ms: int, values: dict | None = None) -> AgentResult:
        values = values if values is not None else build_judge_values(self.catalog, inp)
        encode, decode = symbolic_ids(values)
        user, prefix = self.prompt.render_cached(values, STATIC_JUDGE_KEYS)
        res = await self.llm.call(LLMRequest(
            agent=self.name, model=self.llm.fast.model, thinking_level=self.llm.fast.thinking_level,
            prompt_version=self.prompt_version, system_instruction=self.prompt.system_instruction,
            user_message=user, output_model=self.output_model, deadline_ms=deadline_ms,
            cache_prefix=prefix, cache_ttl_sec=sum(i.planned_duration_sec for i in self.catalog.runsheet.items),
            session_id=inp.session_id, mock_primary_text=inp.utterance, mock_scenario=inp.scenario,
            mock_fallback=lambda _: self.fallback(inp, values),
            fixture_encode=encode, fixture_decode=decode, preview=inp.utterance,
        ))
        if res.output is not None:
            res.output = self.validate(res.output.model_copy(deep=True), values)
        return res


class ComplianceJudge(_SplitJudge):
    name = "compliance_judge"
    output_model = ComplianceOutput

    def fallback(self, inp: JudgeInput, values: dict) -> dict:
        return rule_based_compliance(inp, values, self.catalog, self.reflex)

    def validate(self, out: ComplianceOutput, values: dict) -> ComplianceOutput:
        return validate_compliance(out, self.catalog, values)


class ContextJudge(_SplitJudge):
    name = "context_judge"
    output_model = ContextOutput

    def fallback(self, inp: JudgeInput, values: dict) -> dict:
        return rule_based_context(inp, self.catalog)

    def validate(self, out: ContextOutput, values: dict) -> ContextOutput:
        return validate_context(out, self.catalog, values)
