"""Operator actions (DEV_SPEC §8.13). All under /api/sessions/{sid}; each emits `operator.action`."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..context import AppContext, get_ctx
from ..pipelines import comments as ops
from ..pipelines import utterances as utt
from ..pipelines.runtime import ActionError, SessionRuntime

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


@router.post("/messages/{message_id}/cancel")
async def cancel_message(message_id: str, rt: SessionRuntime = Depends(runtime)) -> dict:
    await utt.cancel_message(rt, message_id)
    return OK


@router.post("/alerts/{alert_id}/dismiss")
async def dismiss_alert(alert_id: str, rt: SessionRuntime = Depends(runtime)) -> dict:
    await utt.dismiss_alert(rt, alert_id)
    return OK


@router.post("/alerts/{alert_id}/cue")
async def alert_cue(alert_id: str, rt: SessionRuntime = Depends(runtime)) -> dict:
    return (await utt.correction_cue(rt, alert_id)).model_dump()


@router.post("/alerts/{alert_id}/resend")
async def resend(alert_id: str, rt: SessionRuntime = Depends(runtime)) -> dict:
    await utt.resend_fact(rt, rt.utterances, alert_id)
    return OK


@router.get("/alerts/{alert_id}/notice-template")
async def notice_template(alert_id: str, rt: SessionRuntime = Depends(runtime)) -> dict:
    a = await utt._alert_or_404(rt, alert_id)
    return {"text": utt.notice_template(rt, a)}


class AlertNoticeBody(BaseModel):
    text: str = Field(min_length=1, max_length=400)


@router.post("/alerts/{alert_id}/notice")
async def alert_notice(alert_id: str, body: AlertNoticeBody, rt: SessionRuntime = Depends(runtime)) -> dict:
    return (await utt.post_notice(rt, alert_id, body.text)).model_dump()


@router.post("/alerts/{alert_id}/rendered")
async def rendered(alert_id: str, rt: SessionRuntime = Depends(runtime)) -> dict:
    await utt.render_ack(rt, alert_id)
    return OK


class CueBody(BaseModel):
    text: str | None = Field(default=None, max_length=200)
    preset_id: str | None = None


@router.post("/cues")
async def send_cue(body: CueBody, rt: SessionRuntime = Depends(runtime)) -> dict:
    return (await utt.send_cue(rt, body.text, body.preset_id)).model_dump()


@router.delete("/cues/{cue_id}")
async def clear_cue(cue_id: str, rt: SessionRuntime = Depends(runtime)) -> dict:
    await utt.clear_cue(rt, cue_id)
    return OK


class PdDismissBody(BaseModel):
    card_id: str


@router.post("/segments/extend")
async def extend(rt: SessionRuntime = Depends(runtime)) -> dict:
    """+2 min on the on-air segment: operator button or host key E (D-138)."""
    return (await rt.extend_segment()).model_dump()


@router.post("/pd/pull")
async def pd_pull(rt: SessionRuntime = Depends(runtime)) -> dict:
    """Host takes the top waiting question now (key Q): no time gap, no pause needed (D-113)."""
    rt.pd.pull()
    return {"ok": True}


@router.post("/pd/dismiss")
async def pd_dismiss(body: PdDismissBody, rt: SessionRuntime = Depends(runtime)) -> dict:
    """Host skips the AI PD card (key N); its topic is not offered again on this product."""
    card = await rt.pd.dismiss(body.card_id)
    if card is None:
        raise ActionError(409, "invalid_state", "no active AI PD card with this id")
    return card.model_dump()


class SwitchBody(BaseModel):
    product_id: str


@router.post("/segments/switch")
async def switch(body: SwitchBody, rt: SessionRuntime = Depends(runtime)) -> dict:
    return (await utt.operator_switch(rt, body.product_id)).model_dump()


@router.post("/segments/undo")
async def undo(rt: SessionRuntime = Depends(runtime)) -> dict:
    return (await utt.undo_switch(rt)).model_dump()


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
