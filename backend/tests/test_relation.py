"""D-296: the relation arm (FACT_RELATION). The fact checker names its evidence by SOURCE sentence id and states a
relation; code builds the quote. FACT_GUARDS=on runs today's post-validation on it, off keeps only the hard checks.
Made-up lines and passages across categories (skincare, a supplement, a children's product, a fragrance, a kettle)."""
from __future__ import annotations

import json
import re

import pytest

from app.agents.fact_checker import DROPS, from_relation, hard_validate, post_validate, sentence_index
from app.models.agent_io import FactRelationOutput
from app.models.data import Passage

from .judge_fakes import AMPOULE, CREAM, PRICE_PASSAGE, ScriptedBackend, close_env, speak
from .test_g_fixes import FACT


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
        ("not_in_sources", None, None),  # an id SOURCE does not have: no alert
        ("contradicted", None, None),  # the active promo
        ("not_in_sources", PRICE_PASSAGE, "Live broadcast price: S$36.00.")]  # uncertain never alerts
    assert [d["reason"] for d in sink] == ["relation: no valid evidence id (S9)", "relation uncertain"]


@pytest.mark.parametrize("fix, category, line, stated, correct, quote, field, false_alert", FACT,
                         ids=[f"{c[0]}-{c[1]}-{i}" for i, c in enumerate(FACT)])
def test_d296_the_guard_set_in_both_guard_modes(catalog, fix, category, line, stated, correct, quote, field,
                                                false_alert):
    """The relation arm is judged by the model; these check the code around it. A model that reads a false line as
    consistent gives no alert in either mode. A model that still says contradicts: guards on drop the false lines
    as today's fixes do, guards off keep it (the model owns the verdict); a true line alerts in both modes."""
    passages = [_p("DL-CR-01#key-facts#x", quote)]
    _, index = sentence_index(passages)
    for relation in ("consistent", "contradicts"):
        out = from_relation(_rel((line, CREAM, field, stated, ["S1"], relation, correct)), index, set())
        on = post_validate(out, passages, catalog, None, line, fixes=frozenset({fix})).claims[0].verdict
        off = hard_validate(out, passages, catalog, None, (), {CREAM}).claims[0].verdict
        if relation == "consistent":
            assert (on, off) == ("supported", "supported")
        else:
            assert on == ("not_in_sources" if false_alert else "contradicted") and off == "contradicted"


def test_d296_hard_checks(catalog):
    promo = next(p for p in catalog.pack.promos.promos if p.promo_id == "promo_time_sale_10")
    cream = _p(PRICE_PASSAGE, "Live broadcast price: S$36.00")
    ocr = _p("DL-CR-01#key-facts#ocr", "Live broadcast price: S$ 3 6.00")  # a table cell OCR spaced
    other = _p("DL-AM-01#key-facts#price", "Live broadcast price: S$44.00", AMPOULE)
    claims_passage = _p("DL-CR-01#claims", "Helps keep skin hydrated for 24 hours.", section="Approved on-air claims")
    caution = _p("DL-CR-01#cautions", "Stop use if irritation occurs.")
    passages = [cream, ocr, other, claims_passage, caution]
    cases = [  # (category, claim, products the line is about, kept)
        ("skincare", ("thirty-two dollars", CREAM, "price", "S$32", PRICE_PASSAGE, "S$36.00"), {CREAM}, True),
        ("skincare: OCR quote, record value (R1)", ("thirty-two", CREAM, "price", "S$32", ocr.passage_id, "S$36.00"),
         {CREAM}, True),
        ("kettle: a number in neither", ("thirty-two", CREAM, "price", "S$32", PRICE_PASSAGE, "S$41.00"), {CREAM},
         False),
        ("fragrance: another product's sentence", ("thirty-two", CREAM, "price", "S$32", other.passage_id, "S$44.00"),
         {CREAM}, False),
        ("supplement: a product the line is not about", ("forty", AMPOULE, "price", "S$40", other.passage_id,
                                                         "S$44.00"), {CREAM}, False),
        ("children: the approved-claims passage", ("all day", CREAM, "test_result", "all day",
                                                   claims_passage.passage_id, "24 hours"), {CREAM}, False),
        ("skincare: a caution without a number", ("keep using it", CREAM, "caution", "keep using it",
                                                  caution.passage_id, "Stop use if irritation occurs"), {CREAM}, True),
        ("promo: the active promo's price", ("thirty dollars", CREAM, "promo", "S$30", None,
                                             catalog.price_display(CREAM, promo)), {CREAM}, True),
        ("promo: not the promo's price", ("thirty dollars", CREAM, "promo", "S$30", None, "S$29.00"), {CREAM}, False),
    ]
    by_id = {p.passage_id: p for p in passages}
    for name, (span, pid, field, stated, passage_id, correct), products, kept in cases:
        raw = {"claims": [{"span": span, "product_id": pid, "field": field, "stated_value": stated,
                           "verdict": "contradicted", "correct_value": correct, "passage_id": passage_id,
                           "quote": by_id[passage_id].text if passage_id else None}], "reason": "relation"}
        from app.models.agent_io import FactCheckOutput

        got = hard_validate(FactCheckOutput.model_validate(raw), passages, catalog, promo, (), products)
        assert (got.claims[0].verdict == "contradicted") is kept, name


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


def _validate_r(catalog, line, violations, fixes):
    """`_validate` with the relation arm's compliance output (`claim_made`)."""
    import os

    from app.agents.utterance_judge import JudgeInput, build_judge_values, validate_compliance
    from app.config import get_settings
    from app.models.agent_io import ComplianceOutputR

    values = build_judge_values(catalog, JudgeInput(utterance=line, on_air=catalog.products[0].product_id))
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


V = "ASEAN-2D-VULNERABLE"


@pytest.mark.parametrize("category, line, span, claim, fixes, kept", [
    ("skincare", "My kids love this gentle wash.", "gentle wash", "the wash is gentle", ("Q6",), False),
    ("skincare", "My kids love this gentle wash.", "gentle wash", None, ("Q6",), True),  # no claim: the raw line
    ("children", "Safe for babies and so soft.", "Safe for babies", "safe for babies", ("Q6",), True),
    ("children", "Kids can brush on their own, so easy.", "brush on their own", "kids can brush on their own",
     ("Q6", "G7"), False),
    ("supplement", "Seniors and kids, zero side effects!", "zero side effects", "no side effects for seniors and kids",
     ("Q6", "G7"), True),
])
def test_d296_rule_fit_reads_claim_made(catalog, category, line, span, claim, fixes, kept):
    v = {"span": span, "rule_id": V, "severity": "HIGH", "is_negated": False, "is_quoted": False, "say_instead": "x",
         "claim_made": claim}
    assert [x.rule_id for x in _validate_r(catalog, line, [v], fixes)] == ([V] if kept else [])


async def test_d296_the_compliance_judge_asks_for_claim_made_only_in_the_arm():
    from app.agents.split_judges import ComplianceJudge
    from app.models.agent_io import ComplianceOutput, ComplianceOutputR

    from .helpers import live_runtime, make_ctx

    for on, model in ((False, ComplianceOutput), (True, ComplianceOutputR)):
        rt = await live_runtime(make_ctx(backend=ScriptedBackend(), FACT_RELATION=on))
        try:
            j = ComplianceJudge(rt.ctx.llm, rt.ctx.prompts, rt.catalog, rt.reflex)
            assert j.output_model is model and (("`claim_made`" in j.system_instruction) is on)
        finally:
            await close_env(rt)
