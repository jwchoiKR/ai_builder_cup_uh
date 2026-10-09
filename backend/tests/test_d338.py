"""D-338 (review H3/H4) dropped a fact contradiction whose evidence is the approved-claims section. D-374 (user, 10/9):
no code drop of a verdict: the fact checker's contradiction stands next to the compliance alert."""
from __future__ import annotations

import pytest

import json
import re

from .judge_fakes import CREAM, ScriptedBackend, close_env, speak, violation

LINE = "This cream treats eczema."


class _Backend(ScriptedBackend):
    async def generate(self, req, timeout_ms):
        if req.agent != "fact_checker":
            return await super().generate(req, timeout_ms)
        from app.providers.llm import RawReply

        m = re.search(r'\["(S\d+)",\s*"Treats eczema', req.user_message)
        claims = [] if m is None else [{
            "span": "treats eczema", "stance": "HOST_ASSERTS", "product_id": CREAM, "field": "other",
            "stated_value": "treats eczema", "evidence": [m.group(1)],
            "source_value": "Claims not approved: treats eczema", "relation": "contradicts",
            "correct_value": "It does not treat eczema."}]
        return RawReply(json.dumps({"claims": claims}), model_version="scripted")


@pytest.mark.legacy_live  # D-434: cites a document passage; production's evidence is the prompter snapshot (N10)
async def test_d374_a_not_approved_phrase_keeps_both_verdicts():
    from app.agents.fact_checker import DROPS

    from .helpers import live_runtime, make_ctx

    llm = _Backend()
    llm.judge(LINE, violations=[violation("ASEAN-2D-DISEASE", "treats eczema")])
    rt = await live_runtime(make_ctx(backend=llm, FACT_RELATION=True, FACT_PROMPT="v5", JUDGE_ARM="single"))
    sink: list = []
    token = DROPS.set(sink)
    try:
        await speak(rt, LINE)
        await rt.utterances.drain()
        alerts = await rt.alerts()
        assert sorted(a.kind for a in alerts if a.status == "active") == ["compliance", "fact"]
        assert not sink  # nothing dropped by code
    finally:
        DROPS.reset(token)
        await close_env(rt)
