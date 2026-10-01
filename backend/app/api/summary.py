"""Post-broadcast summary (DEV_SPEC §11.1 GET /sessions/{sid}/summary, §12.8)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..context import AppContext, get_ctx
from ..pipelines.summary import get_summary

router = APIRouter()


@router.get("/sessions/{session_id}/summary")
async def session_summary(session_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    """{status, stats, recap, error}; status is computing | ready | failed after the end, else not_ended."""
    return await get_summary(await ctx.runtimes.get(session_id))
