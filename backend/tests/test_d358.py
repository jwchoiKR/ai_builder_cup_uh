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
    """A made-up food supplement whose regulation file is the Kelmar code (rebuilt onboarding: product + regulation)."""
    from app.pipelines.runtime import create_session

    from .helpers import make_ctx, product_show

    ctx = make_ctx(backend=llm, CORRECTION_CHECK="judge")
    key = product_show(ctx, {"brand": "Kelmar", "product_name": "Joint Ease", "currency": "SGD", "variants": [{"label": "", "list_price": "30.00", "live_price": "25.00"}],
                             "points": [{"text": "Supports normal joint comfort.", "required": True}]},
                       [("kelmar_code.pdf", CODE)])
    s = await create_session(ctx, "", release_id=key)
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


def test_d405_no_own_rule_for_vulnerable_groups_in_the_prompt():
    """D-405 (user, audit 13a): the judge enforces only the regulation documents; the prompt adds no rule of its own."""
    from pathlib import Path

    text = (Path(__file__).resolve().parents[2] / "prompts" / "compliance_judge.md").read_text(encoding="utf-8")
    assert "PROMISE to a vulnerable group" not in text
    assert 'section 4.2: "No claim may promise safety to infants' in text  # Example A cites its document's text


async def test_d433_the_alert_carries_the_cited_document_s_readable_name_and_section(tmp_path):
    """D-433: the host's red box shows the document and the section the model cited, never the rule-id slug. A law
    pack's original has no title of its own, so its file name without the extension; a market source has a title."""
    from app.agents.originals import cited_title

    llm = _Backend()
    llm.outputs[("compliance_judge", CLAIM)] = _verdict("kelmar_code.pdf#2.1", "must not be presented")
    rt = await _show(tmp_path, llm)
    try:
        await speak(rt, CLAIM)
        [a] = [a for a in await rt.alerts() if a.kind == "compliance"]
        assert a.rule_id == "kelmar-code#2-1" and a.cited_title == "kelmar_code 2.1"
    finally:
        await close_env(rt)
    market = Original("asean_appendix_iii.pdf", "ASEAN Cosmetic Claims Guideline", "ASEAN_APPENDIX_III", b"",
                      "application/pdf", "")
    assert cited_title(market, "asean_appendix_iii.pdf", "2.d") == "ASEAN Cosmetic Claims Guideline 2.d"
    assert cited_title(None, "other_code.pdf", "3") == "other_code 3"  # a document the judge was not given
    assert cited_title(None, "other_code.pdf", "") == "other_code"
