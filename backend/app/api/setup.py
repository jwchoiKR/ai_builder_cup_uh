"""Setup endpoints (DEV_SPEC §11.1, §12.7). Registered by main.py under /api."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ..context import AppContext, get_ctx
from ..pipelines import setup as svc
from .errors import ApiError

router = APIRouter(prefix="/setup")


@router.get("/documents")
async def documents(ctx: AppContext = Depends(get_ctx)) -> dict:
    return await svc.list_documents(ctx)


@router.post("/documents", status_code=202)
async def upload(request: Request, filename: str = "upload.pdf", ctx: AppContext = Depends(get_ctx)) -> dict:
    """Upload a product sheet as the raw request body (Content-Type: application/pdf); the
    file name is a query parameter. (python-multipart is not a dependency.) Returns an upload job
    whose stages the page polls (D-093); the job's `result` is the former response body."""
    data = await request.body()
    if not data:
        raise ApiError(400, "empty_upload", "The request body must be the PDF file.")
    return (await svc.start_upload(ctx, filename, data)).model_dump()


@router.get("/documents/jobs/{job_id}")
async def upload_job(job_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    return (await svc.get_upload_job(ctx, job_id)).model_dump()


class BriefRunBody(BaseModel):
    product_id: str


@router.post("/brief/run")
async def brief_run(body: BriefRunBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    return (await svc.run_brief(ctx, body.product_id)).model_dump()


@router.get("/brief/{product_id}")
async def brief_get(product_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    record = await svc.get_brief(ctx, product_id)
    if record is None:
        raise ApiError(404, "no_brief", f"The Brief Agent has not run for {product_id} yet.")
    return record.model_dump()


@router.post("/brief/{product_id}/confirm")
async def brief_confirm(product_id: str, body: svc.ConfirmBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    """Confirm one product's glossary (and point drafts): glossary version + 1."""
    return await svc.confirm(ctx, {product_id: body})


@router.post("/glossary/confirm")
async def glossary_confirm(body: svc.ConfirmAllBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    """The page's single "Confirm glossary" button: all reviewed products in one version."""
    return await svc.confirm(ctx, body.products)


@router.get("/glossary")
async def glossary(ctx: AppContext = Depends(get_ctx)) -> dict:
    points = await svc.current_points(ctx)
    return {**await svc.current_glossary(ctx),
            "prompter_points": {pid: [p.model_dump() for p in pts] for pid, pts in points.items()}}
