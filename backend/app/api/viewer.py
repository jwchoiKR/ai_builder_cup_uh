"""Viewer endpoints (DEV_SPEC §11.1, §12.5)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..context import AppContext, get_ctx
from ..models.session import Comment
from ..pipelines.comments import submit_comment
from .errors import ApiError

router = APIRouter()


class CommentBody(BaseModel):
    author_id: str = Field(min_length=1, max_length=64)
    author_name: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=2000)


@router.post("/sessions/{session_id}/comments", status_code=201)
async def post_comment(session_id: str, body: CommentBody, ctx: AppContext = Depends(get_ctx)) -> Comment:
    if not ctx.settings.VIEWER_INPUT_ENABLED:
        raise ApiError(403, "viewer_input_disabled", "Chat is read-only in this demo.")
    rt = await ctx.runtimes.get(session_id)
    return await submit_comment(rt, author_id=body.author_id, author_name=body.author_name, text=body.text,
                                source="viewer")
