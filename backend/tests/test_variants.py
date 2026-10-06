"""D-281: a product with several sizes never gets one size's price posted as "the" price. Made-up perfume in 30, 50 and
100 mL; each price question names its size (or none), and every posted price must be the asked size's."""
from __future__ import annotations

import json

import pytest

from app.models.session import Message
from app.onboarding.read import normalise
from app.onboarding.record import ProductRecord
from app.onboarding.release import product_key, save_release
from app.pipelines.runtime import create_session
from app.providers.llm import RawReply

from .helpers import make_ctx, say
from .judge_fakes import ScriptedBackend, close_env
from .test_clean_base import clean_data, kettle

EV = [{"file": "fern.md", "locator": "price table", "quote": "Eau de Parfum 30 mL S$60.00, 50 mL S$90.00, 100 mL S$140.00"}]
SIZES = [("30", 6000, 7000), ("50", 9000, 10500), ("100", 14000, 16000)]


def perfume() -> ProductRecord:
    rec = kettle().model_dump() | {
        "brand": "Fernlight", "product_name": "Fernlight Eau de Parfum", "short_names": ["the perfume"],
        "category": "fragrance", "category_evidence": EV, "key_facts": [], "approved_claims": [],
        "variants": [{"variant_id": f"F{s}", "name": f"Eau de Parfum {s} mL", "size_value": s, "size_unit": "mL",
                      "prices": [{"currency": "SGD", "minor": live, "kind": "live", "market": "SG", "evidence": EV},
                                 {"currency": "SGD", "minor": lst, "kind": "list", "market": "SG", "evidence": EV}],
                      "evidence": EV} for s, live, lst in SIZES]}
    return normalise(ProductRecord.model_validate(rec))[0]


def triage(pid: str, question: str, variant: str | None) -> dict:
    return {"kind": "question", "hide_category": None, "product_id": pid, "product_basis": "context", "intent": "price",
            "condition_slots": {"person_type": None, "life_stage": None, "condition": None, "combined_with": None,
                                "time_of_day": None, "variant": variant},
            "canonical_question": question, "group_candidate_id": None, "reason": "t"}


class Shop(ScriptedBackend):
    """The composer answers from the passage it is told to cite (by the question's size, or a wrong one)."""

    def __init__(self, cite: dict[str, str]):
        super().__init__()
        self.cite = cite

    async def generate(self, req, timeout_ms):
        if req.agent == "answer_composer":
            q = next(k for k in self.cite if k in req.user_message)
            passages = json.loads(req.user_message.split('<data name="SOURCE">')[1].split("</data>")[0])
            p = next(x for x in passages if self.cite[q] in x["text"])
            price = p["text"].rsplit("S$", 1)[1].rstrip(".")
            return RawReply(json.dumps({"answer": f"It is S${price}.", "citations": [
                {"passage_id": p["passage_id"], "quote": p["text"]}], "grounded": True, "needs_human": False,
                "reason": "t"}), model_version="scripted")
        return await super().generate(req, timeout_ms)


@pytest.mark.parametrize("order", [(0, 1, 2, 3), (3, 2, 1, 0), (1, 3, 0, 2)])
async def test_d281_every_posted_price_is_the_asked_size_s(tmp_path, order):
    onb = tmp_path / "onb"
    rid = save_release(onb, perfume(), "job_p")
    pid = product_key(perfume())
    asks = [("price of the 100ml?", "What is the price of the 100 mL?", "100ml", "Eau de Parfum 100 mL: list"),
            ("how much for 30 ml one", "How much is the 30 mL?", "30 ml", "(30 ml)"),
            ("50ml price pls", "What is the price of the 50 mL?", "50ml", "(30 ml)"),  # the composer cites the wrong size
            ("how much?", "How much is it?", None, "(30 ml)")]
    llm = Shop({q: cite for _, q, _, cite in asks})
    for text, q, v, _ in asks:
        llm.outputs[("comment_triage", text)] = triage(pid, q, v)
    ctx = make_ctx(backend=llm, DATA_DIR=str(clean_data(tmp_path)), ONBOARDING_DIR=str(onb))
    s = await create_session(ctx, "", release_id=rid)
    rt = await ctx.runtimes.get(s.session_id)
    await rt.start()
    await ctx.scheduler.advance(5000)
    try:
        for i in order:
            await say(rt, f"V{i}", asks[i][0])
        posted = [m.text for m in await rt.ctx.store.query(rt.path("messages"), Message, order_by="created_at")]
        groups = {g.canonical_question: g for g in await rt.groups()}
        assert sorted(x for m in posted for x in ("60.00", "90.00", "140.00") if x in m) == ["140.00", "60.00"]
        assert (groups["How much is it?"].route, groups["How much is it?"].route_reason) == ("OPERATOR",
                                                                                           "several_variants")
        assert groups["What is the price of the 50 mL?"].status != "auto_answered"  # wrong size cited: not posted
    finally:
        await close_env(rt)


def test_d281_no_screen_or_agent_input_states_one_size_as_the_product_s(tmp_path):
    from fastapi.testclient import TestClient

    from app.agents.inputs import product_compact_json
    from app.logic.catalog import Catalog
    from app.main import create_app

    from .helpers import make_settings

    onb = tmp_path / "onb"
    rid = save_release(onb, perfume(), "job_p")
    with TestClient(create_app(make_settings(DATA_DIR=str(clean_data(tmp_path)), ONBOARDING_DIR=str(onb)),
                               llm_backend=ScriptedBackend())) as c:
        sid = c.post("/api/sessions", json={"release_id": rid}).json()["session_id"]
        [p] = c.get(f"/api/catalog?session={sid}").json()["products"]
        assert p["live_price_display"] == "S$60.00 (Eau de Parfum 30 mL)"
        assert p["variants_display"] == ["Eau de Parfum 30 mL: S$60.00", "Eau de Parfum 50 mL: S$90.00",
                                         "Eau de Parfum 100 mL: S$140.00"]
    ctx = make_ctx(DATA_DIR=str(clean_data(tmp_path / "b")), ONBOARDING_DIR=str(onb))
    pack, _ = ctx.pack_for("SG", "en", rid)
    j = product_compact_json(Catalog(pack, rid), product_key(perfume()))
    assert [v["live_price"] for v in j["variants"]] == ["S$60.00", "S$90.00", "S$140.00"]
