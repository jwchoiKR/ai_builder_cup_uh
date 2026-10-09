"""D-296: the relation fact checker (D-435: the only one). The fact checker names its evidence by SOURCE sentence id and states a
relation; code builds the quote.
Made-up lines and passages across categories (skincare, a supplement, a children's product, a fragrance, a kettle)."""
from __future__ import annotations

import json
import re

import pytest

from app.agents.fact_checker import DROPS, from_relation, sentence_index
from app.models.agent_io import FactRelationOutputV5
from app.models.data import Passage

from .judge_fakes import CREAM, PRICE_PASSAGE, ScriptedBackend, close_env, speak


def _p(pid: str, text: str, product: str = CREAM, section: str = "Key facts") -> Passage:
    return Passage(passage_id=pid, product_id=product, doc="sheet", section=section, text=text, score=0.0)


def _rel(*claims) -> FactRelationOutputV5:
    return FactRelationOutputV5.model_validate({"claims": [
        {"span": c[0], "stance": "HOST_ASSERTS", "product_id": c[1], "field": c[2], "stated_value": c[3],
         "evidence": c[4], "source_value": c[6], "relation": c[5], "correct_value": c[6]} for c in claims]})


def test_d296_sentences_are_numbered_once_and_keep_decimals():
    a = _p("A", "Volume: 4.5 mL. Made in Korea.\nDo not share the brush.")
    blocks, index = sentence_index([a, _p("B", "Price: S$36.00"), a])
    assert [s for b in blocks for s in b["sentences"]] == [
        ["S1", "Volume: 4.5 mL."], ["S2", "Made in Korea."], ["S3", "Do not share the brush."], ["S4", "Price: S$36.00"]]
    assert index["S4"][0].passage_id == "B" and len(blocks) == 2  # a repeated passage is numbered once


def test_d296_from_relation():
    _, index = sentence_index([_p(PRICE_PASSAGE, "Live broadcast price: S$36.00. Free delivery.")])
    out = _rel(("thirty-two dollars", CREAM, "price", "S$32", ["S1"], "contradicts", "S$36.00"),
               ("free delivery", CREAM, "price", "free delivery", ["S2"], "consistent", None),
               ("thirty dollars", CREAM, "price", "S$30", ["S9"], "contradicts", "S$36.00"),
               ("time sale price", CREAM, "promo", "S$30", ["promo"], "contradicts", "S$32.40"),
               ("the big one", CREAM, "price", "S$36", ["S1"], "uncertain", None))
    sink: list = []
    token = DROPS.set(sink)
    try:
        got = from_relation(out, index, {"promo"}).claims
    finally:
        DROPS.reset(token)
    assert [(c.verdict, c.passage_id, c.quote) for c in got] == [
        ("contradicted", PRICE_PASSAGE, "Live broadcast price: S$36.00."),  # the quote is built by code
        ("supported", PRICE_PASSAGE, "Free delivery."),
        ("contradicted", None, None),  # D-374: an id SOURCE does not have: applied as given, no quote
        ("contradicted", None, None),  # the active promo
        ("not_in_sources", PRICE_PASSAGE, "Live broadcast price: S$36.00.")]  # uncertain never alerts
    assert [d["reason"] for d in sink] == ["relation uncertain"]  # D-374: no drop, uncertain is only counted


class _RelationBackend(ScriptedBackend):
    """The fact checker answers in raw production JSON (v5 relation shape, D-434), citing the prompter snapshot's
    live price sentence."""

    def __init__(self, relation: str = "contradicts") -> None:
        super().__init__()
        self.relation, self.requests = relation, []

    async def generate(self, req, timeout_ms):
        if req.agent != "fact_checker":
            return await super().generate(req, timeout_ms)
        from app.providers.llm import RawReply

        self.requests.append(req)
        m = re.search(r'\["(S\d+)",\s*"Live price: S\$36', req.user_message)
        claims = [] if m is None or "thirty-two" not in req.mock_primary_text else [{
            "span": "thirty-two dollars", "stance": "HOST_ASSERTS", "product_id": CREAM, "field": "price",
            "stated_value": "S$32", "evidence": [m.group(1)], "source_value": "S$36.00", "relation": self.relation,
            "correct_value": "S$36.00" if self.relation == "contradicts" else None}]
        return RawReply(json.dumps({"claims": claims}), model_version="scripted")
