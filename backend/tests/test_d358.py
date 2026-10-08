"""D-358: the live compliance judge reads the regulation ORIGINALS (no rule JSON): the files of the show's law packs
in its cached prefix, one instruction prompt, cited verdicts whose quote must be in that original (provenance), the
alert's rule id from the citation, the severity the model chose, and corrections by handle. A fictional law pack
("Kelmar supplement code", a text file) on a made-up food-supplement release; the judge's answers are scripted."""
from __future__ import annotations

import logging

import pytest

from app.agents.originals import Original, citation_rule_id, originals_for
from app.agents.utterance_judge import JudgeInput

from .judge_fakes import ScriptedBackend, close_env, speak

pytestmark = pytest.mark.originals

CODE = (b"Kelmar Supplement Code\n"
        b"2.1 A supplement must not be presented as treating, curing or preventing disease.\n"
        b"4.2 No claim may promise safety to infants or other vulnerable consumers.\n")
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
    from app.onboarding.lawpack import LawPackRecord, normalise_pack, save_lawpack
    from app.onboarding.read import normalise
    from app.onboarding.record import ProductRecord
    from app.onboarding.release import save_release
    from app.pipelines.runtime import create_session

    from .helpers import make_ctx
    from .test_onboarding import EV, _record

    law, _ = normalise_pack(LawPackRecord.model_validate({
        "name": "Kelmar supplement code", "regulator": "Kelmar authority", "covers": ["food_supplement"],
        "language": "en", "rules": [
            {"rule_id": "K-DISEASE", "title": "No disease claims", "description": "No cure claims.",
             "severity": "HIGH", "rule_category": "Disease", "unacceptable_examples": [], "say_instead_hint": "",
             "evidence": [{"file": "kelmar_code.txt", "locator": "2.1", "quote": "must not be presented"}]}]}))
    save_lawpack(tmp_path, "SG", law, "jlaw")
    store(tmp_path, "jlaw", "kelmar_code.txt", CODE)
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
        assert '<data name="REGULATION_DOCUMENTS">' in req.user_message and "kelmar_code.txt" in req.user_message
        assert (b"FILE kelmar_code.txt", "text/plain") in req.cache_parts
        assert any(CODE in data for data, _ in req.cache_parts)
        schema = req.output_model.model_json_schema()
        assert list(schema["properties"])[0] == "alert_checks"
        assert "citation" in schema["$defs"]["ViolationO"]["properties"]
        assert "rule_id" not in schema["$defs"]["ViolationO"]["properties"]
    finally:
        await close_env(rt)


async def test_d358_a_cited_verdict_becomes_an_alert_named_by_its_citation(tmp_path):
    llm = _Backend()
    llm.outputs[("compliance_judge", CLAIM)] = _verdict(
        "kelmar_code.txt#2.1", "must not be presented as treating, curing or preventing disease")
    rt = await _show(tmp_path, llm)
    try:
        await speak(rt, CLAIM)
        [a] = [a for a in await rt.alerts() if a.kind == "compliance"]
        assert a.rule_id == citation_rule_id("kelmar_code.txt", "2.1") == "kelmar-code#2-1"
        assert a.severity == "HIGH" and a.status == "active"
        assert a.say_instead == "It supports normal joint comfort."  # D-361: the model's own, no code rewording
    finally:
        await close_env(rt)


@pytest.mark.parametrize("citation, quote, why", [
    ("kelmar_code.txt#2.1", "a supplement may never be sold online", "the quote is not in kelmar_code.txt"),
    ("other_code.pdf#3", "must not be presented", "names no regulation document given to the judge"),
])
async def test_d358_a_verdict_without_provenance_is_dropped_and_logged(tmp_path, caplog, citation, quote, why):
    llm = _Backend()
    llm.outputs[("compliance_judge", CLAIM)] = _verdict(citation, quote)
    rt = await _show(tmp_path, llm)
    try:
        with caplog.at_level(logging.INFO):
            await speak(rt, CLAIM)
        assert not [a for a in await rt.alerts() if a.kind == "compliance"]
        assert why in caplog.text and "compliance violation dropped by code: provenance" in caplog.text
    finally:
        await close_env(rt)


async def test_d358_the_severity_is_the_model_s_and_a_correction_goes_by_handle(tmp_path):
    llm = _Backend()
    llm.outputs[("compliance_judge", CLAIM)] = _verdict(
        "kelmar_code.txt#2.1", "must not be presented as treating", severity="MEDIUM")
    llm.outputs[("compliance_judge", SORRY)] = {
        "alert_checks": [{"handle": "A1", "fixed_by_this_line": True}], "compliance": {"violations": []},
        "reason": "scripted"}
    rt = await _show(tmp_path, llm)
    try:
        await speak(rt, CLAIM)
        [a] = [a for a in await rt.alerts() if a.kind == "compliance"]
        assert a.severity == "MEDIUM"  # the model's choice; there is no pack severity
        await speak(rt, SORRY)
        await rt.utterances.drain()
        [a] = [a for a in await rt.alerts() if a.kind == "compliance"]
        assert a.status == "corrected"
    finally:
        await close_env(rt)


def test_d358_a_test_qualifier_verdict_is_checked_against_the_recorded_results(catalog):
    from app.agents.utterance_judge import validate_original
    from app.models.agent_io import ComplianceOutputO

    product = next(p for p in catalog.products if p.qualified_results)
    result = product.qualified_results[0]

    def run(rid, quote):
        out = ComplianceOutputO.model_validate({"compliance": {"violations": [{
            "citation": "TEST-QUALIFIER", "quote": quote, "span": "s", "severity": "MEDIUM", "is_negated": False,
            "is_quoted": False, "say_instead": "x", "qualified_result_id": rid}]},
            "correction": {"corrects_alert_ids": []}, "reason": "r"})
        values = {"current_product_json": {"product_id": product.product_id}, "active_alerts_json": []}
        return validate_original(out, catalog, values, ()).compliance.violations

    [v] = run(result.result_id, "anything")
    assert (v.rule_id, v.say_instead) == ("TEST-QUALIFIER", result.say)
    assert run(None, result.say) == []  # D-361: named by id only, no quote matching
    assert run("no-such-result", "anything") == []


async def test_d358_a_rule_source_with_no_original_is_reported(caplog):
    """The shipped demo's product-sheet rules have no original file: it is logged and marked on the judge's calls;
    the judge still reads the originals that exist (the SG cosmetics guideline)."""
    from .helpers import live_runtime, make_ctx

    llm = _Backend()
    ctx = make_ctx(backend=llm)
    rt = await live_runtime(ctx)
    try:
        with caplog.at_level(logging.WARNING):
            found, missing = originals_for(rt.catalog, ctx.settings.onboarding_path, rt.catalog.order)
        assert [d.name for d in found] == ["asean_cosmetic_claims_guideline_appendix_iii_2007.pdf"]
        assert missing == ("PRODUCT_SHEET",) and "compliance originals missing" in caplog.text
        res = await rt.utterances.compliance.run(
            JudgeInput(utterance="It feels light.", on_air=rt.catalog.order[0], session_id=rt.sid), deadline_ms=2000)
        assert res.meta["originals_missing"] == ["PRODUCT_SHEET"]
        assert isinstance(found[0], Original) and found[0].mime == "application/pdf"
    finally:
        await close_env(rt)
