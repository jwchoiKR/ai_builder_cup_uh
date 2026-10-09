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
