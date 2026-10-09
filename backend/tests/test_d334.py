"""D-334 (the user's design): QUESTION_HOLD judges a question final together with the next final, as one utterance,
by all three judges (alone when no answer comes in QUESTION_HOLD_MS); CONTEXT_JUDGE gives the fact checker a
CONVERSATION block of the last 3 finals and checks only the last. Made-up lines only."""
from __future__ import annotations

from .judge_fakes import CREAM, ScriptedBackend

QUESTION = "For 30 mL of concentrate, how much water goes in?"
ANSWER = "90 mL."


class _Record(ScriptedBackend):
    def __init__(self):
        super().__init__()
        self.reqs = []

    async def generate(self, req, timeout_ms):
        self.reqs.append(req)
        return await super().generate(req, timeout_ms)


async def _case(monkeypatch, parts, **settings):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import eval_adversarial

    from .helpers import make_ctx

    monkeypatch.setattr(eval_adversarial, "PART_GAP_S", 0)
    llm = _Record()
    ctx = make_ctx(backend=llm, FACT_RELATION=True, FACT_PROMPT="v5", **settings)
    try:
        row = await eval_adversarial.run_case(ctx, {"case_id": "Q", "type": "t", "utterance": "",
                                                    "current_product_id": CREAM, "parts": parts,
                                                    "expected": {"risky": False}}, 0)
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
    return row, llm.reqs


def _texts(reqs, agent):
    return [r.mock_primary_text for r in reqs if r.agent == agent]


async def test_d334_a_question_and_its_answer_are_judged_as_one(monkeypatch, caplog):
    caplog.set_level("INFO", logger="app.pipelines.utterances")
    row, reqs = await _case(monkeypatch, [QUESTION, ANSWER])
    for agent in ("fact_checker", "compliance_judge", "context_judge"):
        texts = _texts(reqs, agent)
        assert len(texts) == 1 and QUESTION in texts[0] and ANSWER in texts[0], (agent, texts)  # judged once
    [fact] = [r for r in reqs if r.agent == "fact_checker"]
    assert f"[previous line] {QUESTION}\n[this line] {ANSWER}" in fact.user_message  # D-335: two marked lines
    assert any("judged as one" in r.getMessage() for r in caplog.records)
    assert any("question final" in r.getMessage() for r in caplog.records)  # STT's "?" is logged


async def test_d334_a_question_with_no_answer_is_judged_alone(monkeypatch, caplog):
    caplog.set_level("INFO", logger="app.pipelines.utterances")
    _, reqs = await _case(monkeypatch, [QUESTION])
    assert _texts(reqs, "fact_checker") == [QUESTION]
    assert any("judged alone: no answer" in r.getMessage() for r in caplog.records)
