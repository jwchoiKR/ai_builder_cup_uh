"""D-278 (user priority): a release show runs on a clean, product-neutral base. With data/products, data/runsheets,
data/promos and data/demo absent, the app starts, a made-up non-skincare release shows its alerts, and no output names
the demo brand."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from app.onboarding.read import normalise
from app.onboarding.record import ProductRecord
from app.onboarding.release import product_key, release_pack, save_release

from .helpers import make_ctx
from .judge_fakes import ScriptedBackend

DATA = Path(__file__).resolve().parents[2] / "data"
EV = [{"file": "spec.md", "locator": "table", "quote": "Kettle 1.7 L, S$59.00"}]
DEMO_BRAND = "DAON"


def clean_data(tmp_path: Path) -> Path:
    out = tmp_path / "data"
    shutil.copytree(DATA, out, ignore=shutil.ignore_patterns("products", "runsheets", "promos", "demo"))
    return out


def kettle() -> ProductRecord:
    """A made-up kitchen product (not skincare)."""
    t = lambda x: {"text": x, "evidence": EV}  # noqa: E731
    rec = {"brand": "Larkmoor", "product_name": "Larkmoor Quick Kettle", "short_names": ["the kettle"],
           "category": "kitchen_appliance", "category_evidence": EV, "language": "en", "markets": ["SG"],
           "target_group": [],
           "variants": [{"variant_id": "K17", "name": "Quick Kettle 1.7 L", "size_value": "1.7", "size_unit": "L",
                         "prices": [{"currency": "SGD", "minor": 5900, "kind": "live", "market": "SG", "evidence": EV},
                                    {"currency": "SGD", "minor": 6900, "kind": "list", "market": "SG", "evidence": EV}],
                         "evidence": EV}],
           "ingredients": [], "ingredient_list_complete": False,
           "approved_claims": [t("Boils 1 litre in about 3 minutes.")], "not_approved_claims": [],
           "cautions": [t("Do not immerse the base in water.")], "how_to_use": [t("Fill above the MIN line.")],
           "key_facts": [t("Boils 1 litre in about 3 minutes.")], "offers": [], "qualified_results": [], "avoid_saying": [], "conflicts": []}
    return normalise(ProductRecord.model_validate(rec))[0]


async def test_d278_a_release_show_runs_without_the_demo_data(tmp_path, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import eval_adversarial

    data, onb = clean_data(tmp_path), tmp_path / "onb"
    rec = kettle()
    rid = save_release(onb, rec, "job")
    monkeypatch.setattr(eval_adversarial, "RELEASE", rid)
    real_sleep = __import__("asyncio").sleep
    monkeypatch.setattr(__import__("asyncio"), "sleep", lambda _s: real_sleep(0))
    backend = ScriptedBackend()
    ctx = make_ctx(backend=backend, DATA_DIR=str(data), ONBOARDING_DIR=str(onb))
    try:
        pack = release_pack(ctx.pack, rec, rid, onb)
        pid = product_key(rec)
        line = "It is the best kettle in the world and it boils in ten seconds."
        ps = [p for p in pack.passages if p.product_id == pid and "3 minutes" in p.text and "approved" not in p.passage_id]
        backend.facts(line, {"span": "boils in ten seconds", "field": "usage", "product_id": pid,
                             "stated_value": "10 seconds", "verdict": "contradicted",
                             "correct_value": "about 3 minutes", "passage_id": ps[0].passage_id, "quote": ps[0].text})
        case = {"case_id": "K", "type": "t", "current_product_id": pid, "utterance": line,
                "expected": {"risky": True, "kind": "fact"}}
        row = await eval_adversarial.run_case(ctx, case, 0)
        assert pack.products.products[0].name == "Larkmoor Quick Kettle"
        assert [(a["kind"], a["correct_value"]) for a in row["alerts"] if a["kind"] == "fact"] == [
            ("fact", "about 3 minutes")]
        assert DEMO_BRAND.lower() not in json.dumps(row, ensure_ascii=False).lower()
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()


def test_d278_the_app_starts_and_serves_a_release_without_the_demo_data(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    from .helpers import make_settings

    data, onb = clean_data(tmp_path), tmp_path / "onb"
    rid = save_release(onb, kettle(), "job")
    with TestClient(create_app(make_settings(DATA_DIR=str(data), ONBOARDING_DIR=str(onb)),
                               llm_backend=ScriptedBackend())) as c:
        assert c.get("/api/health").status_code == 200
        assert [r["release_id"] for r in c.get("/api/onboarding/releases").json()] == [rid]
        r = c.post("/api/sessions", json={"release_id": rid})
        assert r.status_code == 201, r.text
        sid = r.json()["session_id"]
        for path in (f"/api/catalog?session={sid}", f"/api/sessions/{sid}/state"):
            body = c.get(path)
            assert body.status_code == 200, (path, body.text)
            assert DEMO_BRAND.lower() not in body.text.lower(), path  # step 3: brand-free screen text
        notice = next(n for n in c.get(f"/api/catalog?session={sid}").json()["notices"]["correction_notices"]
                      if n["template_id"] == "compliance_correction")
        assert "{brand}" in notice["text"] and "skin" not in notice["text"].lower()


def test_d278_a_release_gets_no_demo_brand_rules_and_its_qualifier_rule_from_its_results(tmp_path):
    from app.logic.qualifier import RULE_ID

    data, onb = clean_data(tmp_path), tmp_path / "onb"
    ctx = make_ctx(DATA_DIR=str(data), ONBOARDING_DIR=str(onb))
    try:
        assert not any(r.rule_id.startswith("BRAND-") for r in ctx.pack.rules.rules)
        plain = release_pack(ctx.pack, kettle(), "rel_k_v1", onb)
        rec = ProductRecord.model_validate(kettle().model_dump() | {"qualified_results": [{
            "statement": "Boils 1 litre in 3 minutes", "provenance": "third_party_lab", "qualifier": "tested by Fenmore Labs",
            "conditions": None, "evidence": EV}]})
        tested = release_pack(ctx.pack, rec, "rel_k_v2", onb)
        assert RULE_ID not in {r.rule_id for r in plain.rules.rules}
        assert RULE_ID in {r.rule_id for r in tested.rules.rules}
        assert not any(r.rule_id.startswith("BRAND-") for r in tested.rules.rules)
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()


def test_d278_the_demo_is_a_show_of_its_onboarded_releases(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    from .helpers import make_settings

    data, onb = clean_data(tmp_path), tmp_path / "onb"
    show = json.loads((data / "demo_release" / "show.json").read_text(encoding="utf-8"))["release_ids"]
    with TestClient(create_app(make_settings(DATA_DIR=str(data), ONBOARDING_DIR=str(onb), DEMO_TOOLS_ENABLED=True),
                               llm_backend=ScriptedBackend())) as c:
        s = c.post("/api/demo/reset", json={}).json()
        assert s["release_ids"] == show and len(show) == 2
        cat = c.get(f"/api/catalog?session={s['session_id']}").json()
        assert [p["name"] for p in cat["products"]] == ["Hydra Barrier Cream", "Deep Hydration Ampoule"]
        again = c.post("/api/demo/reset", json={}).json()  # a reset keeps the show
        assert again["release_ids"] == show and again["session_id"] != s["session_id"]
