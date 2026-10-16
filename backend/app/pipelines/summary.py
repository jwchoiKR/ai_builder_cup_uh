"""Post-broadcast summary (DEV_SPEC §8.1.4, §8.14, §7.8).

`run_summary(rt)` runs in the background after `End broadcast`: statistics are computed by code
and stored at once (status "computing"), then the BroadcastSummary agent writes the recap. When
the agent fails, the page shows the statistics without a recap (§7.2).
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

from ..agents.broadcast_summary import BroadcastSummary, SummaryInput
from ..logic.summary_stats import compute_summary_stats
from ..models.session import AgentCall, Comment, CommentAnalysis, Message, Transcript
from .comment_insights import run_comment_insights

if TYPE_CHECKING:
    from .runtime import SessionRuntime

log = logging.getLogger(__name__)

DOC_ID = "current"


class SummaryDoc(BaseModel):  # [sessions/{sid}/summary/current]
    status: Literal["computing", "ready", "failed"]
    stats: dict[str, Any]
    recap: dict[str, Any] | None = None
    # what viewers asked: topics, outcomes and notes from the stored comment documents (pipelines/comment_insights)
    comment_insights: dict[str, Any] | None = None
    error: str | None = None
    created_at: int
    updated_at: int


async def compute_stats(rt: "SessionRuntime") -> dict[str, Any]:
    store = rt.ctx.store
    return compute_summary_stats(
        session=await rt.load_session(),
        segments=await rt.segments(),
        catalog=rt.catalog,
        comments=await store.query(rt.path("comments"), Comment),
        analyses=await store.query(rt.path("analyses"), CommentAnalysis),
        groups=await rt.groups(),
        messages=await store.query(rt.path("messages"), Message),
        alerts=await rt.alerts(),
        transcripts=await store.query(rt.path("transcripts"), Transcript),
        events=await rt.ctx.bus.events_after(rt.sid, 0),
        agent_calls=await store.query(rt.path("agent_calls"), AgentCall),
        counters=dict(rt.counters),
        triage_hits=rt.triage_cache.hits,
        triage_misses=rt.triage_cache.misses,
        now=rt.now(),
    )


async def _load(rt: "SessionRuntime") -> SummaryDoc | None:
    return await rt.ctx.store.get(rt.path("summary"), DOC_ID, SummaryDoc)


async def _save(rt: "SessionRuntime", doc: SummaryDoc) -> None:
    await rt.ctx.store.put(rt.path("summary"), DOC_ID, doc)


async def run_summary(rt: "SessionRuntime", *, scenario: str = "S14") -> None:
    """Statistics first (stored at once), then the recap. Never raises."""
    try:
        now = rt.now()
        stats = await compute_stats(rt)
        doc = SummaryDoc(status="computing", stats=stats, created_at=now, updated_at=now)
        await _save(rt, doc)
        agent = BroadcastSummary(rt.ctx.llm, rt.ctx.prompts["broadcast_summary"])
        # the recap and the comment analysis are independent: both at once
        res, doc.comment_insights = await asyncio.gather(
            agent.run(SummaryInput(stats=stats, session_id=rt.sid, scenario=scenario),
                      deadline_ms=rt.settings.SUMMARY_TIMEOUT_MS),
            run_comment_insights(rt, scenario=scenario))
        doc.updated_at = rt.now()
        if res.status == "ok" and res.output is not None:
            doc.status, doc.recap = "ready", res.output.model_dump(mode="json")
        else:
            doc.status, doc.error = "failed", f"recap unavailable ({res.status}): {res.error or ''}".strip()
        await _save(rt, doc)
        await rt.emit("summary.ready", {"status": doc.status})
        after = rt.settings.SESSION_EVICT_AFTER_SEC
        if after > 0 and hasattr(rt.ctx.store, "evict"):
            # the show is over and written down: it leaves memory later and is read back from Firestore when opened
            sid, ctx = rt.sid, rt.ctx
            ctx.scheduler.call_later(f"evict:{sid}", after * 1000, lambda: ctx.runtimes.evict(sid))
    except Exception:  # noqa: BLE001 - the summary must never break the session end
        log.exception("summary failed for %s", rt.sid)
        try:
            await rt.emit("summary.ready", {"status": "failed"})
        except Exception:  # noqa: BLE001
            pass


async def get_summary(rt: "SessionRuntime") -> dict[str, Any]:
    """GET /summary: the stored summary; while live, current statistics without recap."""
    doc = await _load(rt)
    if doc is not None:
        return {"status": doc.status, "stats": doc.stats, "recap": doc.recap, "error": doc.error,
                "comment_insights": doc.comment_insights}
    session = await rt.load_session()
    stats = await compute_stats(rt)
    if session.status == "ended":
        # Ended but not summarised yet (e.g. after a restart): store the stats and write the recap.
        now = rt.now()
        await _save(rt, SummaryDoc(status="computing", stats=stats, created_at=now, updated_at=now))
        rt.spawn(run_summary(rt), name=f"summary:{rt.sid}")
        return {"status": "computing", "stats": stats, "recap": None, "error": None, "comment_insights": None}
    return {"status": "not_ended", "stats": stats, "recap": None, "error": None, "comment_insights": None}


async def retry_summary(rt: "SessionRuntime") -> str:
    """D-498 (user: "add a retry button"): write the recap again, only when the last try failed; a summary
    being written or ready is left alone (no second run). Returns the status. 409 before the show has ended."""
    from .runtime import ActionError

    async with rt.lock:  # two presses at once start one run
        if (await rt.load_session()).status != "ended":
            raise ActionError(409, "not_ended", "the show has not ended yet")
        doc = await _load(rt)
        if doc is not None and doc.status != "failed":
            return doc.status
        now = rt.now()
        stats = doc.stats if doc is not None else await compute_stats(rt)
        await _save(rt, SummaryDoc(status="computing", stats=stats, created_at=doc.created_at if doc else now,
                                   updated_at=now))
    log.info("summary %s: retry", rt.sid)
    rt.spawn(run_summary(rt), name=f"summary:{rt.sid}")
    return "computing"
