"""Rebuilt onboarding: one regulation PDF into the onboarding bucket (regulations/<regulation_id>/<file name>).

A show of a rebuilt product needs one uploaded regulation file (step 5 checks it); nothing reads the file yet.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from ..context import AppContext, get_ctx
from .products import store_pdf

router = APIRouter(prefix="/regulations")


@router.post("")
async def upload_regulation(file: UploadFile = File(...), ctx: AppContext = Depends(get_ctx)) -> dict:
    out = await store_pdf(ctx, file, "regulations", "reg_")
    return {"regulation_id": out.pop("id"), **out}
