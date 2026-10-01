"""Demo tools (DEV_SPEC §11.1, §12.6, §13.2). Only when DEMO_TOOLS_ENABLED."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..context import AppContext, get_ctx
from ..logic.catalog import DEFAULT_RUNSHEET_ID
from ..models.session import Session
from ..pipelines.runtime import create_session, latest_session
from .errors import ApiError

router = APIRouter()


def demo_tools(ctx: AppContext = Depends(get_ctx)) -> AppContext:
    if not ctx.settings.DEMO_TOOLS_ENABLED:
        raise ApiError(403, "demo_tools_disabled", "Demo tools are disabled (DEMO_TOOLS_ENABLED=false).")
    return ctx


class FeedStartBody(BaseModel):
    pool: bool = True
    bursts: bool = False  # accepted for §11.1; bursts are fired one by one (D-040)


@router.post("/sessions/{session_id}/feed/start")
async def feed_start(session_id: str, body: FeedStartBody | None = None, ctx: AppContext = Depends(demo_tools)) -> dict:
    rt = await ctx.runtimes.get(session_id)
    if (body or FeedStartBody()).pool:
        rt.feed.start_pool()
    return rt.feed.state()


@router.post("/sessions/{session_id}/feed/stop")
async def feed_stop(session_id: str, ctx: AppContext = Depends(demo_tools)) -> dict:
    rt = await ctx.runtimes.get(session_id)
    rt.feed.stop_pool()
    return rt.feed.state()


@router.post("/sessions/{session_id}/feed/burst/{burst_id}")
async def feed_burst(session_id: str, burst_id: str, ctx: AppContext = Depends(demo_tools)) -> dict:
    rt = await ctx.runtimes.get(session_id)
    result = await rt.feed.fire(burst_id)
    await rt.emit("operator.action", {"actor": "operator", "action": "burst", **result, "at": rt.now()})
    return {**result, "feed": rt.feed.state()}


@router.get("/demo/current")
async def demo_current(ctx: AppContext = Depends(get_ctx)) -> Session:
    s = await latest_session(ctx)
    return s if s is not None else await create_session(ctx, DEFAULT_RUNSHEET_ID)


@router.post("/demo/reset")
async def demo_reset(ctx: AppContext = Depends(demo_tools)) -> Session:
    s = await latest_session(ctx)
    runsheet_id = DEFAULT_RUNSHEET_ID
    if s is not None:
        runsheet_id = s.runsheet_id
        await ctx.runtimes.drop(s.session_id)
        await ctx.store.delete_session(s.session_id)
        ctx.bus.forget_session(s.session_id)
    return await create_session(ctx, runsheet_id)
