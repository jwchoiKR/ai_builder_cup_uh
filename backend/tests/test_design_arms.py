"""D-187 design arms. Arm B: the model returns the meaning (correction quotes, numbers said, hedges, shout-out
labels) and code only checks it. Arm A stays as it is (every other test runs arm A)."""
from __future__ import annotations

import pytest

from app.agents import arms
from app.config import get_settings
from app.logic.publish import decide
from app.models.agent_io import AnswerLinkB, ComplianceOutputB, UtteranceJudgeOutput

from .helpers import say
from .judge_fakes import CREAM, ScriptedBackend, close_env, judge_output, make_env, speak, violation
from .test_publish import ANSWER, LEX, OFFERED, ans, grp, messages, oily_on_host

PROMPTS = get_settings().prompts_path


def test_arm_b_adds_its_prompt_lines_and_requires_its_fields():
    assert arms.system_instruction("BASE", "compliance_judge", "A", PROMPTS) == "BASE"
    b = arms.system_instruction("BASE", "compliance_judge", "B", PROMPTS)
    assert b.startswith("BASE\n\n") and "correction.quotes" in b and "qualified_result_id" not in b  # D-427
    assert arms.system_instruction("BASE", "compliance_judge", "C", PROMPTS) == b  # C is B's family
    assert "numbers_said" in arms.system_instruction("BASE", "context_judge", "B", PROMPTS)
    assert "shoutout" in arms.system_instruction("BASE", "comment_triage_batch", "B", PROMPTS)
    schema = ComplianceOutputB.model_json_schema()["$defs"]
    assert "quotes" in schema["CorrectionB"]["required"] and "qualified_result_id" not in str(schema)


def _jo(**link) -> UtteranceJudgeOutput:
    out = UtteranceJudgeOutput.model_validate(judge_output(utterance_type="answer", matched="g1", is_answer=True,
                                                           consistent=True))
    out.answer = AnswerLinkB(**out.answer.model_dump(), **link)
    return out


@pytest.mark.parametrize("link, action", [
    ({"numbers_said": [], "hedged": False}, "post"),
    ({"numbers_said": ["4"], "hedged": False}, "verbal_not_posted"),  # the draft "Yes." has no number
    ({"numbers_said": [], "hedged": True}, "verbal_not_posted"),
])
def test_arm_b_posting_compares_the_judges_numbers_and_hedge(link, action):
    d = decide(_jo(**link), OFFERED, grp(), ans(), lex=LEX, high_alert_active=False, facts=None, by_judge=True,
               utterance="I think maybe four")  # the wording itself is not parsed in arm B
    assert d.action == action


class _SecondCallLinks(ScriptedBackend):
    """The context judge links the line to nothing at first and to the group when asked again."""

    def __init__(self, line: str) -> None:
        super().__init__()
        self.line, self.link, self.n = line, None, 0

    async def generate(self, req, timeout_ms):
        if req.agent == "context_judge" and req.mock_primary_text == self.line and self.link:
            self.n += 1
            data = judge_output(**(dict(utterance_type="answer", matched=self.link, is_answer=True, consistent=True)
                                   if self.n > 1 else {}))
            data = {"answer": data["answer"] | {"numbers_said": [], "hedged": False}, "prompter": data["prompter"],
                    "reason": "scripted"}
            import json

            from app.providers.llm import RawReply
            self.calls.append((req.agent, req.mock_primary_text))
            return RawReply(json.dumps(data), model_version="scripted")
        return await super().generate(req, timeout_ms)


def test_arm_d_posting_has_no_code_number_gate():
    from app.models.agent_io import FactCheckOutput

    kw = dict(lex=LEX, high_alert_active=False, facts=FactCheckOutput(claims=[], reason=""), by_judge=True)
    d = decide(_jo(numbers_said=["4"], hedged=False), OFFERED, grp(), ans(), numbers_gate=False, **kw)
    assert d.action == "post"
    d = decide(_jo(numbers_said=[], hedged=True), OFFERED, grp(), ans(), numbers_gate=False, **kw)
    assert d.action == "verbal_not_posted"  # the judge's own "unsure" still holds it


async def test_arm_f_composer_does_no_search(catalog):
    from app.agents.answer_composer import gather_passages

    class NoSearch:
        async def search(self, *a, **k):
            raise AssertionError("searched")

        async def prefetch(self, pid):
            raise AssertionError("prefetched")

    assert await gather_passages(NoSearch(), catalog, {}, product_id=CREAM, intent="price", canonical_question="How much?",
                                 promo=None, top_k=4, search=False) == []


