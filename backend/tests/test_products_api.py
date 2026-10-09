"""Product onboarding, rebuilt (step 1): one PDF straight into the bucket, nothing on local disk."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.onboarding import storage

from .helpers import make_settings


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
