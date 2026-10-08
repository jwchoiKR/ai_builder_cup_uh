"""D-335: QUESTION_HOLD's model trigger. The context judge says whether a line expects the next line to resolve it
(`expects_resolution`); then the next final is judged with it as two marked lines, even when the first line had no
"?" and was already judged alone (waiting at most 300 ms for that verdict). An alert from the first line is not raised
again. The operator sees "collecting context" while a "?" question waits. Made-up lines only."""
from __future__ import annotations

import pytest

from .judge_fakes import CREAM, ScriptedBackend, events, violation

RELAYED = "A viewer says it cures acne."  # a full stop: no D-088 fragment merge
ANSWER = "Yes, that's what it does."
PAIR = f"[previous line] {RELAYED}\n[this line] {ANSWER}"


class _Record(ScriptedBackend):
    def __init__(self):
        super().__init__()
        self.reqs = []

    async def generate(self, req, timeout_ms):
        self.reqs.append(req)
        return await super().generate(req, timeout_ms)


async def _case(monkeypatch, llm, parts, **settings):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import eval_adversarial

    from .helpers import make_ctx

    monkeypatch.setattr(eval_adversarial, "PART_GAP_S", 0.05)
    ctx = make_ctx(backend=llm, FACT_RELATION=True, FACT_PROMPT="v5", JUDGE_ARM="single", QUESTION_HOLD=True,
                   **settings)
    try:
        return await eval_adversarial.run_case(ctx, {"case_id": "M", "type": "t", "utterance": "",
                                                     "current_product_id": CREAM, "parts": parts,
                                                     "expected": {"risky": True}}, 0)
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()


@pytest.mark.parametrize("expects, delay, paired", [(True, 0.0, True), (False, 0.0, False), (True, 1.0, False)])
async def test_d335_the_model_trigger_pairs_the_next_line(monkeypatch, caplog, expects, delay, paired):
    caplog.set_level("INFO", logger="app.pipelines.utterances")
    llm = _Record()
    llm.expects[RELAYED] = expects
    if delay:
        llm.delays[("context_judge", RELAYED)] = delay  # the verdict comes too late: no pair
    await _case(monkeypatch, llm, [RELAYED, ANSWER])
    texts = [r.mock_primary_text for r in llm.reqs if r.agent == "compliance_judge"]
    assert texts[0] == RELAYED  # judged alone first (no "?")
    assert texts[1] == (PAIR if paired else ANSWER)
    assert any("trigger=model" in r.getMessage() for r in caplog.records) is paired


async def test_d335_an_alert_from_the_first_line_is_not_raised_again(monkeypatch):
    llm = _Record()
    llm.expects[RELAYED] = True
    llm.judge(RELAYED, violations=[violation("ASEAN-2D-DISEASE", "cures acne")])
    llm.judge(PAIR, violations=[violation("ASEAN-2D-DISEASE", "cures acne")])  # D-387: the same claim (span)
    row = await _case(monkeypatch, llm, [RELAYED, ANSWER])
    assert len([a for a in row["alerts"] if a["kind"] == "compliance"]) == 1


async def test_d335_the_operator_sees_collecting_context_while_a_question_waits():
    from .helpers import live_runtime, make_ctx
    from .judge_fakes import close_env, speak

    rt = await live_runtime(make_ctx(backend=ScriptedBackend(), QUESTION_HOLD=True, QUESTION_HOLD_MS=2500))
    try:
        await speak(rt, "Is it waterproof?")
        [started] = await events(rt, "hold.started")
        assert started.payload["max_ms"] == 2500 and await events(rt, "hold.ended") == []
        await rt.ctx.scheduler.advance(2500)
        assert [e.payload["transcript_id"] for e in await events(rt, "hold.ended")] == [started.payload["transcript_id"]]
    finally:
        await close_env(rt)
