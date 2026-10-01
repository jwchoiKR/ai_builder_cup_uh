"""Session endpoints (DEV_SPEC §8.1, §11.1)."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..context import AppContext, get_ctx
from ..logic.catalog import DEFAULT_RUNSHEET_ID
from ..models.session import Session
from ..pipelines.runtime import create_session as _create
from ..store.base import SESSIONS
from .errors import ApiError

router = APIRouter()

Role = Literal["operator", "host", "viewer"]


class CreateSessionBody(BaseModel):
    runsheet_id: str = DEFAULT_RUNSHEET_ID


@router.post("/sessions", status_code=201)
async def create_session(body: CreateSessionBody | None = None, ctx: AppContext = Depends(get_ctx)) -> Session:
    return await _create(ctx, (body or CreateSessionBody()).runsheet_id)


@router.post("/sessions/{session_id}/start")
async def start_session(session_id: str, ctx: AppContext = Depends(get_ctx)) -> Session:
    return await (await ctx.runtimes.get(session_id)).start()


@router.post("/sessions/{session_id}/end")
async def end_session(session_id: str, ctx: AppContext = Depends(get_ctx)) -> Session:
    return await (await ctx.runtimes.get(session_id)).end()


@router.get("/sessions/{session_id}/state")
async def session_state(session_id: str, role: Role = "viewer", ctx: AppContext = Depends(get_ctx)) -> dict:
    return await (await ctx.runtimes.get(session_id)).snapshot(role)


@router.get("/sessions/{session_id}/metrics")
async def session_metrics(session_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    return await (await ctx.runtimes.get(session_id)).compute_metrics()


async def require_session(session_id: str, ctx: AppContext) -> Session:
    session = await ctx.store.get(SESSIONS, session_id, Session)
    if session is None:
        raise ApiError(404, "session_not_found", f"session {session_id} not found")
    return session
