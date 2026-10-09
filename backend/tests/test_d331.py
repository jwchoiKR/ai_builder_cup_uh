"""D-331: FACT_PROMPT=v5 is v3 plus a stance per claim (HOST_ASSERTS, HOST_ENDORSES, REPORTS_OR_ASKS), decided right
after the span. Only the host's own facts are checked: a REPORTS_OR_ASKS claim never alerts, whatever its relation.
No hold and no code logic: code only reads the field. Made-up lines only."""
from __future__ import annotations

import json
import re

import pytest

from app.models.agent_io import FactRelationOutputV5

from .judge_fakes import CREAM, ScriptedBackend, close_env, speak


class _V5Backend(ScriptedBackend):
    def __init__(self, stance: str, relation: str = "contradicts"):
        super().__init__()
        self.stance, self.relation, self.requests = stance, relation, []

    async def generate(self, req, timeout_ms):
        self.requests.append(req)
        if req.agent != "fact_checker":
            return await super().generate(req, timeout_ms)
        from app.providers.llm import RawReply

        sid = re.search(r'\["(S\d+)",\s*"Live price: S\$36', req.user_message).group(1)  # the prompter snapshot
        claims = [] if "thirty-two" not in req.mock_primary_text else [{
            "span": "thirty-two dollars", "stance": self.stance, "product_id": CREAM, "field": "price",
            "stated_value": "S$32", "evidence": [sid], "source_value": "S$36.00", "relation": self.relation,
            "correct_value": "S$36.00"}]
        return RawReply(json.dumps({"claims": claims}), model_version="scripted")


@pytest.mark.parametrize("stance, relation, alerts", [
    ("HOST_ASSERTS", "contradicts", 1),
    ("HOST_ENDORSES", "contradicts", 1),  # a compound line or an endorsement: checked
    ("REPORTS_OR_ASKS", "not_checked", 0),
    ("REPORTS_OR_ASKS", "contradicts", 0),  # the stance wins: someone else's words never alert
])
async def test_d331_only_the_host_s_own_facts_alert(stance, relation, alerts, caplog):
    from .helpers import live_runtime, make_ctx

    caplog.set_level("INFO", logger="app.agents.fact_checker")
    llm = _V5Backend(stance, relation)
    rt = await live_runtime(make_ctx(backend=llm))  # D-434: the production defaults
    try:
        await speak(rt, "A viewer says it's thirty-two dollars.")
        await rt.utterances.drain()
        assert len([a for a in await rt.alerts() if a.kind == "fact"]) == alerts
        [fact] = [r for r in llm.requests if r.agent == "fact_checker"]
        assert issubclass(fact.output_model, FactRelationOutputV5)
        assert "adding `stance` must not add claims" in fact.system_instruction
        assert any(f"fact claims 1 fact_relation_v5_v1: {{'{stance}': 1}}" in r.getMessage() for r in caplog.records)
    finally:
        await close_env(rt)


def test_d331_the_stance_comes_right_after_the_span():
    order = list(FactRelationOutputV5.model_json_schema()["$defs"]["FactRelationClaimV5"]["properties"])
    assert order[:2] == ["span", "stance"] and order.index("stance") < order.index("evidence") < order.index("relation")


def test_d331_the_prompt_s_examples_carry_a_stance_on_every_claim():
    from pathlib import Path

    text = (Path(__file__).parents[2] / "prompts" / "fact_relation_v5.md").read_text(encoding="utf-8")
    examples = text.split("## EXAMPLES", 1)[1]
    claims = re.findall(r'\{"span":"[^"]*",("stance":"[A-Z_]+")?', examples)
    assert claims and all(claims)
    for stance in ("HOST_ASSERTS", "HOST_ENDORSES", "REPORTS_OR_ASKS"):
        assert f'"stance":"{stance}"' in examples
