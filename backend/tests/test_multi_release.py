"""D-279: a show of 2-3 approved releases (the user's minimal multi-product show), on made-up releases in two
categories: a skincare cream (the market's cosmetics law) and a kitchen kettle (no law pack for its category)."""
from __future__ import annotations

import pytest

from app.models.session import Alert
from app.onboarding.read import normalise
from app.onboarding.record import ProductRecord
from app.onboarding.release import product_key, save_release
from app.pipelines.runtime import create_session

from .helpers import live_runtime, make_ctx
from .judge_fakes import ScriptedBackend, close_env, speak, violation
from .test_clean_base import EV, clean_data, kettle

CREAM_EV = [{"file": "cream.md", "locator": "table", "quote": "Lumen Night Cream 50 mL, S$36.00"}]


def cream() -> ProductRecord:
    t = lambda x: {"text": x, "evidence": CREAM_EV}  # noqa: E731
    rec = kettle().model_dump() | {
        "brand": "Lumen", "product_name": "Lumen Night Cream", "short_names": ["the night cream"],
        "category": "skincare", "category_evidence": CREAM_EV,
        "variants": [{"variant_id": "LC50", "name": "Night Cream 50 mL", "size_value": "50", "size_unit": "mL",
                      "prices": [{"currency": "SGD", "minor": 3600, "kind": "live", "market": "SG", "evidence": CREAM_EV},
                                 {"currency": "SGD", "minor": 4800, "kind": "list", "market": "SG", "evidence": CREAM_EV}],
                      "evidence": CREAM_EV}],
        "approved_claims": [t("Helps skin feel soft overnight.")], "cautions": [t("Avoid the eye area.")],
        "how_to_use": [t("Apply a thin layer at night.")], "key_facts": [t("Made in Korea.")]}
    return normalise(ProductRecord.model_validate(rec))[0]


@pytest.fixture
async def show(tmp_path):
    onb = tmp_path / "onb"
    ids = [save_release(onb, cream(), "job_c"), save_release(onb, kettle(), "job_k")]
    llm = ScriptedBackend()
    ctx = make_ctx(backend=llm, DATA_DIR=str(clean_data(tmp_path)), ONBOARDING_DIR=str(onb))
    s = await create_session(ctx, "", release_ids=ids)
    rt = await ctx.runtimes.get(s.session_id)
    await rt.start()
    await ctx.scheduler.advance(5000)
    yield rt, llm, ids
    await close_env(rt)


async def test_d279_a_show_holds_two_releases_in_order_with_their_own_law(show):
    rt, _, ids = show
    cream_id, kettle_id = product_key(cream()), product_key(kettle())
    assert rt.catalog.order == [cream_id, kettle_id]
    assert (await rt.load_session()).release_ids == ids and rt.pack.releases == {cream_id: ids[0], kettle_id: ids[1]}
    cream_rules = {r.rule_id for r in rt.catalog.rules_for({cream_id})}
    assert any(r.startswith("ASEAN-") for r in cream_rules)
    assert not any(r.startswith("ASEAN-") for r in {r.rule_id for r in rt.catalog.rules_for({kettle_id})})
    # a kettle line that names the cream gets the cream's law too; one that names nothing gets only the kettle's
    assert rt.catalog.line_products(kettle_id, None, ["the Lumen Night Cream heals eczema"]) == {kettle_id, cream_id}
    assert rt.catalog.line_products(kettle_id, None, ["it heals eczema"]) == {kettle_id}


@pytest.mark.legacy_live  # D-434: the rules-JSON path's per-product rule scope (JUDGE_PRODUCTS=named, N1/N5)
async def test_d279_no_alert_from_another_category_s_law(show):
    rt, llm, _ = show
    kettle_id = product_key(kettle())
    from app.pipelines.utterances import operator_switch

    await operator_switch(rt, kettle_id)
    await rt.ctx.scheduler.advance(10_000)
    line = "It heals eczema while it boils."  # names no product: the kettle on air, which has no cosmetics law
    llm.judge(line, violations=[violation("ASEAN-2D-DISEASE", "heals eczema")])
    await speak(rt, line)
    assert [a for a in await rt.alerts() if a.kind == "compliance"] == []
    cream_line = "The Lumen Night Cream heals eczema."  # names the cream: its law applies on the kettle's segment
    llm.judge(cream_line, violations=[violation("ASEAN-2D-DISEASE", "heals eczema")])
    await speak(rt, cream_line)
    assert [a.rule_id for a in await rt.alerts() if a.kind == "compliance"] == ["ASEAN-2D-DISEASE"]  # legacy path


async def test_d279_a_wrong_product_value_is_caught_with_the_right_release_s_quote(show):
    rt, llm, _ = show
    cream_id = product_key(cream())
    line = "The night cream is only fifty-nine dollars."  # the kettle's price
    price = next(p for p in rt.pack.passages if p.product_id == cream_id and "Live broadcast price" in p.text)
    llm.facts(line, {"span": "fifty-nine dollars", "field": "price", "product_id": cream_id, "stated_value": "S$59",
                     "verdict": "contradicted", "correct_value": "S$36.00", "passage_id": price.passage_id,
                     "quote": "Live broadcast price (50 mL): S$36.00"})
    await speak(rt, line)
    facts = [a for a in await rt.alerts() if a.kind == "fact"]
    assert [(a.product_id, a.correct_value) for a in facts] == [(cream_id, "S$36.00")]


async def test_d279_the_api_takes_2_to_3_releases(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    from .helpers import make_settings

    onb = tmp_path / "onb"
    ids = [save_release(onb, cream(), "job_c"), save_release(onb, kettle(), "job_k")]
    with TestClient(create_app(make_settings(DATA_DIR=str(clean_data(tmp_path)), ONBOARDING_DIR=str(onb)),
                               llm_backend=ScriptedBackend())) as c:
        r = c.post("/api/sessions", json={"release_ids": ids})
        assert r.status_code == 201, r.text
        cat = c.get(f"/api/catalog?session={r.json()['session_id']}").json()
        assert [p["name"] for p in cat["products"]] == ["Lumen Night Cream", "Larkmoor Quick Kettle"]
        assert c.post("/api/sessions", json={"release_ids": [*ids, *ids]}).status_code == 400
        assert c.post("/api/sessions", json={"release_ids": [ids[0], "rel_nope_v1"]}).status_code == 404


async def test_d279_eval_runs_a_case_on_its_segment_of_a_show(tmp_path, monkeypatch):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import eval_adversarial

    onb = tmp_path / "onb"
    ids = [save_release(onb, cream(), "job_c"), save_release(onb, kettle(), "job_k")]
    monkeypatch.setattr(eval_adversarial, "RELEASES", ids)
    real_sleep = __import__("asyncio").sleep
    monkeypatch.setattr(__import__("asyncio"), "sleep", lambda _s: real_sleep(0))
    ctx = make_ctx(backend=ScriptedBackend(), DATA_DIR=str(clean_data(tmp_path)), ONBOARDING_DIR=str(onb))
    try:
        for on_air, want in ((1, product_key(cream())), (2, product_key(kettle())), (ids[1], product_key(kettle()))):
            case = {"case_id": "M", "show": "s1", "on_air": on_air, "about": want, "type": "t",
                    "utterance": "It is lovely.", "expected": {"risky": False}}
            assert (await eval_adversarial.run_case(ctx, case, 0))["on_air"] == want
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
