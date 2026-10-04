"""Per-second session tick: overtime once per segment, metrics every 5 s, TTL close (§8.1.5, §8.9.1, §8.16)."""
from __future__ import annotations

from app.models.session import Event

from .helpers import live_runtime, make_ctx, say


async def events(rt, type_: str) -> list[Event]:
    return [e for e in await rt.ctx.bus.events_after(rt.sid, 0) if e.type == type_]


async def test_overtime_once_and_metrics_every_5s(tmp_path):
    ctx = make_ctx(tmp_path)
    rt = await live_runtime(ctx)  # 5 s after start
    metrics = await events(rt, "metrics.updated")
    assert len(metrics) == 1 and "header" in metrics[0].payload
    await ctx.scheduler.advance(900_000)  # planned 900 s for the cream
    over = await events(rt, "segment.overtime")
    assert len(over) == 1 and over[0].payload["product_id"] == "cream_hydra_barrier"
    assert over[0].payload["overtime_sec"] >= 0
    await ctx.scheduler.advance(10_000)
    assert len(await events(rt, "segment.overtime")) == 1
    ctx.runtimes.shutdown()


async def test_simulate_overtime_and_group_ttl(tmp_path):
    ctx = make_ctx(tmp_path)
    rt = await live_runtime(ctx, "team")  # D-140: in a solo show the question waits on the host's list
    await rt.simulate_overtime()
    await ctx.scheduler.advance(1500)
    assert len(await events(rt, "segment.overtime")) == 1
    await say(rt, "Kumar", "Do you ship to Malaysia?")
    [g] = await rt.groups()
    assert g.status == "needs_review"
    await ctx.scheduler.advance(601_000)  # GROUP_TTL_SEC
    [g] = await rt.groups()
    assert g.status == "closed" and g.closed_reason == "ttl"
    ctx.runtimes.shutdown()


async def test_tick_stops_after_end(tmp_path):
    ctx = make_ctx(tmp_path)
    rt = await live_runtime(ctx)
    await rt.end()

    tick_types = {"metrics.updated", "segment.overtime", "hostqueue.updated", "group.updated"}

    async def non_summary() -> int:  # the summary pipeline (and its agent call) runs after end
        return len([e for e in await rt.ctx.bus.events_after(rt.sid, 0) if e.type in tick_types])

    n = await non_summary()
    await ctx.scheduler.advance(30_000)
    assert await non_summary() == n
