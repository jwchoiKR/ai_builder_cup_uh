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
from .test_q_fixes import _release_catalog


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


@pytest.mark.parametrize("category, line, rule, span, kind, group, kept", [
    # pairs (D-297): each failure class next to its true positive
    ("children", "Have your child swallow the toothpaste.", V, "child swallow the toothpaste", "usage_instruction",
     "child", False),
    ("children", "Safe for babies.", V, "Safe for babies", "safety_promise", "babies", True),
    ("lip balm", "Fine on chapped lips, no problem.", D, "Fine on chapped lips", "safety_promise", "chapped lips",
     False),
    ("skincare", "It cures eczema.", D, "cures eczema", "disease_treatment", None, True),
    ("hand gel", "Zero side effects with this gel.", V, "Zero side effects", "safety_promise", None, False),
    ("fragrance", "Safe for everyone, even sensitive noses.", V, "Safe for everyone", "safety_promise", "everyone", True),
    ("supplement", "Each gummy has 2 mg zinc, great for kids.", V, "2 mg zinc", "composition_fact", "kids", False),
    ("haircare", "Your dandruff will never come back.", D, "never come back", "permanence", None, False),
])
def test_d297_ck_the_claim_kind_must_fit_the_rule(catalog, category, line, rule, span, kind, group, kept):
    assert [x.rule_id for x in _validate_r(catalog, line, [_high(rule, span, kind, group)], ALL)] == (
        [rule] if kept else [])


@pytest.mark.parametrize("line, span, kept", [
    ("Kids can brush on their own, so easy.", "brush on their own", False),  # G7 words
    ("Safe for babies.", "Safe for babies", True),
])
def test_d297_ck_falls_back_to_the_word_lists_without_a_claim_kind(catalog, line, span, kept):
    assert [x.rule_id for x in _validate_r(catalog, line, [_high(V, span)], ALL)] == ([V] if kept else [])


def test_d297_compliance_guards_hold_with_the_fact_guards_off(catalog, monkeypatch):
    monkeypatch.setenv("FACT_GUARDS", "off")
    got = _validate_r(catalog, "Have your child swallow the toothpaste.",
                      [_high(V, "swallow", "usage_instruction", "child")], ALL)
    assert got == []


@pytest.mark.parametrize("prev, line, kept", [
    ("It costs", "SGD 22 for one 4 mL unit.", False),  # a split price line is no test result
    ("And the best part,", "it lasts 4 hours.", True),  # a real result said without its qualifier
])
def test_d297_pair_split_price_is_no_test_result(tmp_path, prev, line, kept):
    from app.logic.qualifier import RULE_ID

    from .test_g_fixes import _validate_after

    catalog = _release_catalog(tmp_path, "Lasts 4 hours", "tested by Fenmore Labs", "skincare")
    v = {"span": line, "rule_id": RULE_ID, "severity": "MEDIUM", "is_negated": False, "is_quoted": False,
         "say_instead": "x"}
    assert [x.rule_id for x in _validate_after(catalog, prev, line, [v], ("G4", "G5", "Q1E"))] == (
        [RULE_ID] if kept else [])


@pytest.mark.parametrize("line, stated, correct, quote, field, alert", [
    ("Someone asked if it's alcohol-free. No, it contains alcohol.", "alcohol-free", "Contains alcohol",
     "Contains alcohol (ethanol)", "ingredient", False),
    ("Someone asked if it's alcohol-free. Yes, it's alcohol-free.", "alcohol-free", "Contains alcohol",
     "Contains alcohol (ethanol)", "ingredient", True),
    ("A comment says the 50 mL is S$20; that mixes up sizes, it's S$24.", "S$20", "S$24.00",
     "Live broadcast price (50 mL): S$24.00", "price", False),
    ("The 50 mL is S$20.", "S$20", "S$24.00", "Live broadcast price (50 mL): S$24.00", "price", True),
    ("Have your child swallow the toothpaste.", "swallow the toothpaste", "Do not swallow",
     "Do not swallow. Spit out after brushing.", "caution", True),  # the usage error is a fact alert
])
def test_d297_pairs_on_the_fact_side(catalog, line, stated, correct, quote, field, alert):
    """FACT_GUARDS=off keeps the quote-then-reject guard (Q2, G1): the relation model still read these as
    contradictions."""
    from app.config import get_settings

    fixes = frozenset(x.strip() for x in get_settings().FACT_FIXES.split(","))
    passages = [_p("DL-CR-01#key-facts#x", quote)]
    _, index = sentence_index(passages)
    out = from_relation(_rel((line, CREAM, field, stated, ["S1"], "contradicts", correct)), index, set())
    got = hard_validate(out, passages, catalog, None, (), {CREAM}, line, fixes).claims[0].verdict
    assert (got == "contradicted") is alert


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
