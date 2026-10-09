"""Demo tools (DEV_SPEC §11.1, §12.6, §13.2). Only when DEMO_TOOLS_ENABLED."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..context import AppContext, get_ctx
from ..logic.catalog import DEFAULT_RUNSHEET_ID
from ..models.session import Session
from ..pipelines.comments import submit_comment
from ..pipelines.demo_script import load_host_script
from ..pipelines.runtime import SESSIONS, create_session, latest_session
from ..onboarding.demo import demo_release_ids
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


@router.get("/demo/script")
async def demo_script(ctx: AppContext = Depends(get_ctx)) -> dict:
    return {"steps": [s.as_dict() for s in load_host_script(str(ctx.settings.data_path))]}


def _is_demo(ctx: AppContext, s: Session) -> bool:
    """D-332: a demo show: the shipped run-sheet's, or the demo releases' (not a test drive or a release show)."""
    return s.runsheet_id == DEFAULT_RUNSHEET_ID or (bool(s.release_ids) and s.release_ids == demo_release_ids(ctx))


@router.get("/demo/current")
async def demo_current(ctx: AppContext = Depends(get_ctx)) -> Session:
    """The demo show every screen opened without ?session joins (the Studio's too). D-332: the newest demo show that
    has not ended; a new one when there is none (an ended show or a test drive is never picked)."""
    found = await ctx.store.query(SESSIONS, Session, order_by="created_at", descending=True, limit=20)
    s = next((x for x in found if x.status != "ended" and _is_demo(ctx, x)), None)
    return s if s is not None else await _demo_show(ctx)


async def _demo_show(ctx: AppContext, show_mode: str = "solo", assistant: bool = True,
                     previous: Session | None = None) -> Session:
    """D-278: the demo is a show of its onboarded releases (D-279); the old run-sheet only where a demo pack still
    has it (the tests)."""
    if previous is not None and previous.release_ids:
        return await create_session(ctx, "", show_mode, assistant=assistant, release_ids=previous.release_ids)
    if DEFAULT_RUNSHEET_ID in ctx.pack.runsheets or previous is not None:
        return await create_session(ctx, previous.runsheet_id if previous else DEFAULT_RUNSHEET_ID, show_mode,
                                    assistant=assistant)
    return await create_session(ctx, "", show_mode, assistant=assistant, release_ids=demo_release_ids(ctx))


class ResetBody(BaseModel):
    assistant: bool = True  # D-139: False for the proof-plan §1 baseline replay
    show_mode: Literal["solo", "team"] | None = None  # None keeps the previous session's mode


@router.post("/demo/reset")
async def demo_reset(body: ResetBody | None = None, ctx: AppContext = Depends(demo_tools)) -> Session:
    body = body or ResetBody()
    s = await latest_session(ctx)
    show_mode = ctx.settings.DEFAULT_SHOW_MODE
    if s is not None:
        show_mode = s.show_mode  # a reset keeps the show mode and the show
        await ctx.runtimes.drop(s.session_id)
        await ctx.store.delete_session(s.session_id)
        ctx.bus.forget_session(s.session_id)
    return await _demo_show(ctx, body.show_mode or show_mode, body.assistant, s)


@router.post("/demo/sessions", status_code=201)
async def demo_session(body: ResetBody | None = None, ctx: AppContext = Depends(demo_tools)) -> Session:
    """D-139: a new session for a driver (voice rehearsal, show replay) that deletes nothing, so several
    drivers and the studio can share one service. Drivers end their session when they finish."""
    body = body or ResetBody()
    return await _demo_show(ctx, body.show_mode or ctx.settings.DEFAULT_SHOW_MODE, body.assistant)


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
