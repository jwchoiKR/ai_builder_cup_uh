"""D-337 (review A2/A3, E6): a release show has no demo chatter (starting it was a 500); "New demo session" uses
/api/demo/sessions (an empty POST /api/sessions now 404s: no shipped run-sheet)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.pipelines.feed import FeedEngine

from .helpers import live_runtime, make_ctx, make_settings
from .judge_fakes import close_env


async def test_d337_a_show_without_demo_chatter_does_not_start_it():
    rt = await live_runtime(make_ctx())
    try:
        feed = FeedEngine(rt, demo=False)
        feed.start_pool()  # was KeyError 'min_gap_ms'
        assert feed.state()["pool_available"] is False and feed.pool_running is False
        assert FeedEngine(rt, demo=True).state()["pool_available"] is True
    finally:
        await close_env(rt)


def test_d337_a_new_demo_session():
    with TestClient(create_app(make_settings())) as c:
        r = c.post("/api/demo/sessions", json={"show_mode": "solo"})
        assert r.status_code == 201 and r.json()["status"] == "ready"
