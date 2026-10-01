"""Setup (DEV_SPEC §8.15, §9.2, §12.7): documents, upload and index rebuild, glossary versions,
prompter overrides, and the /api/setup routes."""
from __future__ import annotations

import asyncio
import io
import json
import shutil
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from pypdf import PdfReader, PdfWriter

from app.api import setup as setup_api
from app.api.errors import install_error_handlers
from app.pipelines import setup as svc
from app.pipelines.runtime import ActionError

from .helpers import make_ctx

CREAM, AMPOULE = "cream_hydra_barrier", "ampoule_deep_hydration"
CREAM_PDF = "DAON_LAB_Hydra_Barrier_Cream.pdf"


@pytest.fixture
def data_dir(tmp_path, settings) -> Path:
    data = tmp_path / "data"
    shutil.copytree(settings.data_path, data)
    return data


@pytest.fixture
def ctx(tmp_path, data_dir):
    # Empty fixture dir: the Brief Agent uses its rule-based fallback.
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    return make_ctx(fixtures, DATA_DIR=str(data_dir))


def modified_pdf(path: Path) -> bytes:
    """Same text, different bytes (new metadata): a "new" upload of the cream sheet."""
    writer = PdfWriter()
    writer.append(PdfReader(path))
    writer.add_metadata({"/Title": "Hydra Barrier Cream (revised)"})
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ---- parser -----------------------------------------------------------------------------------


def test_parser_rebuilds_the_shipped_index_exactly(settings):
    shipped = [json.loads(ln) for ln in (settings.data_path / "products" / "passages.jsonl").read_text("utf-8").splitlines()]
    for pdf, pid in ((CREAM_PDF, CREAM), ("DAON_LAB_Deep_Hydration_Ampoule.pdf", AMPOULE)):
        text, pages = svc.pdf_text((settings.data_path / "products" / pdf).read_bytes())
        code = svc.product_code(text)
        built = {p.passage_id: p.model_dump(exclude={"score"}) for p in
                 svc.parse_sheet_text(text, doc=pdf, product_id=pid, code=code)}
        want = {r["passage_id"]: r for r in shipped if r["product_id"] == pid}
        assert pages == 3 and built == want


def test_slugify_and_caution_ids():
    assert svc.slugify("Sodium Hyaluronate (3 molecular weights)") == "sodium-hyaluronate-3-molecular-weights"
    assert svc.slugify("Participants who said skin tone looked more even after 4 weeks", 60).endswith("after-4-wee")
    assert svc._caution_slug("Pregnancy and breastfeeding: the product has not been tested.") == "pregnancy-and-breastfeeding"
    assert svc._caution_slug("Store below 30°C and away from direct sunlight.") == "store-below-30-c-and-away-from-direct-su"


# ---- documents and upload ------------------------------------------------------------------------


async def test_documents_list_shipped_pdfs(ctx):
    docs = (await svc.list_documents(ctx))["documents"]
    assert {(d["name"], d["product_id"], d["status"], d["pages"]) for d in docs} == {
        (CREAM_PDF, CREAM, "Indexed locally", 3),
        ("DAON_LAB_Deep_Hydration_Ampoule.pdf", AMPOULE, "Indexed locally", 3),
    }


async def test_upload_of_a_shipped_pdf_is_a_no_op(ctx, data_dir):
    before = ctx.retriever.doc_version()
    res = await svc.upload_document(ctx, "copy.pdf", (data_dir / "products" / CREAM_PDF).read_bytes())
    assert res == {"status": "already_indexed", "message": "Already indexed", "name": CREAM_PDF}
    assert ctx.retriever.doc_version() == before and not (data_dir / "uploads").exists()


async def test_upload_of_a_new_sheet_rebuilds_that_product_only(ctx, data_dir):
    amp_before = ctx.retriever.passages_of(AMPOULE)
    data = modified_pdf(data_dir / "products" / CREAM_PDF)
    res = await svc.upload_document(ctx, "cream_v2.pdf", data)
    assert res["status"] == "indexed" and res["product_id"] == CREAM and res["passages"] == 38
    assert res["doc_version"] == 1 == ctx.retriever.doc_version()
    assert (data_dir / "uploads" / "cream_v2.pdf").read_bytes() == data
    cream = ctx.retriever.passages_of(CREAM)
    assert len(cream) == 38 and {p.doc for p in cream} == {"cream_v2.pdf"}
    assert ctx.retriever.passages_of(AMPOULE) == amp_before
    hits = await ctx.retriever.search("oily skin", product_filter=CREAM, top_k=1, timeout_ms=500)
    assert hits[0].passage_id == "DL-CR-01#frequently-asked-questions#is-it-suitable-for-oily-skin"
    docs = (await svc.list_documents(ctx))["documents"]
    assert any(d["source"] == "upload" and d["name"] == "cream_v2.pdf" for d in docs)
    again = await svc.upload_document(ctx, "cream_v2_again.pdf", data)
    assert again["status"] == "already_indexed" and ctx.retriever.doc_version() == 1
    shipped = (data_dir / "products" / "passages.jsonl").read_text("utf-8")
    assert "cream_v2.pdf" not in shipped  # the shipped index file is never modified
    assert "Hydra Barrier Cream" in await svc.document_text(ctx, CREAM)  # Brief input is the uploaded sheet


async def test_upload_rejects_bad_files(ctx):
    with pytest.raises(ActionError, match="PDF"):
        await svc.upload_document(ctx, "notes.txt", b"hello")
    with pytest.raises(ActionError) as e:
        await svc.upload_document(ctx, "blank.pdf", blank_pdf())
    assert e.value.code == "unknown_product_code"


# ---- glossary and prompter overrides -------------------------------------------------------------


async def test_default_glossary_is_version_0(ctx):
    g = await svc.current_glossary(ctx)
    terms = {t["term"]: t["kind"] for t in g["terms"]}
    assert g["version"] == 0 and g["confirmed_at"] is None
    assert terms["DAON LAB"] == "brand" and terms["Hydra Barrier Cream"] == "product"
    assert {"Panthenol", "Ceramide NP", "Niacinamide", "Centella Asiatica Leaf Water"} <= set(terms)
    assert "Volume" not in terms and "Ph" not in terms  # only ingredient amounts from key facts


async def test_confirm_bumps_version_once_per_confirmation(ctx):
    cream = svc.ConfirmBody(glossary=[svc.TermChoice(term="Hydra Barrier Cream", kind="product", spoken_forms=["hydra barrier cream"]),
                                      svc.TermChoice(term="corneometer", kind="technical", spoken_forms=["cor-nee-ometer"]),
                                      svc.TermChoice(term="Squalane", kind="ingredient", include=False)])
    amp = svc.ConfirmBody(glossary=[svc.TermChoice(term="Niacinamide", kind="ingredient", spoken_forms=["nia-sin-a-mide"])])
    g = await svc.confirm(ctx, {CREAM: cream, AMPOULE: amp})
    terms = {t["term"] for t in g["terms"]}
    assert g["version"] == 1 and g["confirmed_at"] is not None
    assert {"DAON LAB", "corneometer", "Niacinamide"} <= terms and "Squalane" not in terms
    g2 = await svc.confirm(ctx, {AMPOULE: amp})
    assert g2["version"] == 2 and "corneometer" in {t["term"] for t in g2["terms"]}  # cream terms kept
    with pytest.raises(ActionError):
        await svc.confirm(ctx, {})


async def test_edited_and_added_terms_are_confirmed_as_edited(ctx):
    """D-094: the operator may change a term, its kind and spoken forms, or add a term."""
    edited = svc.ConfirmBody(glossary=[
        svc.TermChoice(term="  Hydra   Barrier Cream ", kind="product",
                       spoken_forms=["hydra barrier cream", " Hydra Barrier Cream ", "", "hydra cream"]),
        svc.TermChoice(term="DAON LAB cream", kind="product", spoken_forms=["dawn lab cream"], source_section="Added on /setup"),
    ])
    g = await svc.confirm(ctx, {CREAM: edited})
    [hydra, added] = g["terms_by_product"][CREAM]
    assert hydra == {"term": "Hydra Barrier Cream", "kind": "product", "spoken_forms": ["hydra barrier cream", "hydra cream"],
                     "source_section": ""}
    assert added["term"] == "DAON LAB cream" and added["source_section"] == "Added on /setup"
    for bad, code in ((svc.TermChoice(term="   ", kind="value"), "invalid_term"),
                      (svc.TermChoice(term="hydra barrier CREAM", kind="product"), "duplicate_term")):
        with pytest.raises(ActionError) as e:
            await svc.confirm(ctx, {CREAM: svc.ConfirmBody(glossary=[edited.glossary[0], bad])})
        assert e.value.code == code
    assert (await svc.current_glossary(ctx))["version"] == 1  # a rejected confirmation changes nothing


async def test_prompter_overrides_replace_and_add(ctx):
    body = svc.ConfirmBody(prompter_points=[
        svc.PointChoice(action="replace", point_id="cr-p2", text="Ceramide NP 1%, panthenol 5% and squalane 3%."),
        svc.PointChoice(action="add", text="Airless pump tube keeps the formula fresh."),
        svc.PointChoice(action="add", text="Can be used under makeup."),
    ])
    await svc.confirm(ctx, {CREAM: body})
    points = (await svc.prompter_overrides(ctx))[CREAM]
    by_id = {p.point_id: p for p in points}
    assert by_id["cr-p2"].text.startswith("Ceramide NP 1%, panthenol 5% and") and by_id["cr-p2"].required
    assert by_id["cr-x1"].required is False and by_id["cr-x2"].text == "Can be used under makeup."
    assert [p.point_id for p in points][:6] == ["cr-p1", "cr-p2", "cr-p3", "cr-p4", "cr-p5", "cr-p6"]
    assert AMPOULE not in await svc.prompter_overrides(ctx)
    with pytest.raises(ActionError) as e:
        await svc.confirm(ctx, {CREAM: svc.ConfirmBody(prompter_points=[svc.PointChoice(action="add", text="It cures eczema.")])})
    assert e.value.code == "restricted_phrase"
    with pytest.raises(ActionError) as e:
        await svc.confirm(ctx, {CREAM: svc.ConfirmBody(prompter_points=[svc.PointChoice(action="add", text="x" * 91)])})
    assert e.value.status == 400
    assert (await svc.current_glossary(ctx))["version"] == 1  # failed confirmations change nothing


async def test_run_brief_stores_the_result(ctx):
    record = await svc.run_brief(ctx, CREAM)
    assert record.status == "ok" and record.output["product_id"] == CREAM
    assert (await svc.get_brief(ctx, CREAM)).ran_at == record.ran_at
    assert await svc.get_brief(ctx, AMPOULE) is None
    with pytest.raises(ActionError):
        await svc.run_brief(ctx, "nope")


# ---- API ------------------------------------------------------------------------------------------


@pytest.fixture
async def client(ctx):
    app = FastAPI()
    app.state.ctx = ctx
    install_error_handlers(app)
    app.include_router(setup_api.router, prefix="/api")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api") as c:
        yield c


async def finished_job(client, job_id: str) -> dict:
    for _ in range(200):
        job = (await client.get(f"/setup/documents/jobs/{job_id}")).json()
        if job["status"] != "running":
            return job
        await asyncio.sleep(0.02)
    raise AssertionError("upload job did not finish")


async def test_upload_job_reports_each_stage(client, data_dir):
    """D-093: a new sheet goes through every local stage, each with a short detail."""
    up = await client.post("/setup/documents", params={"filename": "cream_v2.pdf"}, content=modified_pdf(data_dir / "products" / CREAM_PDF),
                           headers={"Content-Type": "application/pdf"})
    assert up.status_code == 202
    first = up.json()
    assert [s["stage_id"] for s in first["stages"]] == ["receive", "check", "read", "match", "split", "index", "ready"]
    assert first["stages"][0]["status"] == "done"
    job = await finished_job(client, first["job_id"])
    assert job["status"] == "done" and job["result"]["status"] == "indexed"
    assert all(s["status"] == "done" for s in job["stages"])
    details = {s["stage_id"]: s["detail"] for s in job["stages"]}
    assert details["match"] == "DL-CR-01 · Hydra Barrier Cream" and details["split"].endswith("passages")


async def test_upload_job_marks_the_failing_stage(client):
    up = await client.post("/setup/documents", params={"filename": "notes.pdf"}, content=b"hello",
                           headers={"Content-Type": "application/pdf"})
    job = await finished_job(client, up.json()["job_id"])
    assert job["status"] == "failed" and job["error"] == "Upload a PDF product sheet."
    by_id = {s["stage_id"]: s["status"] for s in job["stages"]}
    assert by_id["check"] == "failed" and by_id["read"] == "pending"
    assert (await client.get("/setup/documents/jobs/nope")).status_code == 404


async def test_api_happy_path(client, data_dir):
    docs = (await client.get("/setup/documents")).json()
    assert len(docs["documents"]) == 2 and docs["doc_version"] == 0
    assert (await client.get(f"/setup/brief/{CREAM}")).status_code == 404
    run = await client.post("/setup/brief/run", json={"product_id": CREAM})
    assert run.status_code == 200 and run.json()["status"] == "ok"
    brief = (await client.get(f"/setup/brief/{CREAM}")).json()
    terms = [{**t, "include": True} for t in brief["output"]["glossary"]]
    g = (await client.post("/setup/glossary/confirm", json={"products": {CREAM: {"glossary": terms}}})).json()
    assert g["version"] == 1
    g2 = (await client.post(f"/setup/brief/{AMPOULE}/confirm", json={"glossary": [], "prompter_points": []})).json()
    assert g2["version"] == 2
    full = (await client.get("/setup/glossary")).json()
    assert full["version"] == 2 and [p["point_id"] for p in full["prompter_points"][AMPOULE]][0] == "am-p1"
    up = await client.post("/setup/documents", params={"filename": "same.pdf"},
                           content=(data_dir / "products" / CREAM_PDF).read_bytes(),
                           headers={"Content-Type": "application/pdf"})
    assert up.status_code == 202
    job = await finished_job(client, up.json()["job_id"])
    assert job["status"] == "done" and job["result"]["message"] == "Already indexed"
    bad = await client.post("/setup/brief/run", json={"product_id": "nope"})
    assert bad.status_code == 404 and bad.json()["error"]["code"] == "unknown_product"
    empty = await client.post("/setup/documents", content=b"")
    assert empty.status_code == 400
