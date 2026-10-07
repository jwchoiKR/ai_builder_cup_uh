"""ComplianceJudge and ContextJudge (`JUDGE_MODE=split3`, the default, D-099): the UtteranceJudge's
jobs in two parallel calls with the same wording.

- ComplianceJudge (jobs 1-2): advertising-rule violations and corrections of active alerts. Its
  verdict alone decides the red alerts, so it is applied as soon as it arrives.
- ContextJudge (jobs 3-4): answer linking, prompter points and cues, product switch.

Both read the same input values as the UtteranceJudge (`build_judge_values`) and get the same checks.
"""
from __future__ import annotations

import json


from ..logic.catalog import Catalog
from ..logic.reflex import Reflex
from ..models.agent_io import (ComplianceOutput, ComplianceOutputB, ComplianceOutputR, ComplianceOutputRC, ContextOutput,
                               ContextOutputB)
from ..providers import rule_search
from ..providers.docstore import LocalDocStore
from ..providers.llm import AgentResult, LLMClient, LLMRequest
from ..providers.prompts import PromptTemplate
from . import arms, inputs
from .utterance_judge import (
    STATIC_JUDGE_KEYS, JudgeInput, build_judge_values, rule_based_compliance, rule_based_context, symbolic_ids, validate_compliance,
    validate_context,
)


class _SplitJudge:
    name: str
    spec: str  # the LLMClient model spec (D-128)
    output_model: type
    output_model_b: type  # D-187: arms B and C

    def __init__(self, llm: LLMClient, prompts: dict[str, PromptTemplate], catalog: Catalog, reflex: Reflex) -> None:
        self.llm = llm
        self.prompt = prompts[self.name]
        self.prompt_version = self.prompt.version
        self.model = llm.fast.model
        self.catalog = catalog
        self.reflex = reflex
        self.docs: dict[str, tuple[tuple, tuple]] = {}  # D-310: product -> (file parts, file passages), as facts has
        self.with_docs = False
        self.arm = llm.design_arm  # D-187
        # D-304 VERBAL_CHECK=judge: the context judge alone answers with arm B's fields (numbers said, hedged)
        self.b = arms.meaning_to_llm(self.arm) or (
            self.name == "context_judge" and getattr(getattr(llm, "settings", None), "VERBAL_CHECK", "code") == "judge")
        self.system_instruction = arms.system_instruction(self.prompt.system_instruction, self.name, self.arm,
                                                          llm.prompts_path, extra_b=self.b)
        # D-242 arm FR: the record's test results and the qualifier each needs
        self.fact_record = getattr(getattr(llm, "settings", None), "FACT_MODE", "sheet") in ("record", "docs")
        fr = arms._addenda(str(llm.prompts_path)).get(("FR", self.name)) if self.fact_record else None
        if fr:
            self.system_instruction = f"{self.system_instruction}\n\n{fr}"
        # D-290: a switched-on fix's prompt line for this judge (FACT_FIXES Q6)
        from .fact_checker import fixes_of

        for f in sorted(fixes_of(getattr(getattr(llm, "settings", None), "FACT_FIXES", "") or "")):
            if extra := arms._addenda(str(llm.prompts_path)).get((f, self.name)):
                self.system_instruction = f"{self.system_instruction}\n\n{extra}"
        if getattr(getattr(llm, "settings", None), "STT_AWARE", False):  # D-303
            if extra := arms._addenda(str(llm.prompts_path)).get(("STT", self.name)):
                self.system_instruction = f"{self.system_instruction}\n\n{extra}"

    def fallback(self, inp: JudgeInput, values: dict) -> dict:
        raise NotImplementedError

    def extra_data(self) -> str:
        """D-187: data blocks a design arm adds after the user message (the cached prefix stays the same).
        D-191 arms D and E: the whole product sheets."""
        if not arms.whole_facts(self.arm):
            return ""
        return inputs.data_block("PRODUCT_FACTS", inputs.passages_json(inputs.all_passages(self.catalog)))

    def validate(self, out, values: dict):
        raise NotImplementedError

    async def run(self, inp: JudgeInput, *, deadline_ms: int, values: dict | None = None, **opts) -> AgentResult:
        values = values if values is not None else build_judge_values(self.catalog, inp)
        encode, decode = symbolic_ids(values)
        # D-194 arm E: the rules differ per line, so they leave the cached prefix
        user, prefix = self.prompt.render_cached(
            values, STATIC_JUDGE_KEYS - {"rules_compact_json"} if self.arm == "E" else STATIC_JUDGE_KEYS)
        if arms.files(self.arm):  # D-192 arms F1 and F2: the on-air product's file, in the cached prefix
            doc = LocalDocStore(self.catalog).get_product(inp.on_air)
            pre = f'<data name="PRODUCT_FILE">{json.dumps(doc, ensure_ascii=False)}</data>\n'
            user, prefix = pre + user, pre + prefix
        parts: tuple = ()
        if self.with_docs:  # D-310: the on-air product's documents, cached with the rules
            pre, parts = self.documents(inp.on_air)
            user, prefix = pre + user, pre + prefix
        user += self.extra_data()
        b = self.b
        res = await self.llm.call(LLMRequest(
            agent=self.name, model=getattr(self.llm, self.spec).model,
            thinking_level=getattr(self.llm, self.spec).thinking_level,
            prompt_version=self.prompt_version, system_instruction=self.system_instruction,
            user_message=user, output_model=self.output_model_b if b else self.output_model, deadline_ms=deadline_ms,
            cache_prefix=prefix, cache_ttl_sec=sum(i.planned_duration_sec for i in self.catalog.runsheet.items),
            cache_parts=parts,
            session_id=inp.session_id, mock_primary_text=inp.utterance, mock_scenario=inp.scenario,
            mock_fallback=lambda _: self.fallback(inp, values),
            fixture_encode=encode, fixture_decode=decode, preview=inp.utterance, **opts,
        ))
        if res.output is not None:
            res.output = self.validate(res.output.model_copy(deep=True), values)
        return res


def _documents_block(passages) -> str:
    text = json.dumps(inputs.passages_json(passages), ensure_ascii=False).replace("</", "<\\/")
    return f'<data name="PRODUCT_DOCUMENTS">{text}</data>\n'


class ComplianceJudge(_SplitJudge):
    name = "compliance_judge"
    spec = "compliance"
    output_model = ComplianceOutput
    output_model_b = ComplianceOutputB

    def __init__(self, llm: LLMClient, prompts: dict[str, PromptTemplate], catalog: Catalog, reflex: Reflex) -> None:
        super().__init__(llm, prompts, catalog, reflex)
        self.with_docs = bool(getattr(getattr(llm, "settings", None), "COMPLIANCE_DOCS", False))  # D-310
        if self.with_docs and (extra := arms._addenda(str(llm.prompts_path)).get(("DOCS", self.name))):
            self.system_instruction = f"{self.system_instruction}\n\n{extra}"
        if getattr(getattr(llm, "settings", None), "FACT_PROMPT", "v1") in ("v2", "v3", "v4"):  # D-312: sound-alikes
            if extra := arms._addenda(str(llm.prompts_path)).get(("V2", self.name)):
                self.system_instruction = f"{self.system_instruction}\n\n{extra}"
        if getattr(getattr(llm, "settings", None), "FACT_RELATION", False):
            # D-296: a HIGH verdict names the claim the line makes; the rule-fit checks (Q6, G7) read it
            self.output_model = ComplianceOutputR
            if extra := arms._addenda(str(llm.prompts_path)).get(("REL", self.name)):
                self.system_instruction = f"{self.system_instruction}\n\n{extra}"
            if getattr(llm.settings, "JUDGE_ARM", "") == "single":  # D-309: the judge may lower a HIGH
                if extra := arms._addenda(str(llm.prompts_path)).get(("SINGLE", self.name)):
                    self.system_instruction = f"{self.system_instruction}\n\n{extra}"
            if getattr(llm.settings, "VOTE_CONFIDENCE", "off") == "self":  # D-302: a log field
                self.output_model = ComplianceOutputRC
                if extra := arms._addenda(str(llm.prompts_path)).get(("CONF", self.name)):
                    self.system_instruction = f"{self.system_instruction}\n\n{extra}"

    def documents(self, pid: str) -> tuple[str, tuple]:
        """D-310: the product's documents as a data block (its passages and its files' text) and its file parts."""
        parts, file_passages = self.docs.get(pid, ((), ()))
        passages = [p for p in self.catalog.pack.passages if p.product_id == pid] + list(file_passages)
        return _documents_block(passages), parts

    async def warm(self, pid: str, session_id: str | None) -> None:
        """D-310: this product's rules-and-documents cache, made at session start."""
        values = build_judge_values(self.catalog, JudgeInput(utterance="", on_air=pid, session_id=session_id))
        _, prefix = self.prompt.render_cached(values, STATIC_JUDGE_KEYS)
        pre, parts = self.documents(pid)
        await self.llm.warm_cache(LLMRequest(
            agent=self.name, model=self.llm.compliance.model, thinking_level=self.llm.compliance.thinking_level,
            prompt_version=self.prompt_version, system_instruction=self.system_instruction,
            user_message=pre + prefix, output_model=self.output_model, deadline_ms=60_000, cache_prefix=pre + prefix,
            cache_parts=parts, cache_ttl_sec=sum(i.planned_duration_sec for i in self.catalog.runsheet.items),
            session_id=session_id))

    def fallback(self, inp: JudgeInput, values: dict) -> dict:
        return rule_based_compliance(inp, values, self.catalog, self.reflex)

    async def run(self, inp: JudgeInput, *, deadline_ms: int, values: dict | None = None, **opts) -> AgentResult:
        search = rule_search.for_settings(self.llm.settings) if self.arm == "E" else None
        if search is not None:  # D-194 arm E: only the rules the search picks for this line (every rule on failure)
            values = dict(values if values is not None else build_judge_values(self.catalog, inp))
            m = self.catalog.pack.market
            ids = await search.search(inp.utterance, m.market if m is not None else "SG")
            if ids is not None:
                by_id = {r["rule_id"]: r for r in values["rules_compact_json"]}
                values["rules_compact_json"] = [by_id[i] for i in dict.fromkeys(ids) if i in by_id]
        return await super().run(inp, deadline_ms=deadline_ms, values=values, **opts)

    def extra_data(self) -> str:
        if not arms.meaning_to_llm(self.arm):
            if not self.fact_record:
                return ""
            rel = issubclass(self.output_model, ComplianceOutputR)  # D-299: the judge names the result by id
            results = [{"product_id": p.product_id, "say": r.say} | ({"result_id": r.result_id} if rel else {})
                       for p in self.catalog.products
                       for r in p.qualified_results]
            return super().extra_data() + (inputs.data_block("QUALIFIED_RESULTS", results) if results else "")
        # D-187 arm B: the in-house test results the judge picks a qualifier replacement from, by id
        results = [{"result_id": r.result_id, "product_id": p.product_id, "say": r.say}
                   for p in self.catalog.products for r in p.qualified_results]
        return super().extra_data() + inputs.data_block("QUALIFIED_RESULTS", results)

    def validate(self, out: ComplianceOutput, values: dict) -> ComplianceOutput:
        judge_arm = getattr(self.llm.settings, "JUDGE_ARM", "guards")
        return validate_compliance(out, self.catalog, values, arm=self.arm, verify=judge_arm in ("verify", "vote", "single"),
                                   model_severity=judge_arm == "single")  # D-309


class ContextJudge(_SplitJudge):
    name = "context_judge"
    spec = "context"
    output_model = ContextOutput
    output_model_b = ContextOutputB

    def fallback(self, inp: JudgeInput, values: dict) -> dict:
        return rule_based_context(inp, self.catalog)

    def validate(self, out: ContextOutput, values: dict) -> ContextOutput:
        return validate_context(out, self.catalog, values)
