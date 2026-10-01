"""Record mock fixtures for the demo (DEV_SPEC §14.2).

Plays data/demo/host_script.md in real time against Vertex AI, in process: injected host lines
(STT injection), scripted bursts (no background chatter), the time sale and B5. Every agent output
is stored under tests/fixtures/llm/<agent>/ with the scene id as scenario tag.

The run is clean only if every agent call returned ok (no timeout, no invalid output) and the
summary recap is ready; otherwise the exit code is 1 and the run must be repeated, because a
failed call leaves no fixture and the mock replay would differ from the run.

    uv run python scripts/record_demo_fixtures.py [--until S11] [--report out.json]
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.context import build_context  # noqa: E402
from app.models.session import AgentCall  # noqa: E402
from app.pipelines.summary import _load as load_summary  # noqa: E402
from app.pipelines.demo_script import load_host_script  # noqa: E402
from app.pipelines.runtime import create_session  # noqa: E402
from app.providers.llm import RecordingBackend, VertexBackend  # noqa: E402

BURST_TAIL_MS = 1500


async def settle(ctx, extra_s: float = 0.0) -> None:
    if extra_s:
        await asyncio.sleep(extra_s)
    for _ in range(120):
        await ctx.scheduler.idle()
        if not [k for k in ctx.scheduler._timers if ":feed:" in k]:
            return
        await asyncio.sleep(0.5)


async def run(until: str | None, report: Path | None) -> int:
    settings = get_settings()
    inner = VertexBackend(settings.GCP_PROJECT, settings.LLM_LOCATION)
    backend = RecordingBackend(inner)
    ctx = build_context(settings, llm_backend=backend)
    await ctx.llm.warm_up()
    session = await create_session(ctx, "daon_skincare_demo")
    rt = await ctx.runtimes.get(session.session_id)
    steps = load_host_script(str(settings.data_path))
    for step in steps:
        if until and step.scene > until:
            break
        print(f"[{step.scene}] {step.who}: {step.action} {step.arg or ''} {step.text[:70] if step.action == 'host_line' else ''}")
        if step.action == "start":
            await rt.start()
            await asyncio.sleep(3)
        elif step.action == "burst":
            await rt.feed.fire(step.arg)
            burst = rt.feed.script["bursts"][rt.feed.resolve(step.arg)]
            await settle(ctx, max(c["offset_ms"] for c in burst["comments"]) / 1000 + BURST_TAIL_MS / 1000)
        elif step.action == "arm_burst":
            await rt.feed.fire(step.arg)
        elif step.action == "promo_start":
            await rt.start_promo(step.arg)
            await asyncio.sleep(1)
        elif step.action == "host_line":
            inject = getattr(rt, "inject_transcript", None)
            if inject is None:
                print("   (utterance pipeline not available yet: skipped)")
                continue
            await inject(step.text, scenario=step.scene)
            await settle(ctx, 6)
        elif step.action == "end":
            state = await rt.snapshot("operator")
            await rt.end()
            continue
        await settle(ctx)
    await settle(ctx, 2)
    ended = (await rt.load_session()).status != "live"
    if not ended:
        state = await rt.snapshot("operator")
    summary_status = None
    if ended:  # the recap runs in the background after end()
        for _ in range(120):
            doc = await load_summary(rt)
            summary_status = doc.status if doc else None
            if summary_status not in (None, "computing"):
                break
            await asyncio.sleep(0.5)
    calls = await ctx.store.query(rt.path("agent_calls"), AgentCall, order_by="started_at")
    failed = [c for c in calls if c.status != "ok"]
    print(f"\nrecorded {len(backend.recorded)} fixtures")
    counts = collections.Counter(f"{c.agent} {c.status}" for c in calls)
    print("agent calls:", ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    for c in failed:
        print(f"  FAILED {c.agent} {c.status} {c.error or ''} ({c.latency_ms} ms)")
    if ended:
        print("summary:", summary_status)
    clean = not failed and (not ended or summary_status == "ready")
    print("RUN CLEAN" if clean else "RUN NOT CLEAN: repeat the recording")
    for g in state["groups"]:
        ans = state["answers"].get(g["answer_id"] or "", {})
        print(f"- {g['status']:13} {g['route']:8} {len(g['unique_author_ids'])} asker(s) {g['product_id']} "
              f"{g['intent']}: {g['canonical_question']} -> {ans.get('text', '')[:90]!r} "
              f"{'' if ans.get('verified', True) else ans.get('verify_errors')}")
    for m in state["messages"]:
        print(f"  msg {m['state']} {m['kind']} -> {m['reply_to_author_names']}: {m['text'][:90]}")
    print("\nalerts:")
    for a in state.get("alerts", []):
        lat = (a["shown_at"] - next((t["speech_end_at"] for t in state.get("transcripts", [])
                                     if t["transcript_id"] == a["transcript_id"]), a["shown_at"])) if a["shown_at"] else None
        print(f"  {a['kind']:10} {a['status']:10} {a.get('rule_id') or a.get('field')} span={a.get('span')!r} "
              f"{a.get('stated_value') or ''}->{a.get('correct_value') or ''} unverified={a['unverified']} "
              f"shown_after={lat} ms corrected_by={a.get('corrected_text')!r}")
    print("\nsegments:")
    for seg in state["segments"]:
        print(f"  {seg['product_id']} {seg['start_reason']} covered={seg['covered_point_ids']} ended={seg['ended_at']}")
    print("pre_covered:", state["session"]["pre_covered"], "switch:", state["session"]["switch"]["status"])
    print("host slots:", [s["group_id"] for s in state["host_slots"]])
    if report:
        state["agent_calls"] = [c.model_dump(mode="json") for c in calls]
        report.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")
    ctx.runtimes.shutdown()
    ctx.scheduler.shutdown()
    await ctx.llm.aclose()
    return 0 if clean else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", help="last scene to play, e.g. S11")
    ap.add_argument("--report", type=Path)
    a = ap.parse_args()
    sys.exit(asyncio.run(run(a.until, a.report)))
