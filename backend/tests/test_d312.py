"""D-312: an `uncertain` relation logs the documents' value (`source_value`) as an eval drop. D-432: the v2-v4 prompt
tests went with those prompts; this check runs on v5's schema, which keeps `source_value`."""
from __future__ import annotations

from app.agents.fact_checker import DROPS, from_relation, sentence_index
from app.models.agent_io import FactRelationOutputV5

from .judge_fakes import CREAM
from .test_relation import _p


def test_d312_an_uncertain_verdict_logs_the_source_value():
    _, index = sentence_index([_p("P", "Net volume: 50 mL.")])
    out = FactRelationOutputV5.model_validate({"claims": [{
        "span": "150 ml tube", "stance": "HOST_ASSERTS", "product_id": CREAM, "field": "volume",
        "stated_value": "150 mL", "evidence": ["S1"], "source_value": "50 mL", "relation": "uncertain",
        "correct_value": None}]})
    sink: list = []
    token = DROPS.set(sink)
    try:
        [c] = from_relation(out, index, set()).claims
    finally:
        DROPS.reset(token)
    assert c.verdict == "not_in_sources"
    assert [(d["reason"], d["source"]) for d in sink] == [("relation uncertain", "50 mL")]


def test_d345_the_default_stays_v5():
    from app.config import Settings

    assert Settings.model_fields["FACT_PROMPT"].default == "v5"
