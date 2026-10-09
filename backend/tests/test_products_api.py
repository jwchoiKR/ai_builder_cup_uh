"""Product onboarding, rebuilt (step 1): one PDF straight into the bucket, nothing on local disk."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import create_app
from app.onboarding import storage

from .helpers import make_settings
from .judge_fakes import ScriptedBackend


def test_upload_puts_one_pdf_in_the_bucket_only(tmp_path, monkeypatch):
    bucket = storage.MemoryBucket()
    monkeypatch.setattr(storage, "bucket_for", lambda name, project=None: bucket)
    try:
        with TestClient(create_app(make_settings(ONBOARDING_DIR=str(tmp_path), ONBOARDING_GCS_BUCKET="fake"))) as c:
            r = c.post("/api/products", files={"file": ("Sheet A.pdf", b"%PDF-1.7 x", "application/pdf")})
            assert r.status_code == 200, r.text
            out = r.json()
            assert out["gcs_uri"] == f"gs://fake/products/{out['product_id']}/Sheet A.pdf"
            assert bucket.download(f"products/{out['product_id']}/Sheet A.pdf") == b"%PDF-1.7 x"
            assert not any(tmp_path.rglob("*.pdf"))  # nothing on local disk
            bad = c.post("/api/products", files={"file": ("a.pdf", b"not a pdf", "application/pdf")})
            assert bad.status_code == 400 and bad.json()["error"]["code"] == "not_pdf"
    finally:
        storage.configure(tmp_path, None)


INFO = {"brand": "Lumen", "product_name": "Night Serum", "currency": "SGD", "list_price": "46.00",
        "live_price": "36.00", "points": [{"text": "Hydrates for 24 hours (in-house test)", "required": True}]}


def test_read_makes_one_model_call_and_stores_the_info(tmp_path, monkeypatch):
    bucket = storage.MemoryBucket()
    monkeypatch.setattr(storage, "bucket_for", lambda name, project=None: bucket)
    backend = ScriptedBackend()
    backend.outputs[("product_read", "Sheet A.pdf")] = INFO
    try:
        with TestClient(create_app(make_settings(ONBOARDING_DIR=str(tmp_path), ONBOARDING_GCS_BUCKET="fake"),
                                   llm_backend=backend)) as c:
            pid = c.post("/api/products", files={"file": ("Sheet A.pdf", b"%PDF-1.7 x", "application/pdf")}
                         ).json()["product_id"]
            r = c.post(f"/api/products/{pid}/read")
            assert r.status_code == 200, r.text
            assert r.json()["info"] == INFO
            assert [a for a, _ in backend.calls] == ["product_read"]
            assert json.loads(bucket.download(f"products/{pid}/info.json")) == INFO
            assert c.post("/api/products/prd_000000000000/read").status_code == 404
    finally:
        storage.configure(tmp_path, None)


def test_approve_fixes_the_read_and_sends_the_pdf_to_the_search_bucket(tmp_path, monkeypatch):
    buckets: dict[str, storage.MemoryBucket] = {}
    monkeypatch.setattr(storage, "bucket_for", lambda name, project=None: buckets.setdefault(name, storage.MemoryBucket()))
    backend = ScriptedBackend()
    backend.outputs[("product_read", "Sheet A.pdf")] = INFO
    try:
        with TestClient(create_app(make_settings(ONBOARDING_DIR=str(tmp_path), ONBOARDING_GCS_BUCKET="fake",
                                                 VERTEX_SEARCH_GCS_BUCKET="search"), llm_backend=backend)) as c:
            pid = c.post("/api/products", files={"file": ("Sheet A.pdf", b"%PDF-1.7 x", "application/pdf")}
                         ).json()["product_id"]
            assert c.post(f"/api/products/{pid}/approve").json()["error"]["code"] == "not_read"
            c.post(f"/api/products/{pid}/read")
            r = c.post(f"/api/products/{pid}/approve")
            assert r.status_code == 200, r.text
            assert r.json()["info"] == INFO and r.json()["warnings"] == []
            assert json.loads(buckets["fake"].download(f"products/{pid}/approved.json"))["info"] == INFO
            assert buckets["search"].download(f"{pid}/Sheet A.pdf") == b"%PDF-1.7 x"
    finally:
        storage.configure(tmp_path, None)


def test_regulation_upload_puts_one_pdf_in_the_bucket(tmp_path, monkeypatch):
    bucket = storage.MemoryBucket()
    monkeypatch.setattr(storage, "bucket_for", lambda name, project=None: bucket)
    try:
        with TestClient(create_app(make_settings(ONBOARDING_DIR=str(tmp_path), ONBOARDING_GCS_BUCKET="fake"))) as c:
            r = c.post("/api/regulations", files={"file": ("Law.pdf", b"%PDF-1.7 law", "application/pdf")})
            assert r.status_code == 200, r.text
            rid = r.json()["regulation_id"]
            assert rid.startswith("reg_") and bucket.download(f"regulations/{rid}/Law.pdf") == b"%PDF-1.7 law"
            assert c.post("/api/regulations", files={"file": ("a.txt", b"x", "text/plain")}).status_code == 400
    finally:
        storage.configure(tmp_path, None)
