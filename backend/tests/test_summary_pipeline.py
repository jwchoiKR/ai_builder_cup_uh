"""Summary pipeline and GET /sessions/{sid}/summary (DEV_SPEC §8.1.4, §8.14, §11.1)."""
from __future__ import annotations

import httpx

from app.api import summary as summary_api
from app.main import create_app
from app.models.session import Event
from app.pipelines.summary import SummaryDoc, get_summary, run_summary
from app.providers.llm import LLMError

from .helpers import live_runtime, make_ctx, say


async def _events(rt, type_: str) -> list[Event]:
    return [e for e in await rt.ctx.bus.events_after(rt.sid, 0) if e.type == type_]


async def finish(rt) -> None:
    """End the session and let the summary run (the runtime starts it on end; else start it here)."""
    await rt.end()
    await finish_after_end(rt)


async def finish_after_end(rt) -> None:
    await rt.ctx.scheduler.idle()
    if not await _events(rt, "summary.ready"):
        await run_summary(rt)


async def test_run_summary_stores_stats_and_recap(tmp_path):
    ctx = make_ctx(tmp_path)
    rt = await live_runtime(ctx)
    await say(rt, "Lee", "How much is the cream?")
    await say(rt, "Kumar", "Do you ship to Malaysia?")
    await rt.inject_transcript("It's a lightweight gel-cream, so it absorbs really quickly.")
    await ctx.scheduler.advance(3000)
    before = await get_summary(rt)
    assert before["status"] == "not_ended" and before["recap"] is None
    await finish(rt)
    doc = await ctx.store.get(rt.path("summary"), "current", SummaryDoc)
    assert doc is not None and doc.status == "ready"
    stats = doc.stats
    assert stats["totals"]["comments"] == 2 and stats["totals"]["questions"] == 2
    cream = stats["products"][0]
    assert cream["product_id"] == "cream_hydra_barrier" and cream["required_points_total"] == 3
    assert any(g["canonical_question"] for g in stats["general_unanswered_groups"])  # shipping question
    assert set(doc.recap) == {"headline", "highlights", "watch_outs", "follow_ups"}
    assert [e.payload for e in await _events(rt, "summary.ready")] == [{"status": "ready"}]
    got = await get_summary(rt)
    assert got["status"] == "ready" and got["stats"] == stats and got["recap"] == doc.recap
    ctx.runtimes.shutdown()


async def test_agent_failure_keeps_stats_without_recap():
    class Failing:
        name = "failing"

        async def generate(self, req, timeout_ms):
            raise LLMError("boom")

        async def warm_up(self, model, timeout_ms):
            return None

        async def aclose(self):
            return None

    ctx = make_ctx(backend=Failing())
    rt = await live_runtime(ctx)
    await finish(rt)
    got = await get_summary(rt)
    assert got["status"] == "failed" and got["recap"] is None and "recap unavailable" in got["error"]
    assert got["stats"]["title"] == "DAON LAB · Skincare session"
    ctx.runtimes.shutdown()


async def test_get_summary_after_end_without_doc_starts_the_recap(tmp_path):
    ctx = make_ctx(tmp_path)
    rt = await live_runtime(ctx)
    await finish(rt)
    await ctx.store.delete(rt.path("summary"), "current")  # e.g. after a restart: no stored summary
    first = await get_summary(rt)
    assert first["status"] == "computing" and first["stats"]["products"]
    await ctx.scheduler.idle()
    assert (await get_summary(rt))["status"] == "ready"
    ctx.runtimes.shutdown()


async def test_summary_route(tmp_path):
    from app.clock import ManualClock
    from app.providers.llm import MockBackend
    from app.scheduler import ManualScheduler

    from .conftest import make_settings

    clock = ManualClock()
    scheduler = ManualScheduler(clock)
    app = create_app(make_settings(), clock=clock, scheduler=scheduler, llm_backend=MockBackend(tmp_path))
    if not any(getattr(r, "path", "") == "/api/sessions/{session_id}/summary" for r in app.routes):
        # Until main.py registers the router: put it ahead of the SPA catch-all route.
        from fastapi import APIRouter

        extra = APIRouter()
        extra.include_router(summary_api.router, prefix="/api")
        app.router.routes[0:0] = extra.routes
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api") as c:
        sid = (await c.post("/sessions")).json()["session_id"]
        await c.post(f"/sessions/{sid}/start")
        await scheduler.advance(5000)
        r = await c.get(f"/sessions/{sid}/summary")
        assert r.status_code == 200 and r.json()["status"] == "not_ended"
        await c.post(f"/sessions/{sid}/end")
        await finish_after_end(await app.state.ctx.runtimes.get(sid))
        body = (await c.get(f"/sessions/{sid}/summary")).json()
        assert body["status"] == "ready" and body["recap"]["headline"]
        assert (await c.get("/sessions/ses_missing/summary")).status_code == 404
    app.state.ctx.runtimes.shutdown()
    scheduler.shutdown()
