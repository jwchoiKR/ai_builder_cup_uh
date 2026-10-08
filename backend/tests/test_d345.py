"""D-345: FACT_PROMPT=v7 is v5 plus `stated_as_heard` (the stated value re-read with number-word homophones as
digits), between `source_value` and `relation`. A value that matches only as heard is `uncertain` (no alert); one
that differs both ways contradicts. The default stays v5. Made-up lines on the fictional fixture product."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.models.agent_io import FactRelationOutputV7

from .judge_fakes import CREAM, ScriptedBackend, close_env, speak


def test_d345_stated_as_heard_sits_between_the_source_value_and_the_relation():
    order = list(FactRelationOutputV7.model_json_schema()["$defs"]["FactRelationClaimV7"]["properties"])
    assert order.index("source_value") + 1 == order.index("stated_as_heard") == order.index("relation") - 1
    assert order[:2] == ["span", "stance"]


def test_d345_the_prompt_s_rule_and_examples():
    text = (Path(__file__).parents[2] / "prompts" / "fact_relation_v7.md").read_text(encoding="utf-8")
    assert '"for"/"four" is 4' in text and "Never rearrange, drop or compute digits" in text
    assert "but `stated_as_heard` equals it, the relation is `uncertain`" in text
    examples = text.split("## EXAMPLES", 1)[1]
    claims = [json.loads(m) for m in re.findall(r'\{"claims":\[.*?\]\}', examples)]
    every = [c for block in claims for c in block["claims"]]
    assert every and all("stated_as_heard" in c for c in every)
    heard = {c["stated_value"]: (c["stated_as_heard"], c["relation"]) for c in every if c["stated_value"] !=
             c["stated_as_heard"]}
    assert heard == {"for 0.5 g": ("4.5 g", "uncertain"), "20 for dollars": ("$24", "uncertain"),
                     "1 ate 0 ml": ("180 ml", "uncertain"), "for 20 dollars": ("$420", "contradicts"),
                     "30 ate dollars": ("$308", "contradicts"), "for 5.5 g": ("45.5 g", "contradicts")}


class _V7Backend(ScriptedBackend):
    def __init__(self, relation: str, heard: str):
        super().__init__()
        self.relation, self.heard, self.requests = relation, heard, []

    async def generate(self, req, timeout_ms):
        self.requests.append(req)
        if req.agent != "fact_checker":
            return await super().generate(req, timeout_ms)
        from app.providers.llm import RawReply

        sid = re.search(r'\["(S\d+)",\s*"Live broadcast price', req.user_message).group(1)
        claims = [{"span": "thirty for dollars", "stance": "HOST_ASSERTS", "product_id": CREAM, "field": "price",
                   "stated_value": "S$30 for", "evidence": [sid], "source_value": "S$36.00",
                   "stated_as_heard": self.heard, "relation": self.relation,
                   "correct_value": "S$36.00" if self.relation == "contradicts" else None}]
        return RawReply(json.dumps({"claims": claims}), model_version="scripted")


@pytest.mark.parametrize("relation, heard, alerts", [("uncertain", "S$34", 0), ("contradicts", "S$304", 1)])
async def test_d345_v7_through_the_pipeline(relation, heard, alerts):
    from .helpers import live_runtime, make_ctx

    llm = _V7Backend(relation, heard)
    rt = await live_runtime(make_ctx(backend=llm, FACT_RELATION=True, FACT_PROMPT="v7", JUDGE_ARM="single"))
    try:
        await speak(rt, "It's only thirty for dollars today.")
        await rt.utterances.drain()
        [fact] = [r for r in llm.requests if r.agent == "fact_checker"]
        assert fact.output_model is FactRelationOutputV7 and "stated_as_heard" in fact.system_instruction
        assert len([a for a in await rt.alerts() if a.kind == "fact"]) == alerts
    finally:
        await close_env(rt)


def test_d345_the_default_stays_v5():
    from app.config import Settings

    assert Settings.model_fields["FACT_PROMPT"].default == "v5"
