"""D-334 (the user's design): QUESTION_HOLD judges a question final together with the next final, as one utterance,
by all three judges (alone when no answer comes in QUESTION_HOLD_MS); CONTEXT_JUDGE gives the fact checker a
CONVERSATION block of the last 3 finals and checks only the last. Made-up lines only."""
from __future__ import annotations

import pytest

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
    ctx = make_ctx(backend=llm, FACT_RELATION=True, FACT_PROMPT="v5", JUDGE_ARM="single", **settings)
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


@pytest.mark.parametrize("hold", [False, True])
async def test_d334_a_question_and_its_answer_are_judged_as_one(monkeypatch, caplog, hold):
    caplog.set_level("INFO", logger="app.pipelines.utterances")
    row, reqs = await _case(monkeypatch, [QUESTION, ANSWER], QUESTION_HOLD=hold)
    for agent in ("fact_checker", "compliance_judge", "context_judge"):
        texts = _texts(reqs, agent)
        if hold:
            assert len(texts) == 1 and QUESTION in texts[0] and ANSWER in texts[0], (agent, texts)  # judged once
        else:
            assert len(texts) == 2, (agent, texts)  # today: each line alone
    if hold:
        [fact] = [r for r in reqs if r.agent == "fact_checker"]
        assert f"[previous line] {QUESTION}\n[this line] {ANSWER}" in fact.user_message  # D-335: two marked lines
        assert any("judged as one" in r.getMessage() for r in caplog.records)
    assert any("question final" in r.getMessage() for r in caplog.records)  # STT's "?" is logged either way


async def test_d334_a_question_with_no_answer_is_judged_alone(monkeypatch, caplog):
    caplog.set_level("INFO", logger="app.pipelines.utterances")
    _, reqs = await _case(monkeypatch, [QUESTION], QUESTION_HOLD=True)
    assert _texts(reqs, "fact_checker") == [QUESTION]
    assert any("judged alone: no answer" in r.getMessage() for r in caplog.records)


async def test_d334_context_judge_sends_the_conversation(monkeypatch):
    _, reqs = await _case(monkeypatch, ["Hello everyone.", QUESTION, ANSWER], CONTEXT_JUDGE=True)
    last = [r for r in reqs if r.agent == "fact_checker"][-1]
    import json
    import re

    convo = json.loads(re.search(r'<data name="CONVERSATION">(.*?)</data>', last.user_message).group(1))
    # the last line is the one checked; the earlier ones come in received order (the test clock does not move, so
    # their order here is not fixed)
    assert convo[-1] == ANSWER and sorted(convo[:-1]) == sorted(["Hello everyone.", QUESTION])
    assert '<data name="UTTERANCE">' not in last.user_message
    assert '<data name="RECENT_TRANSCRIPT">' not in last.user_message
    assert last.user_message.rstrip().endswith("Return the JSON fact check for the last line of CONVERSATION.")
    assert "Check only the facts asserted, or endorsed, in the LAST line" in last.system_instruction
