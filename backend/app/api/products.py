"""Product onboarding, rebuilt (step 1): one product PDF straight into the onboarding bucket, nothing on local disk.

The PDF lands at gs://<ONBOARDING_GCS_BUCKET>/products/<product_id>/<file name>. Later steps (read, approve, show)
build on the product id.
"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import PurePath

from fastapi import APIRouter, Depends, File, UploadFile

from ..context import AppContext, get_ctx
from ..onboarding.files import MAX_BYTES
from ..onboarding import storage
from ..pipelines.runtime import ActionError

router = APIRouter(prefix="/products")


@router.post("")
async def upload_product(file: UploadFile = File(...), ctx: AppContext = Depends(get_ctx)) -> dict:
    bucket_name = ctx.settings.ONBOARDING_GCS_BUCKET
    if not bucket_name:
        raise ActionError(503, "no_bucket", "ONBOARDING_GCS_BUCKET is not set")
    name = PurePath(file.filename or "").name
    data = await file.read(MAX_BYTES + 1)
    if not name.lower().endswith(".pdf") or not data.startswith(b"%PDF"):
        raise ActionError(400, "not_pdf", f"PDF files only: {name or '(no name)'}")
    if len(data) > MAX_BYTES:
        raise ActionError(413, "too_large", f"{name}: larger than {MAX_BYTES // (1024 * 1024)} MB")
    product_id = "prd_" + uuid.uuid4().hex[:12]
    key = f"products/{product_id}/{name}"
    bucket = storage.bucket_for(bucket_name, ctx.settings.GCP_PROJECT)
    await asyncio.to_thread(bucket.upload, key, data, create_only=True)
    return {"product_id": product_id, "file": name, "bytes": len(data), "gcs_uri": f"gs://{bucket_name}/{key}"}
