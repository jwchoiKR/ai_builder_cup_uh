"""Session endpoints (DEV_SPEC §8.1, §11.1)."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from ..context import AppContext, get_ctx
from ..logic.catalog import DEFAULT_RUNSHEET_ID
from ..models.session import Comment, Session
from ..pipelines.runtime import create_session as _create
from ..store.base import SESSIONS, sub
from .errors import ApiError

router = APIRouter()

Role = Literal["operator", "host", "viewer"]


class CreateSessionBody(BaseModel):
    runsheet_id: str = DEFAULT_RUNSHEET_ID
    show_mode: Literal["solo", "team"] | None = None  # D-111; None: DEFAULT_SHOW_MODE
    market: str | None = None  # D-142: default MARKET; the market must offer the language
    lang: str | None = None  # D-142: default BROADCAST_LANGUAGE
    release_id: str | None = None  # D-218: an onboarded product's release instead of the run sheet
    release_ids: list[str] | None = None  # D-279: 2-3 releases in segment order, equal time each


@router.post("/sessions", status_code=201)
async def create_session(body: CreateSessionBody | None = None, ctx: AppContext = Depends(get_ctx)) -> Session:
    body = body or CreateSessionBody()
    return await _create(ctx, body.runsheet_id, body.show_mode or ctx.settings.DEFAULT_SHOW_MODE, market=body.market,
                         lang=body.lang,
                         release_id=body.release_id, release_ids=body.release_ids)


@router.post("/sessions/{session_id}/start")
async def start_session(session_id: str, ctx: AppContext = Depends(get_ctx)) -> Session:
    return await (await ctx.runtimes.get(session_id)).start()


@router.post("/sessions/{session_id}/end")
async def end_session(session_id: str, ctx: AppContext = Depends(get_ctx)) -> Session:
    return await (await ctx.runtimes.get(session_id)).end()


@router.get("/sessions/{session_id}/state")
async def session_state(session_id: str, role: Role = "viewer", ctx: AppContext = Depends(get_ctx)) -> dict:
    return await (await ctx.runtimes.get(session_id)).snapshot(role)


DEMO_SOURCES = ("script", "pool")


@router.get("/sessions/{session_id}/audience")
async def session_audience(session_id: str, response: Response, ctx: AppContext = Depends(get_ctx)) -> dict:
    """D-477: how many are watching. Per process: the distinct viewer ids with a live stream on this instance (the
    one that runs the show and sends its live chat; another instance's viewers are not seen), plus, in a demo, each
    simulated viewer from their first comment to the end of the show."""
    session = await require_session(session_id, ctx)
    ids = ctx.bus.audience(session_id)
    if session.status != "ended":
        comments = await ctx.store.query(sub(session_id, "comments"), Comment)
        ids |= {c.author_id for c in comments if c.source in DEMO_SOURCES}
    response.headers["Cache-Control"] = "no-store"
    return {"count": len(ids), "at": ctx.clock.now_ms()}


@router.get("/sessions/{session_id}/metrics")
async def session_metrics(session_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    return await (await ctx.runtimes.get(session_id)).compute_metrics()


async def require_session(session_id: str, ctx: AppContext) -> Session:
    session = await ctx.store.get(SESSIONS, session_id, Session)
    if session is None:
        raise ApiError(404, "session_not_found", f"session {session_id} not found")
    return session
