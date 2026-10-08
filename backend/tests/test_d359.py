"""D-359: GET /onboarding/regulations (read-only): approved regulation packs with their source files and sections, the
pack active per market and category, and per release the originals its live judge reads (D-358), with a warning when
no regulation matches. A mock-LLM flow on a fictional law pack: upload, approve, a matching release lists the
original, a release of another category shows the warning."""
from __future__ import annotations

import time

from .test_onboarding import EV, _record

LAW = {"name": "Kelmar supplement code", "regulator": "Kelmar authority", "covers": ["food_supplement"],
       "language": "en", "rules": [
           {"rule_id": "K-DISEASE", "title": "No disease claims", "description": "No cure claims.", "severity": "HIGH",
            "rule_category": "Disease", "unacceptable_examples": [], "say_instead_hint": "",
            "evidence": [{"file": "kelmar_code.txt", "locator": "section 2.1", "quote": "must not be presented"}]}]}


def _wait(c, job: str) -> dict:
    for _ in range(200):
        j = c.get(f"/api/onboarding/jobs/{job}").json()
        if j["status"] in ("done", "failed"):
            return j
        time.sleep(0.02)
    raise AssertionError(f"job {job} did not finish")


def test_d359_upload_approve_and_the_originals_each_release_reads(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    from .helpers import make_settings
    from .judge_fakes import ScriptedBackend

    backend = ScriptedBackend()
    backend.outputs[("lawpack_read", "kelmar_code.txt")] = LAW
    backend.outputs[("onboarding_read", "supp.txt")] = _record(category="food_supplement", product_name="Joint Caps")
    backend.outputs[("onboarding_read", "kettle.txt")] = _record(category="kitchen_appliance",
                                                                 product_name="Quick Kettle",
                                                                 approved_claims=[{"text": "Boils fast.",
                                                                                   "evidence": EV}])
    with TestClient(create_app(make_settings(ONBOARDING_DIR=str(tmp_path)), llm_backend=backend)) as c:
        law = c.post("/api/onboarding/lawpacks/jobs", data={"market": "SG", "category": "food_supplement"},
                     files=[("files", ("kelmar_code.txt", b"2.1 must not be presented as curing", "text/plain"))])
        job = law.json()["job_id"]
        assert _wait(c, job)["status"] == "done"
        pack_id = c.post(f"/api/onboarding/jobs/{job}/approve-lawpack", json={}).json()["pack_id"]
        for name in ("supp.txt", "kettle.txt"):
            j = c.post("/api/onboarding/jobs", files=[("files", (name, b"spec", "text/plain"))]).json()["job_id"]
            assert _wait(c, j)["status"] == "done"
            c.post(f"/api/onboarding/jobs/{j}/approve", json={})
        reg = c.get("/api/onboarding/regulations").json()
    [pack] = reg["packs"]
    assert pack["pack_id"] == pack_id and pack["files"] == ["kelmar_code.txt"]
    assert pack["active_for"] == ["food_supplement"] and pack["sections"] == ["kelmar_code.txt · section 2.1"]
    assert "SG" in reg["markets"] and {"food_supplement", "kitchen_appliance"} <= set(reg["categories"])
    rows = {r["product_name"]: r for r in reg["releases"]}
    assert [o["name"] for o in rows["Joint Caps"]["originals"]] == ["kelmar_code.txt"]
    assert rows["Joint Caps"]["warning"] is False
    assert rows["Quick Kettle"]["originals"] == [] and rows["Quick Kettle"]["warning"] is True
