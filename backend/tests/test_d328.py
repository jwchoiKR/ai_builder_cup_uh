"""D-328: REPORTED_HOLD and COMPLIANCE_NEG. The fact checker marks each claim the host's or someone else's
(`attributed`) and says what a line does with the previous line's reported words (`previous_line`); a contradiction
in someone else's words waits for the next line's check: rejected, it is dropped; endorsed or neither, it shows; with
no next line it shows when the hold ends. The model decides; code only waits. Made-up lines only."""
from __future__ import annotations

import json
import re

import pytest

from app.models.agent_io import FactRelationOutputH, FactRelationOutputV2

from .judge_fakes import CREAM, ScriptedBackend, close_env, events, speak

REPORTED = "A viewer says the live price is thirty-two dollars."
HOST = "The live price is thirty-two dollars."


class _HoldBackend(ScriptedBackend):
    """A model that follows the HOLD addendum on a price line."""

    def __init__(self):
        super().__init__()
        self.requests = []

    async def generate(self, req, timeout_ms):
        self.requests.append(req)
        if req.agent != "fact_checker":
            return await super().generate(req, timeout_ms)
        from app.providers.llm import RawReply

        sid = re.search(r'\["(S\d+)",\s*"Live broadcast price', req.user_message).group(1)
        recent = req.user_message.split('<data name="RECENT_TRANSCRIPT">')[1].split("</data>")[0]
        line = req.mock_primary_text

        def claim(attributed, relation, span="the live price is thirty-two dollars"):
            return {"span": span, "attributed": attributed, "product_id": CREAM, "field": "price",
                    "stated_value": "S$32" if relation == "contradicts" else "S$36", "evidence": [sid],
                    "source_value": "S$36.00", "relation": relation,
                    "correct_value": "S$36.00" if relation == "contradicts" else None}

        out = {"previous_line": "unrelated", "claims": []}
        if line == REPORTED:
            out["claims"] = [claim("other", "contradicts")]
        elif line == HOST:
            out["claims"] = [claim("host", "contradicts")]
        elif "thirty-two" in recent and line.startswith("No"):
            out = {"previous_line": "rejects", "claims": [claim("host", "consistent", "it's thirty-six")]}
        elif "thirty-two" in recent and line == "Correct.":
            out = {"previous_line": "endorses", "claims": [claim("host", "contradicts")]}
        return RawReply(json.dumps(out), model_version="scripted")


async def _case(monkeypatch, parts: list[str], **settings) -> dict:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import eval_adversarial

    from .helpers import make_ctx

    monkeypatch.setattr(eval_adversarial, "PART_GAP_S", 0)
    ctx = make_ctx(backend=_HoldBackend(), FACT_RELATION=True, FACT_PROMPT="v3", JUDGE_ARM="single",
                   REPORTED_HOLD=True, REPORTED_HOLD_MS=50, **settings)
    try:
        return await eval_adversarial.run_case(ctx, {"case_id": "H", "type": "t", "utterance": "",
                                                     "current_product_id": CREAM, "parts": parts,
                                                     "expected": {"risky": True}}, 0)
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()


@pytest.mark.parametrize("parts, alerts", [
    ([REPORTED, "No, it's thirty-six."], 0),  # rejected by the next line: dropped
    ([REPORTED, "Correct."], 1),  # endorsed: shown (one alert, the endorsement's own claim joins it)
    ([REPORTED], 1),  # nothing comes: shown when the hold ends
    ([REPORTED, "It feels light."], 1),  # the next line neither endorses nor rejects: shown
    ([HOST], 1),  # the host's own claim: not held
])
async def test_d328_a_reported_contradiction_waits_for_the_next_line(monkeypatch, caplog, parts, alerts):
    caplog.set_level("INFO", logger="app.pipelines.utterances")
    row = await _case(monkeypatch, parts)
    facts = [a for a in row["alerts"] if a["kind"] == "fact"]
    assert len(facts) == alerts, row
    held = any("fact alert held" in r.getMessage() for r in caplog.records)
    assert held is (parts[0] == REPORTED)
    if parts[-1].startswith("No"):
        assert any("held alert dropped: rejected by next line" in r.getMessage() for r in caplog.records)


async def test_d328_the_switch_picks_the_schema_and_the_lines():
    from .helpers import live_runtime, make_ctx

    for hold, prompt, model in [(True, "v3", FactRelationOutputH), (False, "v3", FactRelationOutputV2),
                                (True, "v1", None)]:
        llm = _HoldBackend()
        rt = await live_runtime(make_ctx(backend=llm, FACT_RELATION=True, FACT_PROMPT=prompt, REPORTED_HOLD=hold,
                                         COMPLIANCE_NEG=hold))
        try:
            assert (rt.utterances.facts.relation_model is model) if model else \
                rt.utterances.facts.relation_model is not FactRelationOutputH
            assert ("set `attributed` before anything else" in rt.utterances.facts.system_instruction) is (model is
                                                                                                         FactRelationOutputH)
            assert ("warns against a risky use" in rt.utterances.compliance.system_instruction) is hold
        finally:
            await close_env(rt)


async def test_d328_the_host_sees_the_checking_chip_while_it_waits():
    from .helpers import live_runtime, make_ctx

    rt = await live_runtime(make_ctx(backend=_HoldBackend(), FACT_RELATION=True, FACT_PROMPT="v3", JUDGE_ARM="single",
                                     REPORTED_HOLD=True, REPORTED_HOLD_MS=2500))
    try:
        await speak(rt, REPORTED)
        await rt.ctx.scheduler.idle()
        started = [e.payload for e in await events(rt, "verify.started")]
        assert {"transcript_id": started[0]["transcript_id"], "kind": "reported"} in started
        assert [a for a in await rt.alerts() if a.kind == "fact"] == []  # nothing shown yet
        await rt.ctx.scheduler.advance(2500)
        assert len([a for a in await rt.alerts() if a.kind == "fact"]) == 1  # the hold ended: shown
        assert [e.payload["kind"] for e in await events(rt, "verify.done")] == ["reported"]
    finally:
        await close_env(rt)
