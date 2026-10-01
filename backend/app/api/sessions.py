"""Session endpoints (DEV_SPEC §8.1, §11.1). P0: create. Start/end and /state come with P1/P2."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..context import AppContext, get_ctx
from ..logic.catalog import DEFAULT_RUNSHEET_ID, DataPackError
from ..models.session import Session
from ..store.base import SESSIONS
from .errors import ApiError

router = APIRouter()


class CreateSessionBody(BaseModel):
    runsheet_id: str = DEFAULT_RUNSHEET_ID


@router.post("/sessions", status_code=201)
async def create_session(body: CreateSessionBody | None = None, ctx: AppContext = Depends(get_ctx)) -> Session:
    body = body or CreateSessionBody()
    try:
        runsheet = ctx.pack.runsheet(body.runsheet_id)
    except DataPackError as e:
        raise ApiError(404, "unknown_runsheet", str(e)) from None
    session_id = ctx.ids.new("ses_")
    session = Session(
        session_id=session_id,
        runsheet_id=runsheet.runsheet_id,
        title=runsheet.title,
        status="ready",
        settings_snapshot=ctx.settings.snapshot(),
        created_at=ctx.clock.now_ms(),
    )
    await ctx.store.put(SESSIONS, session_id, session)
    return session


async def require_session(session_id: str, ctx: AppContext) -> Session:
    session = await ctx.store.get(SESSIONS, session_id, Session)
    if session is None:
        raise ApiError(404, "session_not_found", f"session {session_id} not found")
    return session
