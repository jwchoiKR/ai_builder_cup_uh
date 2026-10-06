"""D-300 (R2, JUDGE_ARM=verify): one stronger model reads each candidate alert with the evidence and keeps or rejects
it. The flaggers (compliance judge, fact checker) run with their code drops off; code here checks only schema and
provenance: the evidence id exists, and a correction's number is in the product's passages. Nothing silently becomes
safe: a verifier timeout keeps the candidate as an unverified alert, and every reject is logged with its reason."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from ..logic import qualifier
from ..logic.catalog import Catalog
from ..models.agent_io import ComplianceOutput, FactCheckOutput, VerifyOutput
from ..models.data import Passage
from ..providers.llm import AgentResult, LLMClient, LLMRequest
from ..providers.prompts import PromptTemplate
from .fact_checker import _drop, _numbers, _product_numbers, sentence_index
from .utterance_judge import _cdrop

log = logging.getLogger(__name__)


class Verifier:
    name = "verifier"

    def __init__(self, llm: LLMClient, prompt: PromptTemplate, catalog: Catalog,
                 files: dict[str, tuple[tuple, tuple]] | None = None) -> None:
        self.llm, self.prompt, self.catalog = llm, prompt, catalog
        self.files = files or {}  # product id -> (model parts, file passages), as the fact checker has them
        self._sources: dict[str, tuple[list[dict], dict]] = {}

    def source(self, pid: str) -> tuple[list[dict], dict]:
        """The product's documents, numbered once per product (the cached prefix of every call)."""
        if pid not in self._sources:
            passages = [p for p in self.catalog.pack.passages if p.product_id == pid]
            self._sources[pid] = sentence_index([*passages, *self.files.get(pid, ((), ()))[1]])
        return self._sources[pid]

    async def _one(self, pid: str, cand: dict, line: str, previous: Sequence[str],
                   session_id: str | None) -> tuple[AgentResult, dict]:
        blocks, index = self.source(pid)
        user, prefix = self.prompt.render_cached({
            "passages_json": blocks, "candidate_json": cand,
            "last_two_final_transcripts_json": list(previous)[-2:], "utterance_text": line}, {"passages_json"})
        s = self.llm.settings
        res = await self.llm.call(LLMRequest(
            agent=self.name, model=self.llm.verify.model, thinking_level=self.llm.verify.thinking_level,
            prompt_version=self.prompt.version, system_instruction=self.prompt.system_instruction, user_message=user,
            output_model=VerifyOutput, deadline_ms=s.VERIFY_TIMEOUT_MS, session_id=session_id, cache_prefix=prefix,
            cache_parts=self.files.get(pid, ((), ()))[0],
            cache_ttl_sec=sum(i.planned_duration_sec for i in self.catalog.runsheet.items),
            mock_primary_text=f"{line}|{cand.get('span', '')}",
            mock_fallback=lambda _: {"evidence": None, "reason": "mock: kept", "decision": "keep", "severity": None},
            preview=f"{line} | {cand.get('kind')}: {cand.get('span', '')}",
        ))
        return res, index

    async def check_compliance(self, out: ComplianceOutput, line: str, previous: Sequence[str], on_air: str,
                               session_id: str | None = None) -> ComplianceOutput:
        cands = [v for v in out.compliance.violations if not v.is_negated and not v.is_quoted]
        if not cands:
            return out
        rules = self.catalog.pack.rules_by_id
        says = [r.say for p in self.catalog.products for r in p.qualified_results]

        async def go(v):
            r = rules[v.rule_id]
            cand = {"kind": "compliance", "rule": {"rule_id": r.rule_id, "title": r.title, "description": r.description,
                                                   "severity": r.severity,
                                                   "unacceptable_examples": r.unacceptable_examples[:3]},
                    "span": v.span, "claim_kind": getattr(v, "claim_kind", None), "group": getattr(v, "group", None)}
            if v.rule_id == qualifier.RULE_ID:
                cand["qualified_results"] = says
            return v, await self._one(on_air, cand, line, previous, session_id)

        rejected = set()
        for v, (res, index) in await asyncio.gather(*(go(v) for v in cands)):
            o = res.output if res.status == "ok" else None
            if o is None:
                v._unverified = True  # a timeout or error keeps the candidate, marked
                log.info("verifier %s: compliance kept unverified | rule=%s span=%r", res.status, v.rule_id, v.span)
            elif o.decision == "reject":
                _cdrop(v, f"verifier: {o.reason}")
                rejected.add(id(v))
            else:
                v._severity = o.severity or rules[v.rule_id].severity
                if o.evidence and o.evidence not in index:
                    v._unverified = True
                    log.info("verifier: unknown evidence id %s | rule=%s", o.evidence, v.rule_id)
        out.compliance.violations = [v for v in out.compliance.violations if id(v) not in rejected]
        return out

    async def check_facts(self, out: FactCheckOutput, line: str, previous: Sequence[str], on_air: str,
                          passages: Sequence[Passage], session_id: str | None = None) -> FactCheckOutput:
        cands = [c for c in out.claims if c.verdict == "contradicted"]
        if not cands:
            return out
        lex = self.catalog.lexicon

        async def go(c):
            pid = c.product_id if self.catalog.is_product(c.product_id) else on_air
            cand = {"kind": "fact", "field": c.field, "product_id": c.product_id, "span": c.span,
                    "stated": c.stated_value, "correction": c.correct_value, "quote": c.quote}
            return c, await self._one(pid, cand, line, previous, session_id)

        for c, (res, index) in await asyncio.gather(*(go(c) for c in cands)):
            o = res.output if res.status == "ok" else None
            right = _numbers(lex, c.correct_value)
            if (c.passage_id is not None and right
                    and not right <= _product_numbers(lex, self.catalog, c.product_id, passages)):
                _drop(c, "provenance: a number of the correction is in no passage of the product")
            elif o is None:
                c._unverified = True
                log.info("verifier %s: fact kept unverified | field=%s stated=%r", res.status, c.field, c.stated_value)
            elif o.decision == "reject":
                _drop(c, f"verifier: {o.reason}")
            elif o.evidence and o.evidence not in index:
                c._unverified = True
                log.info("verifier: unknown evidence id %s | field=%s", o.evidence, c.field)
        return out
