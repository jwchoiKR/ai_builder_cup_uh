"""D-296: the relation arm (FACT_RELATION). The fact checker names its evidence by SOURCE sentence id and states a
relation; code builds the quote. FACT_GUARDS=on runs today's post-validation on it, off keeps only the hard checks.
Made-up lines and passages across categories (skincare, a supplement, a children's product, a fragrance, a kettle)."""
from __future__ import annotations

import json
import re

import pytest

from app.agents.fact_checker import DROPS, from_relation, sentence_index
from app.models.agent_io import FactRelationOutput
from app.models.data import Passage

from .judge_fakes import CREAM, PRICE_PASSAGE, ScriptedBackend, close_env, speak


def _p(pid: str, text: str, product: str = CREAM, section: str = "Key facts") -> Passage:
    return Passage(passage_id=pid, product_id=product, doc="sheet", section=section, text=text, score=0.0)


def _rel(*claims) -> FactRelationOutput:
    return FactRelationOutput.model_validate({"claims": [
        {"span": c[0], "product_id": c[1], "field": c[2], "stated_value": c[3], "evidence": c[4], "relation": c[5],
         "correct_value": c[6]} for c in claims]})


def test_d296_sentences_are_numbered_once_and_keep_decimals():
    a = _p("A", "Volume: 4.5 mL. Made in Korea.\nDo not share the brush.")
    blocks, index = sentence_index([a, _p("B", "Price: S$36.00"), a])
    assert [s for b in blocks for s in b["sentences"]] == [
        ["S1", "Volume: 4.5 mL."], ["S2", "Made in Korea."], ["S3", "Do not share the brush."], ["S4", "Price: S$36.00"]]
    assert index["S4"][0].passage_id == "B" and len(blocks) == 2  # a repeated passage is numbered once


def test_d296_from_relation():
    _, index = sentence_index([_p(PRICE_PASSAGE, "Live broadcast price: S$36.00. Free delivery.")])
    out = _rel(("thirty-two dollars", CREAM, "price", "S$32", ["S1"], "contradicts", "S$36.00"),
               ("free delivery", CREAM, "price", "free delivery", ["S2"], "consistent", None),
               ("thirty dollars", CREAM, "price", "S$30", ["S9"], "contradicts", "S$36.00"),
               ("time sale price", CREAM, "promo", "S$30", ["promo"], "contradicts", "S$32.40"),
               ("the big one", CREAM, "price", "S$36", ["S1"], "uncertain", None))
    sink: list = []
    token = DROPS.set(sink)
    try:
        got = from_relation(out, index, {"promo"}).claims
    finally:
        DROPS.reset(token)
    assert [(c.verdict, c.passage_id, c.quote) for c in got] == [
        ("contradicted", PRICE_PASSAGE, "Live broadcast price: S$36.00."),  # the quote is built by code
        ("supported", PRICE_PASSAGE, "Free delivery."),
        ("contradicted", None, None),  # D-374: an id SOURCE does not have: applied as given, no quote
        ("contradicted", None, None),  # the active promo
        ("not_in_sources", PRICE_PASSAGE, "Live broadcast price: S$36.00.")]  # uncertain never alerts
    assert [d["reason"] for d in sink] == ["relation uncertain"]  # D-374: no drop, uncertain is only counted


class _RelationBackend(ScriptedBackend):
    """The fact checker answers in the relation shape, citing the sentence that holds the live price."""

    def __init__(self, relation: str = "contradicts") -> None:
        super().__init__()
        self.relation, self.requests = relation, []

    async def generate(self, req, timeout_ms):
        if req.agent != "fact_checker":
            return await super().generate(req, timeout_ms)
        from app.providers.llm import RawReply

        self.requests.append(req)
        m = re.search(r'\["(S\d+)",\s*"Live broadcast price', req.user_message)
        claims = [] if m is None or "thirty-two" not in req.mock_primary_text else [{
            "span": "thirty-two dollars", "product_id": CREAM, "field": "price", "stated_value": "S$32",
            "evidence": [m.group(1)], "relation": self.relation,
            "correct_value": "S$36.00" if self.relation == "contradicts" else None}]
        return RawReply(json.dumps({"claims": claims}), model_version="scripted")


@pytest.mark.parametrize("guards", ["on", "off"])
@pytest.mark.parametrize("relation, alerts", [("contradicts", 1), ("consistent", 0), ("uncertain", 0)])
async def test_d296_the_relation_arm_end_to_end(guards, relation, alerts):
    from .helpers import live_runtime, make_ctx

    llm = _RelationBackend(relation)
    rt = await live_runtime(make_ctx(backend=llm, FACT_RELATION=True, FACT_GUARDS=guards))
    try:
        await speak(rt, "It's only thirty-two dollars today.")
        await rt.utterances.drain()
        facts = [a for a in await rt.alerts() if a.kind == "fact"]
        assert len(facts) == alerts
        if alerts:
            assert facts[0].correct_value == "S$36.00" and "S$36.00" in (facts[0].quote or "")
        req = llm.requests[0]
        assert req.output_model is FactRelationOutput and "sentences" in req.user_message
        assert "`evidence`" in req.system_instruction
    finally:
        await close_env(rt)


def _validate_r(catalog, line, violations, fixes, prev=None):
    """`_validate` with the relation arm's compliance output (`claim_kind`, `group`), and a previous final."""
    import os

    from app.agents.utterance_judge import JudgeInput, build_judge_values, validate_compliance
    from app.config import get_settings
    from app.models.agent_io import ComplianceOutputR

    values = build_judge_values(catalog, JudgeInput(utterance=line, on_air=catalog.products[0].product_id))
    if prev is not None:
        values["last_two_final_transcripts_json"] = [prev]
    out = ComplianceOutputR.model_validate({"compliance": {"violations": violations},
                                            "correction": {"corrects_alert_ids": []}, "reason": "t"})
    old = os.environ.get("FACT_FIXES")
    os.environ["FACT_FIXES"] = ",".join(fixes)
    get_settings.cache_clear()
    try:
        return validate_compliance(out, catalog, values).compliance.violations
    finally:
        os.environ.pop("FACT_FIXES") if old is None else os.environ.__setitem__("FACT_FIXES", old)
        get_settings.cache_clear()


V, D = "ASEAN-2D-VULNERABLE", "ASEAN-2D-DISEASE"
ALL = ("CK", "Q6", "G7")


def _high(rule, span, kind=None, group=None):
    return {"span": span, "rule_id": rule, "severity": "HIGH", "is_negated": False, "is_quoted": False,
            "say_instead": "x", "claim_kind": kind, "group": group}


async def test_d297_the_compliance_judge_asks_for_claim_kind_only_in_the_arm():
    from app.agents.split_judges import ComplianceJudge
    from app.models.agent_io import ComplianceOutput, ComplianceOutputR

    from .helpers import live_runtime, make_ctx

    for on, model in ((False, ComplianceOutput), (True, ComplianceOutputR)):
        rt = await live_runtime(make_ctx(backend=ScriptedBackend(), FACT_RELATION=on))
        try:
            j = ComplianceJudge(rt.ctx.llm, rt.ctx.prompts, rt.catalog, rt.reflex)
            assert j.output_model is model and (("`claim_kind`" in j.system_instruction) is on)
        finally:
            await close_env(rt)


def test_d297_law_pack_rules_get_claim_kinds(pack):
    from app.onboarding.lawpack import to_rules

    from .test_q_fixes import _law_rule

    for category, kinds in (("vulnerable_groups", ["safety_promise", "disease_treatment"]),
                            ("disease", ["disease_treatment"]), ("safety", [])):
        _, rec = _law_rule("HS-X", category)
        r = to_rules("law_x_v1", rec, pack.lang_pack.categories)[0]
        assert r.claim_kinds == kinds and r.needs_group is (category == "vulnerable_groups")
