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
from ..logic.verify import _flat
from ..models.agent_io import ComplianceOutput, FactCheckOutput, VerifyOutput, VerifyOutputC
from ..models.data import Passage
from ..providers.llm import AgentResult, LLMClient, LLMRequest
from ..providers.prompts import PromptTemplate
from .fact_checker import _drop, _numbers, _product_numbers, sentence_index
from .utterance_judge import _cdrop

log = logging.getLogger(__name__)

WINDOW = 2  # D-301: sentences on each side of the cited ones


class Verifier:
    name = "verifier"

    def __init__(self, llm: LLMClient, prompt: PromptTemplate, catalog: Catalog,
                 files: dict[str, tuple[tuple, tuple]] | None = None) -> None:
        self.llm, self.prompt, self.catalog = llm, prompt, catalog
        self.files = files or {}  # product id -> (model parts, file passages), as the fact checker has them
        self._sources: dict[str, tuple[list[dict], dict]] = {}
        self.failures: dict[str, int] = {}  # D-306: verifier calls with no answer, by failure type
        # D-301: "all" (the product's documents, cached) or "window" (the cited sentences and their neighbours)
        self.window = getattr(llm.settings, "VERIFY_EVIDENCE", "all") == "window"
        # D-303: speech-to-text awareness, and the "check" decision for one misheard number
        from . import arms

        s, addenda = llm.settings, arms._addenda(str(llm.prompts_path))
        self.number_check = getattr(s, "NUMBER_CHECK", False)
        extra = [addenda.get(("STT", self.name)) if getattr(s, "STT_AWARE", False) else None,
                 addenda.get(("CHECK", self.name)) if self.number_check else None]
        self.system_instruction = "\n\n".join([prompt.system_instruction, *(x for x in extra if x)])

    def source(self, pid: str) -> tuple[list[dict], dict]:
        """The product's documents, numbered once per product (the cached prefix of every call)."""
        if pid not in self._sources:
            passages = [p for p in self.catalog.pack.passages if p.product_id == pid]
            self._sources[pid] = sentence_index([*passages, *self.files.get(pid, ((), ()))[1]])
        return self._sources[pid]

    def evidence(self, pid: str, quote: str | None) -> list[dict]:
        """D-301 window mode: the sentences the flagger's quote covers, with WINDOW neighbours each side (same ids as
        the whole documents); none for a compliance candidate."""
        blocks, index = self.source(pid)
        if not self.window:
            return blocks
        ids, q = list(index), _flat(quote or "")
        hits = [i for i, sid in enumerate(ids) if q and (s := _flat(index[sid][1])) and (s in q or q in s)]
        if q and not hits:
            # D-309: the flagger's quote matches no sentence, so the verifier gets no documents for this fact
            log.info("verifier window: no sentence matches the quote %r", (quote or "")[:120])
            from .fact_checker import DROPS

            if (sink := DROPS.get()) is not None:
                sink.append({"reason": "verifier window: no sentence matches the quote", "field": None,
                             "stated": None, "correct": None, "passage_id": None, "quote": quote})
        keep = {ids[j] for i in hits for j in range(max(0, i - WINDOW), min(len(ids), i + WINDOW + 1))}
        return [b | {"sentences": [s for s in b["sentences"] if s[0] in keep]} for b in blocks
                if any(s[0] in keep for s in b["sentences"])]

    def _request(self, pid: str, blocks: list[dict], cand: dict, line: str, previous: Sequence[str],
                 session_id: str | None) -> LLMRequest:
        user, prefix = self.prompt.render_cached({
            "passages_json": blocks, "candidate_json": cand,
            "last_two_final_transcripts_json": list(previous), "utterance_text": line}, {"passages_json"})
        return LLMRequest(
            agent=self.name, model=self.llm.verify.model, thinking_level=self.llm.verify.thinking_level,
            prompt_version=self.prompt.version, system_instruction=self.system_instruction, user_message=user,
            output_model=VerifyOutputC if self.number_check else VerifyOutput,
            deadline_ms=self.llm.settings.VERIFY_TIMEOUT_MS, session_id=session_id,
            cache_prefix="" if self.window else prefix,
            cache_parts=() if self.window else self.files.get(pid, ((), ()))[0],
            cache_ttl_sec=sum(i.planned_duration_sec for i in self.catalog.runsheet.items),
            mock_primary_text=f"{line}|{cand.get('span', '')}",
            mock_fallback=lambda _: {"evidence": None, "reason": "mock: kept", "decision": "keep", "severity": None},
            preview=f"{line} | {cand.get('kind')}: {cand.get('span', '')}",
        )

    async def warm(self, pid: str, session_id: str | None) -> None:
        """D-301: the product's documents cache, made at session start, so the first candidates are not uncached."""
        if not self.window:
            await self.llm.warm_cache(self._request(pid, self.source(pid)[0], {}, "", [], session_id))

    async def _one(self, pid: str, cand: dict, quote: str | None, line: str, previous: Sequence[str],
                   session_id: str | None) -> tuple[AgentResult, dict]:
        res = await self.llm.call(self._request(pid, self.evidence(pid, quote), cand, line, previous, session_id))
        if res.status != "ok":
            kind = res.meta.get("failure") or "other_error"
            self.failures[kind] = self.failures.get(kind, 0) + 1
        return res, self.source(pid)[1]

    async def check_compliance(self, out: ComplianceOutput, line: str, previous: Sequence[str], on_air: str,
                               session_id: str | None = None) -> ComplianceOutput:
        cands = [v for v in out.compliance.violations if not v.is_negated and not v.is_quoted]
        if not cands:
            return out
        rules = self.catalog.pack.rules_by_id
        says = [r.say for p in self.catalog.products for r in p.qualified_results]
        product = self.catalog.get_product(on_air) if self.catalog.is_product(on_air) else None

        async def go(v):
            r = rules[v.rule_id]
            cand = {"kind": "compliance", "rule": {"rule_id": r.rule_id, "title": r.title, "description": r.description,
                                                   "severity": r.severity,
                                                   "unacceptable_examples": r.unacceptable_examples[:3]},
                    "span": v.span, "claim_kind": getattr(v, "claim_kind", None), "group": getattr(v, "group", None)}
            if v.rule_id == qualifier.RULE_ID:
                cand["qualified_results"] = says
            if self.window and product is not None:
                cand["cautions"] = product.cautions  # D-301: with no documents, the cautions a line may reverse
            return v, await self._one(on_air, cand, None, line, previous, session_id)

        rejected = set()
        for v, (res, index) in await asyncio.gather(*(go(v) for v in cands)):
            o = res.output if res.status == "ok" else None
            if o is None:
                v._unverified = True  # a timeout or error keeps the candidate, marked
                v._unverified_reason = res.meta.get("failure") or "other_error"  # D-306
                log.info("verifier %s: compliance kept unverified | rule=%s span=%r", res.status, v.rule_id, v.span)
            elif o.decision == "reject":
                _cdrop(v, f"verifier: {o.reason}")
                rejected.add(id(v))
            elif o.decision == "check":  # D-303: only for facts; a compliance "check" is kept as it is
                v._severity = rules[v.rule_id].severity
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
            return c, await self._one(pid, cand, c.quote, line, previous, session_id)

        for c, (res, index) in await asyncio.gather(*(go(c) for c in cands)):
            o = res.output if res.status == "ok" else None
            right = _numbers(lex, c.correct_value)
            if (c.passage_id is not None and right
                    and not right <= _product_numbers(lex, self.catalog, c.product_id, passages)):
                _drop(c, "provenance: a number of the correction is in no passage of the product")
            elif o is None:
                c._unverified = True
                c._unverified_reason = res.meta.get("failure") or "other_error"  # D-306
                log.info("verifier %s: fact kept unverified | field=%s stated=%r", res.status, c.field, c.stated_value)
            elif o.decision == "reject":
                _drop(c, f"verifier: {o.reason}")
            elif o.decision == "check":
                c._check = True  # D-303: "check what was said", the heard words shown
                log.info("verifier: check what was said | field=%s stated=%r", c.field, c.stated_value)
            elif o.evidence and o.evidence not in index:
                c._unverified = True
                log.info("verifier: unknown evidence id %s | field=%s", o.evidence, c.field)
        return out
