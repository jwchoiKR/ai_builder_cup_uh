"""Questions are not grouped by meaning: only a comment that repeats a member's own words joins a group."""
from __future__ import annotations

from app.providers.llm import MockBackend

from .helpers import live_runtime, make_ctx, say


async def test_only_the_very_same_words_join_a_group(tmp_path):
    ctx = make_ctx(backend=MockBackend(tmp_path), RECORD_ANSWERS=True)
    rt = await live_runtime(ctx)
    try:
        await say(rt, "Lee", "How much is the cream?")
        await say(rt, "Kumar", "how much is the cream?")  # the same words
        await say(rt, "Mei", "cream price?")  # the same question in other words: its own group and reply
        groups = await rt.groups()
        assert sorted(len(g.member_comment_ids) for g in groups) == [1, 2]
        assert all(g.status == "auto_answered" for g in groups)  # each asker is answered
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
