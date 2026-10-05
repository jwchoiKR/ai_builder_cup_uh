"""P0 onboarding steps 1-3: immutable storage, file conversion, the read call and code normalisation."""
from __future__ import annotations

import io

import pytest

from app.onboarding.files import UnsupportedFile, model_part, store
from app.onboarding.read import normalise, read_product
from app.onboarding.record import ProductRecord

from .helpers import make_ctx
from .judge_fakes import ScriptedBackend

EV = [{"file": "spec.docx", "locator": "paragraph 1", "quote": "x"}]


def test_store_is_content_addressed_and_never_overwrites(tmp_path):
    a = store(tmp_path, "d1", "spec.txt", b"one")
    again = store(tmp_path, "d1", "spec.txt", b"one")
    b = store(tmp_path, "d1", "spec.txt", b"two")  # a new version is a new file
    assert a.path == again.path and a.path != b.path and a.path.read_bytes() == b"one"
    with pytest.raises(UnsupportedFile):
        store(tmp_path, "d1", "virus.exe", b"x")


def test_docx_and_xlsx_become_located_text():
    import docx
    import openpyxl

    d = docx.Document()
    d.add_paragraph("Warnings: patch test first.")
    t = d.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "Niacin", "2%"
    buf = io.BytesIO()
    d.save(buf)
    text = model_part("spec.docx", buf.getvalue()).data.decode()
    assert "[paragraph 1] Warnings: patch test first." in text and "[table 1 row 1] Niacin | 2%" in text
    wb = openpyxl.Workbook()
    wb.active.title = "Prices"
    wb.active.append(["SKU", "Price"])
    wb.active.append(["X-1", "S$10.00"])
    buf = io.BytesIO()
    wb.save(buf)
    part = model_part("prices.xlsx", buf.getvalue())
    assert part.mime == "text/plain" and "[sheet Prices row 2] X-1 | S$10.00" in part.data.decode()
    assert model_part("label.jpg", b"\xff\xd8").mime == "image/jpeg"


def _record(**kw) -> dict:
    base = {"brand": "B", "product_name": "P", "short_names": ["p"], "generic_word": "Serum", "category": "Cosmetic",
            "category_evidence": EV, "language": "en",
            "variants": [{"variant_id": "A", "name": "P 30", "size_value": "30.0 ml", "size_unit": "mL",
                          "market": "sg", "prices": [{"currency": "S$", "minor": 3600, "kind": "live", "market": "sg",
                                                       "evidence": EV},
                                                      {"currency": "??", "minor": 1, "kind": "list", "market": None,
                                                       "evidence": EV}], "evidence": EV},
                         {"variant_id": "A", "name": "P 50", "size_value": None, "size_unit": None, "market": None,
                          "prices": [], "evidence": EV},
                         {"variant_id": "Z", "name": "made up", "size_value": None, "size_unit": None, "market": None,
                          "prices": [], "evidence": []}],
            "offers": [], "ingredients": [{"name": "Zinc", "amount_value": "0,50", "amount_unit": "MG", "purpose": None,
                                           "evidence": EV}],
            "ingredient_list_complete": False, "approved_claims": [], "not_approved_claims": [],
            "avoid_saying": [], "qualified_results": [], "cautions": [{"text": "Patch test.", "evidence": []}],
            "how_to_use": [], "key_facts": [], "missing": [], "conflicts": []}
    return base | kw


def test_normalise_currency_units_identity_and_evidence():
    r, notes = normalise(ProductRecord.model_validate(_record()))
    v = r.variants
    assert [x.variant_id for x in v] == ["A", "A_2"]  # the one without evidence is dropped, ids are unique
    assert (v[0].size_value, v[0].size_unit, v[0].market) == ("30", "ml", "SG")
    assert [(m.currency, m.minor, m.market) for m in v[0].prices] == [("SGD", 3600, "SG")]
    assert (r.ingredients[0].amount_value, r.ingredients[0].amount_unit) == ("0.5", "mg")
    assert r.cautions == [] and r.generic_word == "serum" and r.category == "cosmetic"
    assert any("unknown currency" in n for n in notes) and any("cautions" in n for n in notes)


def test_every_field_is_required_in_the_model_schema():
    schema = ProductRecord.model_json_schema()
    assert set(schema["required"]) == set(schema["properties"])
    assert set(schema["$defs"]["Variant"]["required"]) == set(schema["$defs"]["Variant"]["properties"])


async def test_read_product_sends_every_file_and_normalises(tmp_path):
    backend = ScriptedBackend()
    backend.outputs[("onboarding_read", "spec.txt|label.jpg")] = _record()
    seen = []
    original = backend.generate

    async def capture(req, timeout_ms):
        seen.append(req)
        return await original(req, timeout_ms)

    backend.generate = capture
    ctx = make_ctx(backend=backend)
    try:
        res = await read_product(ctx.llm, [model_part("spec.txt", b"hello"), model_part("label.jpg", b"\xff\xd8")])
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
    [req] = seen
    assert [m for _, m in req.parts] == ["text/plain", "text/plain", "text/plain", "image/jpeg"]
    assert res.method == "gemini_whole" and res.record.variants[0].prices[0].currency == "SGD"


def test_d217_the_upload_api_runs_the_same_pipeline(tmp_path):
    import time

    from fastapi.testclient import TestClient

    from app.main import create_app

    from .helpers import make_settings

    backend = ScriptedBackend()
    backend.outputs[("onboarding_read", "spec.txt")] = _record()
    with TestClient(create_app(make_settings(ONBOARDING_DIR=str(tmp_path)), llm_backend=backend)) as c:
        def wait(job: str) -> dict:
            for _ in range(100):
                got = c.get(f"/api/onboarding/jobs/{job}").json()
                if got["status"] in ("done", "failed"):
                    return got
                time.sleep(0.02)
            return got

        r = c.post("/api/onboarding/jobs", files=[("files", ("spec.txt", b"hello", "text/plain"))])
        got = wait(r.json()["job_id"])
        assert got["status"] == "done" and got["result"]["record"]["variants"][0]["prices"][0]["currency"] == "SGD"
        assert (tmp_path / r.json()["job_id"] / "result.json").exists()
        bad = c.post("/api/onboarding/jobs", files=[("files", ("x.exe", b"MZ", "application/octet-stream"))])
        assert wait(bad.json()["job_id"])["status"] == "failed"


async def test_d218_a_release_runs_its_own_one_segment_show(tmp_path):
    from app.onboarding.release import save_release
    from app.pipelines.runtime import create_session

    rec, _ = normalise(ProductRecord.model_validate(_record(
        cautions=[{"text": "Patch test first.", "evidence": EV}],
        approved_claims=[{"text": "Helps skin feel soft.", "evidence": EV}])))
    rid = save_release(tmp_path, rec, "job1")
    assert save_release(tmp_path, rec, "job2") == rid.replace("_v1", "_v2")  # every approval is a new version
    ctx = make_ctx(ONBOARDING_DIR=str(tmp_path))
    try:
        s = await create_session(ctx, "ignored", release_id=rid)
        rt = await ctx.runtimes.get(s.session_id)
        assert s.release_id == rid and rt.catalog.order == ["p"] and rt.catalog.brand == "B"
        assert rt.catalog.money(rt.catalog.live_price_value("p")) == "S$36.00"
        assert [p.text for p in ctx.retriever.passages_of("p") if p.section == "Cautions"] == ["Patch test first."]
        shipped = await create_session(ctx, "daon_skincare_demo")  # the shipped catalog is untouched
        assert (await ctx.runtimes.get(shipped.session_id)).catalog.order != ["p"]
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
