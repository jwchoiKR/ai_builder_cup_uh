"""Post-broadcast summary (DEV_SPEC §11.1 GET /sessions/{sid}/summary, §12.8)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..context import AppContext, get_ctx
from ..pipelines.summary import get_summary, retry_summary

router = APIRouter()


@router.get("/sessions/{session_id}/summary")
async def session_summary(session_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    """{status, stats, recap, error}; status is computing | ready | failed after the end, else not_ended."""
    return await get_summary(await ctx.runtimes.get(session_id))


@router.post("/sessions/{session_id}/summary/retry")
async def session_summary_retry(session_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    """D-498: write a failed recap again; {status}. A summary being written or ready is left as it is."""
    return {"status": await retry_summary(await ctx.runtimes.get(session_id))}
