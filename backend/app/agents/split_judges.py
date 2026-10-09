"""ComplianceJudge and ContextJudge (`JUDGE_MODE=split3`, the default, D-099): the UtteranceJudge's
jobs in two parallel calls with the same wording.

- ComplianceJudge (jobs 1-2): advertising-rule violations and corrections of active alerts. Its
  verdict alone decides the red alerts, so it is applied as soon as it arrives.
- ContextJudge (jobs 3-4): answer linking, prompter points and cues, product switch.

Both read the same input values as the UtteranceJudge (`build_judge_values`) and get the same checks.
"""
from __future__ import annotations

import json
import logging


from ..logic.catalog import Catalog
from ..logic.reflex import Reflex
from ..models.agent_io import (ComplianceOutput, ComplianceOutputB, ComplianceOutputO,
                               ContextOutput,
                               ContextOutputB, ContextOutputQ, with_alert_checks, with_product,
                               with_same_as, with_switch_naming)
from ..providers.docstore import LocalDocStore
from ..providers.llm import AgentResult, LLMClient, LLMRequest
from ..providers.prompts import PromptTemplate
from . import arms, inputs
from .utterance_judge import (
    STATIC_JUDGE_KEYS, JudgeInput, build_judge_values, rule_based_compliance, rule_based_context, symbolic_ids, validate_compliance,
    validate_context, validate_original,
)


log = logging.getLogger(__name__)

# D-406: sent only with a merged line's re-judgment (a line speech-to-text split)
MERGED_NOTE = (
    'UTTERANCE joins lines that speech-to-text split. `chain_handles` are the ACTIVE_ALERTS entries raised '
    'from those lines. For each violation, `same_as` is the one of `chain_handles` whose claim it repeats '
    '(the same claim from the split line), else null. Example: A1 is "cures eczema"; UTTERANCE "It cures '
    'eczema and psoriasis too." gives "cures eczema" `same_as` "A1" and "psoriasis too" null.')

# D-358: the live compliance judge reads the regulation originals; there is no rule-JSON fallback in production. The
# rules path (LEGACY_RULES) is kept only for the test suite, which pins it. D-391: the mock provider runs the
# originals path, like production; None and False: originals; True: the rules path (tests).
LEGACY_RULES: bool | None = None


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
        self.with_docs = False
        self.arm = llm.design_arm  # D-187
        # D-304 VERBAL_CHECK=judge: the context judge alone answers with arm B's fields (numbers said, hedged)
        self.b = arms.meaning_to_llm(self.arm) or (
            self.name == "context_judge" and getattr(getattr(llm, "settings", None), "VERBAL_CHECK", "code") == "judge")
        self.system_instruction = arms.system_instruction(self.prompt.system_instruction, self.name, self.arm,
                                                          llm.prompts_path, extra_b=self.b)
        # D-242 arm FR: the record's test results and the qualifier each needs
        self.fact_record = getattr(getattr(llm, "settings", None), "FACT_MODE", "sheet") in ("record", "docs",
                                                                                              "prompter")
        fr = arms._addenda(str(llm.prompts_path)).get(("FR", self.name)) if self.fact_record else None
        if fr:
            self.system_instruction = f"{self.system_instruction}\n\n{fr}"
        # D-290: a switched-on fix's prompt line for this judge (FACT_FIXES Q6)
        from .fact_checker import fixes_of

        for f in sorted(fixes_of(getattr(getattr(llm, "settings", None), "FACT_FIXES", "") or "")):
            if extra := arms._addenda(str(llm.prompts_path)).get((f, self.name)):
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

    def scope_data(self, inp: JudgeInput) -> str:
        """D-349: data blocks for this line's scope (none by default)."""
        return ""

    def model_for(self, inp: JudgeInput, model: type) -> type:
        return model

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
        user += self.extra_data() + self.scope_data(inp)
        b = self.b
        res = await self.llm.call(LLMRequest(
            agent=self.name, model=getattr(self.llm, self.spec).model,
            thinking_level=getattr(self.llm, self.spec).thinking_level,
            prompt_version=self.prompt_version, system_instruction=self.system_instruction,
            user_message=user, output_model=self.model_for(inp, self.output_model_b if b else self.output_model),
            deadline_ms=deadline_ms,
            cache_prefix=prefix, cache_ttl_sec=sum(i.planned_duration_sec for i in self.catalog.runsheet.items),
            cache_parts=parts,
            session_id=inp.session_id, mock_primary_text=inp.utterance, mock_scenario=inp.scenario,
            mock_fallback=lambda _: self.fallback(inp, values),
            fixture_encode=encode, fixture_decode=decode, preview=inp.utterance, **opts,
        ))
        if res.output is not None:
            res.output = self.validate(res.output.model_copy(deep=True), values)
        return res


class ComplianceJudge(_SplitJudge):
    name = "compliance_judge"
    spec = "compliance"
    output_model = ComplianceOutput
    output_model_b = ComplianceOutputB

    def __init__(self, llm: LLMClient, prompts: dict[str, PromptTemplate], catalog: Catalog, reflex: Reflex) -> None:
        legacy = bool(LEGACY_RULES)  # D-391: the mock provider runs the production path too
        originals = not legacy
        if not originals and "compliance_judge_rules" in prompts:  # the legacy path keeps its own prompt
            prompts = {**prompts, "compliance_judge": prompts["compliance_judge_rules"]}
        super().__init__(llm, prompts, catalog, reflex)
        self.originals = originals
        if self.originals:  # D-358: one instruction, the originals as the cached prefix, handles, cited verdicts
            self.system_instruction = self.prompt.system_instruction
            self.output_model = self.output_model_b = ComplianceOutputO
            self.with_docs = self.handles = True
            self._docs = None
            return
        self.handles = False  # D-435: the rules-JSON path answers by alert id (handles are the originals path's)

    def regulation(self):
        """D-358: the originals behind the show's products' rules. D-363 (user): loaded ONCE, at show start (the cache
        warm-up, or the first line), and fixed for the show: the prefix the judge gets and the quote check always use
        this one snapshot. A missing original is logged once here and stays marked for the show (the release screen
        warns before the show)."""
        if self._docs is None:
            from .originals import originals_for

            self._docs = originals_for(self.catalog, self.llm.settings.onboarding_path, self.catalog.order)
            if self._docs[1]:
                log.warning("compliance originals missing for this show (not given to the judge): %s",
                            list(self._docs[1]))
        return self._docs

    def documents(self, pid: str) -> tuple[str, tuple]:
        """D-358: the regulation originals: each file after a "FILE <name>" line, and a REGULATION_DOCUMENTS block
        naming them (only the originals path sets with_docs; D-432: the D-310 product-documents branch is gone)."""
        docs, _ = self.regulation()
        parts = tuple(x for d in docs for x in ((f"FILE {d.name}".encode(), "text/plain"), (d.data, d.mime)))
        index = [{"document": d.name, "title": d.title} for d in docs]
        return inputs.data_block("REGULATION_DOCUMENTS", index) + "\n", parts

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
        if self.originals:  # no rule-based verdict without the rules
            return {"alert_checks": [], "compliance": {"violations": []}, "reason": "no verdict"}
        return rule_based_compliance(inp, values, self.catalog, self.reflex)

    @staticmethod
    def _previous(inp: JudgeInput) -> str | None:
        prev = inp.switch.previous_product_id
        return prev if prev and prev != inp.on_air else None

    def scope_data(self, inp: JudgeInput) -> str:
        """D-349 SWITCH_MODE=immediate: in the seconds after a switch, the product that just left the air, labelled."""
        prev = self._previous(inp)
        # D-406: a merged line's re-judgment (a line speech-to-text split) is asked which listed alert it repeats
        merged = ""
        if self.originals and inp.chain:  # D-410: with the handles of the chain's own alerts (as _with_handles numbers)
            by_id = {a.alert_id: a for a in inp.active_alerts}
            chain = [f"A{i}" for i, row in enumerate(inputs.active_alerts_json(inp.active_alerts), 1)
                     if by_id[row["alert_id"]].transcript_id in inp.chain]
            merged = inputs.data_block("MERGED_LINE", {"note": MERGED_NOTE, "chain_handles": chain})
        if prev is None:
            return merged
        return merged + inputs.data_block("PREVIOUS_PRODUCT", {
            "note": ("The host switched products a few seconds ago. CURRENT_PRODUCT is now on air; this product was "
                     "on air just before. For each violation, set product_id to the product the claim is about "
                     "(CURRENT_PRODUCT or this one) and take say_instead from that product's approved claims."),
            "product": inputs.current_product_json(self.catalog, prev),
            "approved_claims": inputs.approved_claims_of_current_product_json(self.catalog, prev)})

    def model_for(self, inp: JudgeInput, model: type) -> type:
        model = with_product(model) if self._previous(inp) else model
        model = with_same_as(model, "violations") if self.originals and inp.chain else model  # D-406
        return with_alert_checks(model) if self.handles else model

    def _with_handles(self, inp: JudgeInput, values: dict) -> dict:
        """D-356: ACTIVE_ALERTS as handles (A1, A2 ...) with span, rule and status; the handle -> id map stays in
        the values (never sent) and restores the ids before the id check."""
        by_id = {a.alert_id: a for a in inp.active_alerts}
        shown, handles = [], {}
        for i, row in enumerate(values["active_alerts_json"], 1):
            a = by_id.get(row["alert_id"])
            handles[f"A{i}"] = row["alert_id"]
            # D-403: and how many seconds ago it was raised, so the model can tell a repeat from a new claim
            age = max(0, (inp.now - a.created_at) // 1000) if inp.now is not None and a is not None else None
            shown.append({"handle": f"A{i}", "product_id": row.get("product_id"), "span": row["span"],
                          "rule_id": row["rule_id"], "status": "active", "say_instead": row.get("say_instead"),
                          "raised_s_ago": age})
        return {**values, "active_alerts_json": shown, "alert_handles": handles}

    async def run(self, inp: JudgeInput, *, deadline_ms: int, values: dict | None = None, **opts) -> AgentResult:
        if (prev := self._previous(inp)) is not None:  # D-349: the products a violation may name
            values = {**(values if values is not None else build_judge_values(self.catalog, inp)),
                      "scope_product_ids": [inp.on_air, prev]}
        if self.handles:
            values = self._with_handles(inp, values if values is not None else build_judge_values(self.catalog, inp))
        res = await super().run(inp, deadline_ms=deadline_ms, values=values, **opts)
        if self.originals and (missing := self.regulation()[1]):
            res.meta["originals_missing"] = list(missing)  # D-358: judged without these sources' documents
        if self.handles:  # D-356: per call, what was shown, the handle map and the answer
            log.info("compliance handles call=%s line=%r active_alerts=%s handles=%s answer=%s corrects=%s",
                     res.call_id, inp.utterance[:80], json.dumps(values["active_alerts_json"], ensure_ascii=False),
                     values["alert_handles"],
                     [c.model_dump() for c in res.output.alert_checks] if res.output is not None else res.status,
                     res.output.correction.corrects_alert_ids if res.output is not None else None)
        return res

    def validate(self, out: ComplianceOutput, values: dict) -> ComplianceOutput:
        handles = values.get("alert_handles")
        if handles is not None:  # D-356: the handles the model said this line fixes, as ids, before the id check
            checks = getattr(out, "alert_checks", [])
            unknown = [c.handle for c in checks if c.handle not in handles]
            if unknown:
                log.info("compliance handles: unknown handles dropped: %s (shown: %s)", unknown, sorted(handles))
            out.correction.corrects_alert_ids = list(dict.fromkeys([
                *out.correction.corrects_alert_ids,
                *(handles[c.handle] for c in checks if c.fixed_by_this_line and c.handle in handles)]))
            for v in out.compliance.violations:  # D-403: the alert a violation repeats, by handle, as its id
                if getattr(v, "same_as", None) is not None:
                    if v.same_as not in handles:
                        log.info("compliance same_as %r is not a listed handle: a new alert (shown: %s)", v.same_as,
                                 sorted(handles))
                    v.same_as = handles.get(v.same_as)
            values = {**values, "active_alerts_json": [{"alert_id": i} for i in handles.values()]}
        if self.originals:
            return validate_original(out, self.catalog, values, self.regulation()[0])  # the show's snapshot
        return validate_compliance(out, self.catalog, values)


class ContextJudge(_SplitJudge):
    name = "context_judge"
    spec = "context"
    output_model = ContextOutput
    output_model_b = ContextOutputB

    def __init__(self, llm: LLMClient, prompts: dict[str, PromptTemplate], catalog: Catalog, reflex: Reflex) -> None:
        super().__init__(llm, prompts, catalog, reflex)
        self.output_model = ContextOutputQ  # D-335: does the next line resolve it?
        if extra := arms._addenda(str(llm.prompts_path)).get(("QHOLD", self.name)):
            self.system_instruction = f"{self.system_instruction}\n\n{extra}"
        # D-351: the switch verdict names the next product (D-415: the only switch mode)
        self.output_model = with_switch_naming(self.output_model)
        self.output_model_b = with_switch_naming(self.output_model_b)
        if extra := arms._addenda(str(llm.prompts_path)).get(("SWITCH", self.name)):
            self.system_instruction = f"{self.system_instruction}\n\n{extra}"

    def fallback(self, inp: JudgeInput, values: dict) -> dict:
        return rule_based_context(inp, self.catalog)

    def validate(self, out: ContextOutput, values: dict) -> ContextOutput:
        return validate_context(out, self.catalog, values)
