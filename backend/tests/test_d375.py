"""D-375 (user): the DAON demo show (its onboarded releases) has the demo feed, and the Demo Console's "Send sample
questions" burst posts viewer questions through the normal comment pipeline: three common questions asked several
ways group for the host's Top 3. Mock LLM (the keyword triage fallback, so only the price group forms here)."""
from __future__ import annotations

import shutil
from pathlib import Path

from app.onboarding.demo import demo_release_ids
from app.pipelines.runtime import create_session

from .helpers import make_ctx

DATA = Path(__file__).resolve().parents[2] / "data"  # the shipped data (the test pack has its own demo scripts)


async def test_d375_the_demo_show_has_the_feed_and_the_sample_questions_group(tmp_path):
    shutil.copytree(DATA, tmp_path / "data")
    ctx = make_ctx(DATA_DIR=str(tmp_path / "data"), ONBOARDING_DIR=str(tmp_path / "onb"))
    s = await create_session(ctx, "", release_ids=demo_release_ids(ctx))
    rt = await ctx.runtimes.get(s.session_id)
    try:
        await rt.start()
        await ctx.scheduler.advance(5000)
        state = rt.feed.state()
        assert state["pool_available"] and "B6_sample_questions" in [b["burst_id"] for b in state["bursts"]]
        await rt.feed.fire("B6")
        await ctx.scheduler.advance(40_000)
        from app.models.session import Comment

        comments = await ctx.store.query(rt.path("comments"), Comment)
        assert len(comments) == 13
        groups = await rt.groups()
        assert sum(len(g.member_comment_ids) for g in groups) == 13  # every question reached a group
        # the mock's keyword triage groups the four price questions; the live triage model groups the other two
        # common questions by meaning (sensitive skin, use with the ampoule)
        assert max(len(g.member_comment_ids) for g in groups) == 4
        [ship] = [g for g in groups if g.intent == "shipping"]
        assert ship.route == "OPERATOR"  # the product info does not answer it
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
