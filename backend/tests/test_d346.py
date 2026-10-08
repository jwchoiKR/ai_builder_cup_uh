"""D-346: after the fact checker, code keeps only provenance (the evidence exists, it is no claim-wording passage); the
number checks only log "would drop (log-only)". And the planner's question: a made-up product whose brochure file
and record both list a NOT APPROVED phrase; the host says it. Expected: a compliance alert and no fact alert citing
the record sentence or the file sentence."""
from __future__ import annotations

import json
import re

import pytest

from .judge_fakes import ScriptedBackend, close_env, violation

LINE = "This balm cures eczema overnight."
BROCHURE = b"Velmora Night Balm\nNOT APPROVED: Cures eczema.\nApply a thin layer at night."


class _Backend(ScriptedBackend):
    """The fact checker contradicts the line, citing the sentence that holds the banned phrase."""

    def __init__(self, cite: str):
        super().__init__()
        self.cite = cite

    async def generate(self, req, timeout_ms):
        if req.agent != "fact_checker":
            return await super().generate(req, timeout_ms)
        from app.providers.llm import RawReply

        m = re.search(r'\["(S\d+)",\s*"' + re.escape(self.cite), req.user_message)
        pid = re.search(r'"product_id":"([^"]+)"', req.user_message).group(1)
        claims = [] if m is None else [{
            "span": "cures eczema overnight", "stance": "HOST_ASSERTS", "product_id": pid, "field": "other",
            "stated_value": "cures eczema", "evidence": [m.group(1)], "source_value": "not approved: cures eczema",
            "relation": "contradicts", "correct_value": "Do not say it cures eczema."}]
        self.cited = m is not None
        return RawReply(json.dumps({"claims": claims}), model_version="scripted")


async def _show(tmp_path, cite: str):
    from app.models.session import Transcript  # noqa: F401
    from app.onboarding.files import store
    from app.onboarding.read import normalise
    from app.onboarding.record import ProductRecord
    from app.onboarding.release import save_release
    from app.pipelines.runtime import create_session

    from .helpers import make_ctx
    from .test_onboarding import EV, _record

    ev = [{"file": "brochure.txt", "locator": "line 2", "quote": "NOT APPROVED: Cures eczema."}]
    rec, _ = normalise(ProductRecord.model_validate(_record(
        brand="Velmora", product_name="Night Balm", category="Cosmetic",
        not_approved_claims=[{"text": "Cures eczema.", "evidence": ev}],
        approved_claims=[{"text": "Helps skin feel soft by morning.", "evidence": EV}])))
    store(tmp_path, "job1", "brochure.txt", BROCHURE)
    rid = save_release(tmp_path, rec, "job1")
    llm = _Backend(cite)
    llm.judge(LINE, violations=[violation("ASEAN-2D-DISEASE", "cures eczema")])
    ctx = make_ctx(backend=llm, ONBOARDING_DIR=str(tmp_path), FACT_MODE="docs", FACT_RELATION=True,
                   FACT_PROMPT="v5", JUDGE_ARM="single")
    s = await create_session(ctx, "", release_id=rid)
    rt = await ctx.runtimes.get(s.session_id)
    await rt.start()
    await ctx.scheduler.advance(5000)
    return rt, llm


async def _run(tmp_path, cite):
    from .judge_fakes import speak

    rt, llm = await _show(tmp_path, cite)
    try:
        await speak(rt, LINE)
        await rt.utterances.drain()
        kinds = sorted(a.kind for a in await rt.alerts() if a.status == "active")
        return kinds, llm.cited
    finally:
        await close_env(rt)


async def test_d346_the_record_s_not_approved_sentence_gives_no_fact_alert(tmp_path):
    kinds, cited = await _run(tmp_path, "Claims not approved: Cures eczema.")
    assert cited and kinds == ["compliance"]  # D-338: the claims section is no fact source


@pytest.mark.xfail(strict=True, reason="D-346 finding: a NOT APPROVED line in a release file ('Source file' section) "
                                       "is still a valid fact source; the fact alert stands next to the compliance one")
async def test_d346_the_brochure_file_s_not_approved_sentence_gives_no_fact_alert(tmp_path):
    kinds, cited = await _run(tmp_path, "NOT APPROVED: Cures eczema.")
    assert cited and kinds == ["compliance"]
