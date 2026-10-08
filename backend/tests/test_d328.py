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

        out = {"previous_line": [], "claims": []}
        if line == REPORTED:
            out["claims"] = [claim("other", "contradicts")]
        elif line == HOST:
            out["claims"] = [claim("host", "contradicts")]
        elif "thirty-two" in recent and line.startswith("No"):
            out = {"previous_line": [{"product_id": CREAM, "field": "price", "stance": "rejects"}],
                   "claims": [claim("host", "consistent", "it's thirty-six")]}
        elif "thirty-two" in recent and line == "Correct.":
            out = {"previous_line": [{"product_id": CREAM, "field": "price", "stance": "endorses"}],
                   "claims": [claim("host", "contradicts")]}
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
    ([REPORTED, "It feels light."], 1),  # the next line neither endorses nor rejects: shown when the hold ends
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


# ---- D-329: the hold settled by its own next line, per claim, with the originating line's timing ----------------

def _claim(field: str, attributed: str = "other", verdict: str = "contradicted"):
    from app.models.agent_io import FactClaim

    c = FactClaim(span=field, field=field, product_id=CREAM, stated_value="x", verdict=verdict, correct_value="y",
                  passage_id=f"P-{field}", quote="q")
    c._attributed = attributed
    return c


async def _line(rt, n: int, claims=(), stances=None, at: int | None = None):
    """Line n's fact check arriving: its transcript (numbered n) and output, applied as the pipeline does."""
    from app.models.agent_io import FactCheckOutput
    from app.models.session import Transcript

    seg = await rt.current_segment()
    t = Transcript(transcript_id=f"tr_l{n}", text=f"line {n}", is_final=True, speech_end_at=at or rt.now(),
                   received_at=at or rt.now(), source="mic", segment_id=seg.segment_id)
    rt.utterances._sequence[t.transcript_id] = n
    out = FactCheckOutput(claims=list(claims), reason="t")
    out._previous_line = {(CREAM, f): s for f, s in (stances or {}).items()}
    async with rt.lock:
        await rt.utterances._apply_facts_locked(t, out, set())
    return t


def _heard(rt, n: int) -> None:
    rt.utterances._sequence[f"tr_l{n}"] = n  # heard, its fact check not back yet


async def _facts(rt):
    return sorted((a.field, a.transcript_id) for a in await rt.alerts() if a.kind == "fact" and a.status == "active")


async def _rt():
    from .helpers import live_runtime, make_ctx

    return await live_runtime(make_ctx(backend=ScriptedBackend(), REPORTED_HOLD=True, REPORTED_HOLD_MS=2500))


async def test_d329_a_partial_rejection_drops_only_the_named_claim():
    rt = await _rt()
    try:
        await _line(rt, 1, [_claim("price"), _claim("volume")])
        await _line(rt, 2, stances={"price": "rejects"})
        assert await _facts(rt) == []  # the amount is still held
        await rt.ctx.scheduler.advance(2500)
        assert await _facts(rt) == [("volume", "tr_l1")]
    finally:
        await close_env(rt)


async def test_d329_only_the_next_line_settles_a_hold():
    """Completion order L1, L3, L2: L3 (unrelated) does not release L1; L2's rejection still drops it."""
    rt = await _rt()
    try:
        await _line(rt, 1, [_claim("price")])
        _heard(rt, 2)
        await _line(rt, 3, stances={})
        assert await _facts(rt) == []
        await rt.ctx.scheduler.advance(2500)  # the hold's time is up, but line 2 was heard and is not checked yet
        assert await _facts(rt) == []
        await _line(rt, 2, stances={"price": "rejects"})
        await rt.ctx.scheduler.advance(20_000)
        assert await _facts(rt) == []
    finally:
        await close_env(rt)


async def test_d329_an_endorsed_alert_keeps_its_own_line_and_its_delay():
    rt = await _rt()
    try:
        heard = rt.now()
        await _line(rt, 1, [_claim("price")], at=heard)
        await rt.ctx.scheduler.advance(2000)
        await _line(rt, 2, [_claim("price", attributed="host")], stances={"price": "endorses"})
        [a] = [a for a in await rt.alerts() if a.kind == "fact"]
        assert a.transcript_id == "tr_l1" and a.shown_at - heard == 2000  # the hold's cost shows in the latency
    finally:
        await close_env(rt)


async def test_d329_two_holds_in_a_row():
    rt = await _rt()
    try:
        await _line(rt, 1, [_claim("price")])
        await _line(rt, 2, [_claim("volume")], stances={})  # also someone else's words; says nothing on line 1
        await _line(rt, 3, stances={"volume": "rejects"})
        await rt.ctx.scheduler.advance(2500)
        assert await _facts(rt) == [("price", "tr_l1")]
    finally:
        await close_env(rt)


async def test_d329_a_timeout_waits_for_the_next_line_s_check_up_to_a_cap():
    rt = await _rt()
    try:
        await _line(rt, 1, [_claim("price")])
        _heard(rt, 2)
        await rt.ctx.scheduler.advance(2500 + 2 * rt.settings.FACT_TIMEOUT_MS - 500)
        assert await _facts(rt) == []  # still waiting for line 2's check
        await rt.ctx.scheduler.advance(1000)
        assert await _facts(rt) == [("price", "tr_l1")]  # the cap: shown
    finally:
        await close_env(rt)


async def test_d329_the_show_ending_shows_what_is_still_held():
    rt = await _rt()
    try:
        await _line(rt, 1, [_claim("price")])
        await rt.end()
        assert [a.field for a in await rt.alerts() if a.kind == "fact"] == ["price"]
        assert [e.payload["kind"] for e in await events(rt, "verify.done")] == ["reported"]
    finally:
        await close_env(rt)
