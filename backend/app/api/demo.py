"""Demo tools (DEV_SPEC §11.1, §12.6, §13.2): drive a show's live path (lines, comments, the feed, overtime) for
tests, evals and replays. Only when DEMO_TOOLS_ENABLED. The demo show itself is gone (user, 10/10)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..context import AppContext, get_ctx
from ..pipelines.comments import submit_comment
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


class TranscriptBody(BaseModel):
    text: str
    scene: str | None = None  # host-script scene id, used as the mock scenario tag (§7.1)


@router.post("/sessions/{session_id}/transcripts", status_code=201)
async def inject_transcript(session_id: str, body: TranscriptBody, ctx: AppContext = Depends(demo_tools)) -> dict:
    rt = await ctx.runtimes.get(session_id)
    t = await rt.inject_transcript(body.text, scenario=body.scene or "default")
    return t.model_dump()


@router.post("/sessions/{session_id}/demo/simulate-overtime")
async def simulate_overtime(session_id: str, ctx: AppContext = Depends(demo_tools)) -> dict:
    rt = await ctx.runtimes.get(session_id)
    return (await rt.simulate_overtime()).model_dump()


class ScriptCommentBody(BaseModel):
    author: str
    text: str


@router.post("/sessions/{session_id}/demo/comments", status_code=201)
async def script_comment(session_id: str, body: ScriptCommentBody, ctx: AppContext = Depends(demo_tools)) -> dict:
    """D-139: a scripted viewer comment (show replay); viewer input stays off."""
    rt = await ctx.runtimes.get(session_id)
    c = await submit_comment(rt, author_id=f"u_{body.author.lower()}", author_name=body.author, text=body.text,
                             source="script", scenario="replay")
    return c.model_dump()
