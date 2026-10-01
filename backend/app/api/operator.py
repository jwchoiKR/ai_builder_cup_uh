"""Operator actions (DEV_SPEC §8.13). All under /api/sessions/{sid}; each emits `operator.action`."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..context import AppContext, get_ctx
from ..pipelines import comments as ops
from ..pipelines.runtime import SessionRuntime

router = APIRouter(prefix="/sessions/{session_id}")


async def runtime(session_id: str, ctx: AppContext = Depends(get_ctx)) -> SessionRuntime:
    return await ctx.runtimes.get(session_id)


OK = {"ok": True}


@router.post("/groups/{group_id}/push")
async def push(group_id: str, rt: SessionRuntime = Depends(runtime)) -> dict:
    await ops.push_to_host(rt, group_id)
    return OK


@router.post("/groups/{group_id}/recall")
async def recall(group_id: str, rt: SessionRuntime = Depends(runtime)) -> dict:
    await ops.recall_from_host(rt, group_id)
    return OK


class AssignBody(BaseModel):
    product_id: str


@router.post("/groups/{group_id}/assign-product")
async def assign_product(group_id: str, body: AssignBody, rt: SessionRuntime = Depends(runtime)) -> dict:
    await ops.assign_product(rt, group_id, body.product_id)
    return OK


@router.post("/groups/{group_id}/approve")
async def approve(group_id: str, rt: SessionRuntime = Depends(runtime)) -> dict:
    await ops.approve(rt, group_id)
    return OK


class AnswerBody(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    origin: Literal["operator_edit", "operator_written"]
    confirm: bool = False


@router.post("/groups/{group_id}/answer")
async def answer(group_id: str, body: AnswerBody, rt: SessionRuntime = Depends(runtime)) -> dict:
    await ops.write_answer(rt, group_id, body.text, body.origin, body.confirm)
    return OK


@router.post("/groups/{group_id}/post-suggested")
async def post_suggested(group_id: str, rt: SessionRuntime = Depends(runtime)) -> dict:
    await ops.post_suggested(rt, group_id)
    return OK


@router.post("/groups/{group_id}/reject")
async def reject(group_id: str, rt: SessionRuntime = Depends(runtime)) -> dict:
    await ops.reject(rt, group_id)
    return OK


@router.post("/comments/{comment_id}/unhide")
async def unhide(comment_id: str, rt: SessionRuntime = Depends(runtime)) -> dict:
    await ops.unhide_comment(rt, comment_id)
    return OK


@router.post("/promos/{promo_id}/start")
async def start_promo(promo_id: str, rt: SessionRuntime = Depends(runtime)) -> dict:
    await rt.start_promo(promo_id)
    await ops.operator_action(rt, "promo_start", promo_id=promo_id)
    return OK


@router.post("/promos/{promo_id}/stop")
async def stop_promo(promo_id: str, rt: SessionRuntime = Depends(runtime)) -> dict:
    await rt.stop_promo(promo_id)
    await ops.operator_action(rt, "promo_stop", promo_id=promo_id)
    return OK


class NoticeBody(BaseModel):
    text: str = Field(min_length=1, max_length=300)


@router.post("/notices")
async def pin_notice(body: NoticeBody, rt: SessionRuntime = Depends(runtime)) -> dict:
    await rt.set_notice(body.text)
    await ops.operator_action(rt, "pin_notice")
    return OK


@router.delete("/notices")
async def unpin_notice(rt: SessionRuntime = Depends(runtime)) -> dict:
    await rt.set_notice(None)
    await ops.operator_action(rt, "unpin_notice")
    return OK
