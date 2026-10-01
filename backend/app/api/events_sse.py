"""SSE stream of session events (DEV_SPEC §11.2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse

from ..bus import sse_stream
from ..context import AppContext, get_ctx
from .sessions import require_session

router = APIRouter()


@router.get("/sessions/{session_id}/events")
async def session_events(
    session_id: str,
    after_seq: int = 0,
    last_event_id: str | None = Header(default=None),
    ctx: AppContext = Depends(get_ctx),
) -> StreamingResponse:
    await require_session(session_id, ctx)
    # On reconnect the browser sends Last-Event-ID; it wins over the query parameter.
    start = int(last_event_id) if last_event_id and last_event_id.strip().isdigit() else after_seq
    return StreamingResponse(
        sse_stream(ctx.bus, session_id, max(0, start), heartbeat_sec=ctx.sse_heartbeat_sec),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
