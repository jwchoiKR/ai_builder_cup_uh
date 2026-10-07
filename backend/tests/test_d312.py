"""D-312 (FACT_PROMPT=v2): fact_relation_v2.md checks only what the host asserts, holds sound-alike values back as
`uncertain`, and asks for the documents' value (`source_value`) before the relation. The compliance judge gets a line
on sound-alike tester names. Prompt and schema order only: no code check of the values."""
from __future__ import annotations

import json
import re

import pytest

from app.agents.fact_checker import DROPS, from_relation, sentence_index
from app.models.agent_io import FactRelationOutput, FactRelationOutputV2

from .judge_fakes import CREAM, ScriptedBackend, close_env, speak
from .test_relation import _p


class _V2Backend(ScriptedBackend):
    def __init__(self, source: str):
        super().__init__()
        self.source, self.requests = source, []

    async def generate(self, req, timeout_ms):
        self.requests.append(req)
        if req.agent != "fact_checker":
            return await super().generate(req, timeout_ms)
        from app.providers.llm import RawReply

        m = re.search(r'\["(S\d+)",\s*"Live broadcast price', req.user_message)
        same = self.source == "S$32"
        claims = [] if m is None or "thirty-two" not in req.mock_primary_text else [{
            "span": "thirty-two dollars", "product_id": CREAM, "field": "price", "stated_value": "S$32",
            "evidence": [m.group(1)], "source_value": self.source,
            "relation": "consistent" if same else "contradicts", "correct_value": None if same else self.source}]
        return RawReply(json.dumps({"claims": claims}), model_version="scripted")


@pytest.mark.parametrize("prompt", ["v1", "v2"])
async def test_d312_the_switch_picks_the_prompt_and_schema(prompt):
    from .helpers import live_runtime, make_ctx

    v2 = prompt == "v2"
    llm = _V2Backend("S$36.00")
    rt = await live_runtime(make_ctx(backend=llm, FACT_RELATION=True, FACT_PROMPT=prompt))
    try:
        await speak(rt, "It's only thirty-two dollars today.")
        await rt.utterances.drain()
        [fact] = [r for r in llm.requests if r.agent == "fact_checker"]
        [comp] = [r for r in llm.requests if r.agent == "compliance_judge"]
        assert (fact.output_model is FactRelationOutputV2) is v2 and (fact.output_model is FactRelationOutput) is not v2
        assert ("Only what the host asserts" in fact.system_instruction) is v2
        assert ("Marro Bey labs" in comp.system_instruction) is v2
        [a] = [a for a in await rt.alerts() if a.kind == "fact"]  # the same alert either way
        assert a.correct_value == "S$36.00"
        if v2:
            order = list(FactRelationOutputV2.model_json_schema()["$defs"]["FactRelationClaimV2"]["properties"])
            assert order.index("source_value") == order.index("relation") - 1
    finally:
        await close_env(rt)


def test_d312_an_uncertain_verdict_logs_the_source_value():
    _, index = sentence_index([_p("P", "Net volume: 50 mL.")])
    out = FactRelationOutputV2.model_validate({"claims": [{
        "span": "150 ml tube", "product_id": CREAM, "field": "volume", "stated_value": "150 mL", "evidence": ["S1"],
        "source_value": "50 mL", "relation": "uncertain", "correct_value": None}]})
    sink: list = []
    token = DROPS.set(sink)
    try:
        [c] = from_relation(out, index, set()).claims
    finally:
        DROPS.reset(token)
    assert c.verdict == "not_in_sources"
    assert [(d["reason"], d["source"]) for d in sink] == [("relation uncertain", "50 mL")]
