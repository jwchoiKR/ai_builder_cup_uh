"""D-477: the live viewer count. Per process: distinct viewer ids with an open viewer stream (or one closed less than
10 s ago), plus a demo's simulated viewers from their first comment to the end of the show."""
from __future__ import annotations

from fastapi import Response

from app.api.sessions import session_audience
from app.bus import AUDIENCE_GRACE_MS, sse_stream
from app.pipelines.comments import submit_comment

from .judge_fakes import ScriptedBackend, close_env
from .test_d462 import show


async def _open(bus, viewer_id=None, role="viewer"):
    gen = sse_stream(bus, "ses_a", after_seq=0, heartbeat_sec=10, role=role, viewer_id=viewer_id)
    assert await gen.__anext__() == "retry: 1000\n\n"  # the stream is open
    return gen


async def test_one_browser_counts_once_and_stays_counted_through_a_refresh(bus, clock):
    tab1, tab2 = await _open(bus, "v_1"), await _open(bus, "v_1")
    assert bus.audience("ses_a") == {"v_1"}
    await tab1.aclose()
    assert bus.audience("ses_a") == {"v_1"}  # the other tab is still open
    await tab2.aclose()
    clock.advance(AUDIENCE_GRACE_MS - 1)
    assert bus.audience("ses_a") == {"v_1"}  # a refresh or reconnect must not flicker the number
    clock.advance(1)
    assert bus.audience("ses_a") == set()


async def test_streams_without_a_viewer_id_or_of_other_roles_are_not_counted(bus):
    gens = [await _open(bus), await _open(bus, "v_host", role="host"), await _open(bus, "v_op", role="operator")]
    assert bus.audience("ses_a") == set()
    for g in gens:
        await g.aclose()


async def test_forget_session_clears_the_count(bus):
    gen = await _open(bus, "v_1")
    bus.forget_session("ses_a")
    assert bus.audience("ses_a") == set()
    await gen.aclose()
    assert bus.audience("ses_a") == set()


async def test_demo_viewers_count_from_their_first_comment_to_the_end_of_the_show():
    rt = await show(ScriptedBackend())
    ctx = rt.ctx
    try:
        for name, text in [("Amy", "hi"), ("Ben", "price?"), ("Amy", "love it")]:
            await submit_comment(rt, author_id=f"u_{name.lower()}", author_name=name, text=text, source="script")
        # a real viewer's typed comment does not count beyond their stream
        await submit_comment(rt, author_id="v_typed", author_name="Kim", text="hello", source="viewer")
        gen = sse_stream(ctx.bus, rt.sid, after_seq=0, heartbeat_sec=10, role="viewer", viewer_id="v_watch")
        await gen.__anext__()
        response = Response()
        body = await session_audience(rt.sid, response, ctx)
        assert body["count"] == 3  # Amy, Ben and the watching viewer
        assert response.headers["Cache-Control"] == "no-store"
        await rt.end()
        assert (await session_audience(rt.sid, Response(), ctx))["count"] == 1  # ended: only the open stream
        await gen.aclose()
    finally:
        await close_env(rt)
