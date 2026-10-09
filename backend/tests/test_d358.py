"""D-358: the live compliance judge reads the regulation ORIGINALS (no rule JSON): the files of the show's law packs
in its cached prefix, one instruction prompt, cited verdicts whose quote must be in that original (provenance), the
alert's rule id from the citation, the severity the model chose, and corrections by handle. A fictional law pack
("Kelmar supplement code", a PDF) on a made-up food-supplement release; the judge's answers are scripted."""
from __future__ import annotations

import logging

import pytest

from app.agents.originals import Original, citation_rule_id, originals_for
from app.agents.utterance_judge import JudgeInput

from .helpers import text_pdf
from .judge_fakes import ScriptedBackend, close_env, speak

pytestmark = pytest.mark.originals

CODE = text_pdf("Kelmar Supplement Code\n"
                "2.1 A supplement must not be presented as treating, curing or preventing disease.\n"
                "4.2 No claim may promise safety to infants or other vulnerable consumers.\n")
CLAIM = "Honestly, this cures arthritis in a week."
SORRY = "Sorry, scratch that, it supports normal joint comfort."


def _verdict(citation: str, quote: str, severity: str = "HIGH", span: str = "cures arthritis") -> dict:
    return {"alert_checks": [], "compliance": {"violations": [{
        "citation": citation, "quote": quote, "span": span, "severity": severity, "is_negated": False,
        "is_quoted": False, "say_instead": "It supports normal joint comfort.", "qualified_result_id": None}]},
        "reason": "scripted"}


class _Backend(ScriptedBackend):
    def __init__(self):
        super().__init__()
        self.requests = []

    async def generate(self, req, timeout_ms):
        self.requests.append(req)
        return await super().generate(req, timeout_ms)


async def _show(tmp_path, llm):
    from app.onboarding.files import store
    from app.onboarding.lawpack import LawPackRecord, save_lawpack
    from app.onboarding.read import normalise
    from app.onboarding.record import ProductRecord
    from app.onboarding.release import save_release
    from app.pipelines.runtime import create_session

    from .helpers import make_ctx
    from .test_onboarding import EV, _record

    save_lawpack(tmp_path, "SG", LawPackRecord(covers=["food_supplement"]), "jlaw")  # D-427: the PDF only
    store(tmp_path, "jlaw", "kelmar_code.pdf", CODE)
    rec, _ = normalise(ProductRecord.model_validate(_record(category="food_supplement", approved_claims=[
        {"text": "Supports normal joint comfort.", "evidence": EV}])))
    rid = save_release(tmp_path, rec, "j")
    ctx = make_ctx(backend=llm, ONBOARDING_DIR=str(tmp_path), CORRECTION_CHECK="judge")
    s = await create_session(ctx, "", release_id=rid)
    rt = await ctx.runtimes.get(s.session_id)
    await rt.start()
    await ctx.scheduler.advance(5000)
    return rt


async def test_d358_the_judge_gets_the_originals_and_no_rule_json(tmp_path):
    llm = _Backend()
    rt = await _show(tmp_path, llm)
    try:
        await speak(rt, "This tub has sixty capsules.")
        req = [r for r in llm.requests if r.agent == "compliance_judge"][-1]
        assert '<data name="RULES">' not in req.user_message
        assert '<data name="REGULATION_DOCUMENTS">' in req.user_message and "kelmar_code.pdf" in req.user_message
        assert (CODE, "application/pdf") in req.cache_parts
        schema = req.output_model.model_json_schema()
        assert list(schema["properties"])[0] == "alert_checks"
        assert "citation" in schema["$defs"]["ViolationO"]["properties"]
        assert "rule_id" not in schema["$defs"]["ViolationO"]["properties"]
    finally:
        await close_env(rt)


async def test_d358_a_cited_verdict_becomes_an_alert_named_by_its_citation(tmp_path):
    llm = _Backend()
    llm.outputs[("compliance_judge", CLAIM)] = _verdict(
        "kelmar_code.pdf#2.1", "must not be presented as treating, curing or preventing disease")
    rt = await _show(tmp_path, llm)
    try:
        await speak(rt, CLAIM)
        [a] = [a for a in await rt.alerts() if a.kind == "compliance"]
        assert a.rule_id == citation_rule_id("kelmar_code.pdf", "2.1") == "kelmar-code#2-1"
        assert a.severity == "HIGH" and a.status == "active"
        assert a.say_instead == "It supports normal joint comfort."  # D-361: the model's own, no code rewording
    finally:
        await close_env(rt)


@pytest.mark.parametrize("citation, quote, rule_id, log_says", [
    # D-374 (user, 10/9; the 00008 wrinkle line): a paraphrased summary of a real section keeps its HIGH
    ("kelmar_code.pdf#Section 2.1", "Supplements cannot claim to cure illness.", "kelmar-code#section-2-1", None),
    # a document the judge was not given: applied as given, logged
    ("other_code.pdf#3", "must not be presented", "other-code#3", "a document the judge was not given"),
])
async def test_d374_a_cited_verdict_is_applied_as_given(tmp_path, caplog, citation, quote, rule_id, log_says):
    llm = _Backend()
    llm.outputs[("compliance_judge", CLAIM)] = _verdict(citation, quote)
    rt = await _show(tmp_path, llm)
    try:
        with caplog.at_level(logging.INFO):
            await speak(rt, CLAIM)
        [a] = [a for a in await rt.alerts() if a.kind == "compliance"]
        assert (a.severity, a.status, a.rule_id) == ("HIGH", "active", rule_id)
        assert (a.citation, a.quote) == (citation, quote)  # shown as the model's citation and summary
        assert "dropped by code" not in caplog.text
        assert log_says is None or log_says in caplog.text
    finally:
        await close_env(rt)


async def test_d400_a_document_citation_is_red_and_a_correction_goes_by_handle(tmp_path):
    llm = _Backend()
    llm.outputs[("compliance_judge", CLAIM)] = _verdict(
        "kelmar_code.pdf#2.1", "must not be presented as treating", severity="MEDIUM")
    llm.outputs[("compliance_judge", SORRY)] = {
        "alert_checks": [{"handle": "A1", "fixed_by_this_line": True}], "compliance": {"violations": []},
        "reason": "scripted"}
    rt = await _show(tmp_path, llm)
    try:
        await speak(rt, CLAIM)
        [a] = [a for a in await rt.alerts() if a.kind == "compliance"]
        assert a.severity == "HIGH"  # D-400: a regulation document is red, whatever the model sent
        await speak(rt, SORRY)
        await rt.utterances.drain()
        [a] = [a for a in await rt.alerts() if a.kind == "compliance"]
        assert a.status == "corrected"
    finally:
        await close_env(rt)


async def test_d358_a_rule_source_with_no_original_is_reported(caplog):
    """The shipped demo's product-sheet rules have no original file: it is logged and marked on the judge's calls;
    the judge still reads the originals that exist (the SG cosmetics guideline)."""
    from .helpers import live_runtime, make_ctx

    llm = _Backend()
    ctx = make_ctx(backend=llm)
    rt = await live_runtime(ctx)
    try:
        found, missing = originals_for(rt.catalog, ctx.settings.onboarding_path, rt.catalog.order)
        assert [d.name for d in found] == ["asean_cosmetic_claims_guideline_appendix_iii_2007.pdf"]
        rt.utterances.compliance._docs = None
        with caplog.at_level(logging.WARNING):  # D-363: logged once, when the show loads its originals
            rt.utterances.compliance.regulation()
        assert missing == ("PRODUCT_SHEET",) and "compliance originals missing for this show" in caplog.text
        res = await rt.utterances.compliance.run(
            JudgeInput(utterance="It feels light.", on_air=rt.catalog.order[0], session_id=rt.sid), deadline_ms=2000)
        assert res.meta["originals_missing"] == ["PRODUCT_SHEET"]
        assert isinstance(found[0], Original) and found[0].mime == "application/pdf"
    finally:
        await close_env(rt)


def test_d400_the_model_is_not_asked_for_a_severity_and_a_document_citation_is_red(catalog):
    """D-427: TEST-QUALIFIER (the only orange citation) is gone; its name is now cited like any document."""
    from app.agents.utterance_judge import validate_original
    from app.models.agent_io import ComplianceOutputO

    props = ComplianceOutputO.model_json_schema()["$defs"]["ViolationO"]["properties"]
    assert "severity" not in props and "qualified_result_id" not in props
    out = ComplianceOutputO.model_validate({"compliance": {"violations": [
        {"citation": "TEST-QUALIFIER", "quote": "q", "span": "s", "is_negated": False, "is_quoted": False,
         "say_instead": "x"},
        {"citation": "guideline.pdf#3", "quote": "q", "span": "t", "is_negated": False, "is_quoted": False,
         "say_instead": "y"}]}, "correction": {"corrects_alert_ids": []}, "reason": "r"})
    values = {"current_product_json": {"product_id": catalog.order[0]}, "active_alerts_json": []}
    got = validate_original(out, catalog, values, ()).compliance.violations
    assert [(v.severity, v.rule_id) for v in got] == [("HIGH", "test-qualifier#document"), ("HIGH", "guideline#3")]


def test_d405_no_own_rule_for_vulnerable_groups_in_the_prompt():
    """D-405 (user, audit 13a): the judge enforces only the regulation documents; the prompt adds no rule of its own."""
    from pathlib import Path

    text = (Path(__file__).resolve().parents[2] / "prompts" / "compliance_judge.md").read_text(encoding="utf-8")
    assert "PROMISE to a vulnerable group" not in text
    assert 'section 4.2: "No claim may promise safety to infants' in text  # Example A cites its document's text
