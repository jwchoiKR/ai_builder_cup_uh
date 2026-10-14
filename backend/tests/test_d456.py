"""D-456: fact-checker probe arms, each an env setting, all off by default. FACT_PROMPT=v5_cot asks for a short
`reasoning` FIRST in each claim (logged in the agent-call output, decides nothing); SINGLE_FACTS_THINKING and
FACTS_MODEL set the fact checker's thinking level and model. The fact deadline, the retry and the hedge stay as they
are. Made-up lines; the answers are scripted (no Gemini)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from app.config import Settings
from app.models.agent_io import FactRelationOutputV5Cot
from app.models.session import AgentCall
from app.providers.llm import RawReply

from .helpers import make_ctx, product_show, text_pdf
from .judge_fakes import ScriptedBackend, close_env, speak

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

REG = text_pdf("Lunelle Code\n2.1 A cosmetic must not be presented as treating disease.\n")
CREAM = {"brand": "Lunelle", "product_name": "Hydra Calm Cream", "category": "face cream", "currency": "SGD",
         "variants": [{"label": "", "list_price": "42.00", "live_price": "36.00"}],
         "points": [{"text": "Fragrance-free.", "required": True}]}
PID = "prd_000000000101"
LINE = "And today it's only thirty-two dollars."
REASONING = "Host commits to: the live price is S$32 now. Evidence says: the live price is S$36.00. Same: no."


class _Backend(ScriptedBackend):
    """The fact checker answers a contradiction on LINE in the shape the request asks for (with `reasoning` when its
    schema has it); `invalid_first` makes the first fact answer unparseable."""

    def __init__(self, invalid_first: bool = False):
        super().__init__()
        self.requests, self.invalid_first = [], invalid_first

    async def generate(self, req, timeout_ms):
        self.requests.append(req)
        if req.agent != "fact_checker":
            return await super().generate(req, timeout_ms)
        if self.invalid_first:
            self.invalid_first = False
            return RawReply("not json", model_version="scripted")
        sid = re.search(r'\["(S\d+)",\s*"[^"]*36\.00', req.user_message).group(1)  # the prompter snapshot
        claim = {"span": "only thirty-two dollars", "stance": "HOST_ASSERTS", "product_id": PID, "field": "price",
                 "stated_value": "S$32", "evidence": [sid], "source_value": "S$36.00", "relation": "contradicts",
                 "correct_value": "S$36.00", "say": "The live price is S$36.00."}
        if "reasoning" in json.dumps(req.output_model.model_json_schema()):
            claim = {"reasoning": REASONING, **claim}
        return RawReply(json.dumps({"claims": [claim] if req.mock_primary_text == LINE else []}),
                        model_version="scripted")


async def _show(llm, **settings):
    from app.pipelines.runtime import create_session

    ctx = make_ctx(backend=llm, **settings)
    s = await create_session(ctx, "", release_id=product_show(ctx, CREAM, [("lunelle_code.pdf", REG)], PID))
    rt = await ctx.runtimes.get(s.session_id)
    await rt.start()
    await ctx.scheduler.advance(5000)
    return rt


def _fact_requests(llm):
    return [r for r in llm.requests if r.agent == "fact_checker"]


def test_d456_the_defaults_are_today_s():
    f = Settings.model_fields
    assert (f["FACT_PROMPT"].default, f["SINGLE_FACTS_THINKING"].default, f["FACTS_MODEL"].default) == ("v5", "LOW",
                                                                                            "gemini-3.8-flash")  # D-466


def test_d456_reasoning_is_the_first_field_of_a_claim():
    order = list(FactRelationOutputV5Cot.model_json_schema()["$defs"]["FactRelationClaimV5Cot"]["properties"])
    assert order[:3] == ["reasoning", "span", "stance"]


def test_d456_the_cot_prompt_is_v5_plus_reasoning_in_every_example(prompts):
    v5, cot = prompts["fact_relation_v5"], prompts["fact_relation_v5_cot"]
    assert cot.version == "fact_relation_v5_cot_v1" and cot.user_template == v5.user_template
    examples = cot.system_instruction.split("## EXAMPLES", 1)[1]
    outs = [json.loads(b) for b in re.findall(r"```json\n(.*?)\n```", examples, re.S)]
    claims = [c for o in outs for c in o["claims"]]
    assert len(outs) == 12 and len(claims) == 10
    for o in outs:
        FactRelationOutputV5Cot.model_validate(o)
    assert all(list(c)[0] == "reasoning" and len(c["reasoning"].split()) <= 30 for c in claims)
    # the rest of each example is v5's, unchanged
    assert re.sub(r'"reasoning":"(?:[^"\\]|\\.)*",', "", examples) == v5.system_instruction.split("## EXAMPLES", 1)[1]


async def test_d456_v5_cot_alerts_as_v5_and_logs_the_reasoning():
    llm = _Backend()
    rt = await _show(llm, FACT_PROMPT="v5_cot")
    try:
        await speak(rt, LINE)
        await rt.utterances.drain()
        [req] = _fact_requests(llm)
        assert req.prompt_version == "fact_relation_v5_cot_v1"
        assert "`reasoning`: first" in req.system_instruction
        assert (req.model, req.thinking_level) == ("gemini-3.8-flash", "LOW")  # D-466
        [fact] = [a for a in await rt.alerts() if a.kind == "fact"]
        assert (fact.correct_value, fact.status) == ("S$36.00", "active")
        [call] = [c for c in await rt.ctx.store.query(rt.path("agent_calls"), AgentCall) if c.agent == "fact_checker"]
        assert call.output["claims"][0]["reasoning"] == REASONING
    finally:
        await close_env(rt)


@pytest.mark.parametrize("arm, want", [
    ({}, ("gemini-3.8-flash", "LOW", "fact_relation_v5_v2")),  # D-466
    ({"SINGLE_FACTS_THINKING": "MEDIUM"}, ("gemini-3.8-flash", "MEDIUM", "fact_relation_v5_v2")),
    ({"SINGLE_FACTS_THINKING": "MEDIUM", "FACT_PROMPT": "v5_cot"},
     ("gemini-3.8-flash", "MEDIUM", "fact_relation_v5_cot_v1")),
    ({"FACTS_MODEL": ""}, ("gemini-3.5-flash-lite", "LOW", "fact_relation_v5_v2")),  # empty = SINGLE_MODEL
])
async def test_d456_each_arm_changes_only_the_fact_call(arm, want):
    llm = _Backend()
    rt = await _show(llm, **arm)
    try:
        await speak(rt, LINE)
        await rt.utterances.drain()
        [req] = _fact_requests(llm)
        assert (req.model, req.thinking_level, req.prompt_version) == want
        assert 4000 < req.deadline_ms <= 5000 and req.hedge and req.retry_429  # the line's 5 s fact deadline, as today
        [comp] = [r for r in llm.requests if r.agent == "compliance_judge"]
        assert (comp.model, comp.thinking_level) == ("gemini-3.5-flash-lite", "LOW")
        assert [a.correct_value for a in await rt.alerts() if a.kind == "fact"] == ["S$36.00"]
    finally:
        await close_env(rt)


async def test_d456_an_invalid_cot_answer_is_retried_as_today():
    llm = _Backend(invalid_first=True)
    rt = await _show(llm, FACT_PROMPT="v5_cot")
    try:
        await speak(rt, LINE)
        await rt.utterances.drain()
        first, second = _fact_requests(llm)
        assert first.seeded and not second.seeded  # D-408: the retry goes without the seed
        assert [a.correct_value for a in await rt.alerts() if a.kind == "fact"] == ["S$36.00"]
    finally:
        await close_env(rt)


async def test_d456_the_eval_records_the_fact_call_s_latency_arm_and_reasoning(monkeypatch):
    import eval_adversarial

    llm = _Backend()
    ctx = make_ctx(backend=llm, FACT_PROMPT="v5_cot", FACTS_MODEL="gemini-3.8-flash")
    monkeypatch.setattr(eval_adversarial, "RELEASE", product_show(ctx, CREAM, [("lunelle_code.pdf", REG)], PID))
    row = await eval_adversarial.run_case(ctx, {"case_id": "C1", "current_product_id": PID, "utterance": LINE}, 1)
    try:
        [call] = [c for c in row["calls"] if c["agent"] == "fact_checker"]
        assert call["output"]["claims"][0]["reasoning"] == REASONING
        assert (call["model"], call["prompt_version"], call["status"]) == (
            "gemini-3.8-flash", "fact_relation_v5_cot_v1", "ok")
        assert isinstance(call["latency_ms"], int)
        [line] = row["facts"]
        assert (line["input"], line["tries"], line["final_status"]) == (LINE, 1, "ok") and line["ms"] >= 0
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
