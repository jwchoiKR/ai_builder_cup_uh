"""Real-model probe: a few STT finals through the production runtime, with each final's fact-check claims.

For tracing a missed alert from a sealed replay without sharing the finals: put them in a local JSON file

    {"product_id": "cream_hydra_barrier", "promo_id": "promo_time_sale_10",
     "finals": [{"text": "So the cream,", "gap_ms": 1500}, {"text": "It's $36, very cheap."}]}

    uv run python scripts/probe_finals.py case.json [--runs 3]

and read, per final, what the fact checker said (product, field, stated value, verdict) and which alerts came.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_holdout_sequences import ReplayClock, feed_turns  # noqa: E402

from app.config import Settings  # noqa: E402
from app.context import build_context  # noqa: E402
from app.pipelines.runtime import create_session  # noqa: E402
from app.pipelines.utterances import operator_switch  # noqa: E402
from app.scheduler import AsyncScheduler  # noqa: E402


async def run_once(ctx, case: dict) -> None:
    s = await create_session(ctx, next(iter(ctx.pack.runsheets)))
    rt = await ctx.runtimes.get(s.session_id)
    rt.pd.agent = None
    await rt.start()
    if case.get("product_id") and (await rt.current_segment()).product_id != case["product_id"]:
        await operator_switch(rt, case["product_id"])
    if case.get("promo_id"):
        await rt.start_promo(case["promo_id"])
    facts: dict[str, list] = {}
    apply = rt.utterances._apply_facts_locked

    async def capture(t, out, protected):
        facts[t.transcript_id] = [(c.product_id, c.field, c.stated_value, c.verdict, c.correct_value) for c in out.claims]
        return await apply(t, out, protected)

    rt.utterances._apply_facts_locked = capture
    ts = await feed_turns(rt, [{"utterance": f["text"], "gap_ms": f.get("gap_ms", 1500)} for f in case["finals"]])
    alerts = await rt.alerts()
    for t in ts:
        print(f"  {t.text!r}" + (f"  [judged as {t.judged_text!r}]" if t.judged_text else ""))
        for c in facts.get(t.transcript_id, []):
            print(f"      fact: product={c[0]} field={c[1]} stated={c[2]!r} verdict={c[3]} correct={c[4]!r}")
        for a in alerts:
            if a.transcript_id == t.transcript_id:
                print(f"      alert: {a.kind} {a.rule_id or ''} {a.severity} {a.status}")


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("case", type=Path)
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()
    case = json.loads(args.case.read_text(encoding="utf-8"))
    settings = Settings(LLM_PROVIDER="vertex", STT_PROVIDER="mock", STORE="memory", RETRIEVER="local",
                        JUDGE_MODE="split3")
    clock = ReplayClock()
    ctx = build_context(settings, clock=clock, scheduler=AsyncScheduler(clock))
    try:
        await ctx.llm.warm_up()
        for run in range(args.runs):
            print(f"run {run + 1}")
            await run_once(ctx, case)
        print("second requests (D-184):", ctx.llm.hedges or "none")
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
        await ctx.llm.aclose()


if __name__ == "__main__":
    asyncio.run(main())
