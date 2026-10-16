"""Sample documents for people trying the service: whatever PDFs sit in the onboarding bucket under
onboarding/sample/products/ and onboarding/sample/regulations/ (changed in the bucket, not in code)."""
from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from ..context import AppContext, get_ctx
from ..pipelines.runtime import ActionError
from .products import _bucket

router = APIRouter(prefix="/samples")
PREFIX = "onboarding/sample/"
Kind = Literal["products", "regulations"]


async def _names(bucket, kind: str) -> list[str]:
    keys = await asyncio.to_thread(bucket.keys, f"{PREFIX}{kind}/")
    return [k.rsplit("/", 1)[1] for k in keys if k.lower().endswith(".pdf")]


@router.get("")
async def list_samples(ctx: AppContext = Depends(get_ctx)) -> dict:
    bucket = _bucket(ctx)
    return {kind: await _names(bucket, kind) for kind in ("products", "regulations")}


@router.get("/{kind}/{name}")
async def download_sample(kind: Kind, name: str, ctx: AppContext = Depends(get_ctx)) -> Response:
    bucket = _bucket(ctx)
    if name not in await _names(bucket, kind):  # only listed files, so no path tricks
        raise ActionError(404, "sample_not_found", f"no sample {name!r}")
    data = await asyncio.to_thread(bucket.download, f"{PREFIX}{kind}/{name}")
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=\"{name}\""})
