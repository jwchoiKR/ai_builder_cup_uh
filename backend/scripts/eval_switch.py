"""Product-switch eval (D-349) on the real UtterancePipeline: one show's ordered host lines, replayed with their real
gaps through ONE sequential session (a multi-release show, D-279), so the switch state carries from line to line.

Input: a JSONL file, one show per line:
    {"show_id": "S1", "release_ids": ["rel_a", "rel_b"],
     "lines": [{"id": "L1", "text": "...", "gap_ms": 1800, "expect": "stay"},
               {"id": "L2", "text": "...", "gap_ms": 2400, "expect": "switch_to:2"}, ...]}
`gap_ms` is the pause before the line (after the previous line ended). `expect` is "stay" or "switch_to:<n>", where n
is a 1-based position in `release_ids` (a release id also works): the line where the host moves to that product.

    uv run python scripts/eval_switch.py --cases shows.jsonl --mode immediate --out ../results/switch_immediate
    uv run python scripts/eval_switch.py --cases shows.jsonl --mode two_step --arm-name off --out ...

Output: <out>.json (per show: every line with its transcript id and times, every switch event in order (decided,
counting, pending, cancelled, committed, undone) with its time and transcript id, and every alert) and <out>.md.

Scoring, per show: an expected switch is caught when the show commits to that product after the line was heard and
before the next expected switch's line; its latency is commit time minus the line's final. Any other commit is a
false switch (an early one counts as a false switch and a miss). The same rule in both modes.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_holdout_sequences import ReplayClock  # noqa: E402

from app.config import Settings  # noqa: E402
from app.context import build_context  # noqa: E402
from app.models.session import Event, Segment  # noqa: E402
from app.pipelines.runtime import create_session  # noqa: E402
from app.scheduler import AsyncScheduler  # noqa: E402

SWITCH_EVENTS = {"segment.switch_decided": "decided", "segment.switch_counting": "counting",
                 "segment.switch_pending": "pending", "segment.switch_cancelled": "cancelled",
                 "segment.started": "committed", "segment.undone": "undone"}


def _target(show: dict, expect: str) -> str | None:
    """The release id an expect names ("switch_to:2" or "switch_to:<release id>"); None for "stay"."""
    if not expect.startswith("switch_to:"):
        return None
    ref = expect.split(":", 1)[1]
    return show["release_ids"][int(ref) - 1] if ref.isdigit() else ref


async def run_show(ctx, show: dict, settle_ms: int) -> dict:
    s = await create_session(ctx, "", release_ids=show["release_ids"])
    rt = await ctx.runtimes.get(s.session_id)
    rt.pd.agent = None  # the utterance pipeline only
    release_of = {}
    try:
        await rt.start()
        release_of = dict(rt.pack.releases)  # product id -> release id
        lines = []
        for line in show["lines"]:
            await asyncio.sleep(line.get("gap_ms", 0) / 1000)
            on_air = (await rt.current_segment()).product_id
            t = await rt.utterances.submit(line["text"], source="injected", speech_end_at=rt.now(), scenario="eval")
            lines.append({"id": line["id"], "text": line["text"], "expect": line.get("expect", "stay"),
                          "transcript_id": t.transcript_id, "heard_at": t.received_at,
                          "on_air_release": release_of.get(on_air)})
        await asyncio.sleep(settle_ms / 1000)  # a pending two-step switch commits after its countdown
        await rt.utterances.drain()
        evs = await rt.ctx.store.query(rt.path("events"), Event, order_by="seq")
        line_of = {x["transcript_id"]: x["id"] for x in lines}
        switch = []
        for e in evs:
            if e.type not in SWITCH_EVENTS or (e.type == "segment.started" and e.payload.get("start_reason") == "session_start"):
                continue
            p = e.payload
            tid = p.get("transcript_id")
            row = {"event": SWITCH_EVENTS[e.type], "at": e.at, "transcript_id": tid, "line": line_of.get(tid)}
            if e.type == "segment.started":
                row |= {"release": release_of.get(p["product_id"]), "reason": p.get("start_reason")}
            elif e.type == "segment.switch_decided":
                row |= {k: p.get(k) for k in ("switch", "target_product_id", "confidence", "is_quote",
                                               "utterance_type", "reason")}
            elif e.type in ("segment.switch_counting", "segment.switch_pending"):
                row |= {"target_product_id": p.get("target_product_id"), "cue_count": p.get("cue_count")}
            elif e.type == "segment.switch_cancelled":
                row["reason"] = p.get("reason")
            switch.append(row)
        heard = {x["transcript_id"]: x["heard_at"] for x in lines}
        alerts = [{"line": line_of.get(a.transcript_id), "transcript_id": a.transcript_id, "kind": a.kind,
                   "release": release_of.get(a.product_id), "rule_id": a.rule_id, "severity": a.severity,
                   "field": a.field, "span": a.span, "say_instead": a.say_instead,
                   "stated_value": a.stated_value, "correct_value": a.correct_value, "status": a.status,
                   "ms_to_shown": a.shown_at - heard[a.transcript_id] if a.transcript_id in heard else None}
                  for a in await rt.alerts() if a.shown_at is not None]
        segments = sorted(await rt.ctx.store.query(rt.path("segments"), Segment), key=lambda x: x.started_at)
        return {"show_id": show["show_id"], "release_ids": show["release_ids"], "lines": lines, "switch_events": switch,
                "alerts": alerts, "segments": [{"release": release_of.get(x.product_id), "started_at": x.started_at,
                                                "ended_at": x.ended_at, "reason": x.start_reason} for x in segments]}
    finally:
        await ctx.runtimes.drop(rt.sid)


def score(raw: dict, show: dict) -> dict:
    commits = [e for e in raw["switch_events"] if e["event"] == "committed"]
    expected = [(x, _target(show, x["expect"])) for x in raw["lines"] if _target(show, x["expect"])]
    used, rows = set(), []
    for i, (line, rel) in enumerate(expected):
        until = expected[i + 1][0]["heard_at"] if i + 1 < len(expected) else float("inf")
        hit = next((j for j, c in enumerate(commits) if j not in used and c["release"] == rel
                    and line["heard_at"] <= c["at"] < until), None)
        if hit is not None:
            used.add(hit)
        rows.append({"line": line["id"], "to": rel, "caught": hit is not None,
                     "latency_ms": commits[hit]["at"] - line["heard_at"] if hit is not None else None})
    false = [{"at": c["at"], "to": c["release"], "reason": c["reason"]} for j, c in enumerate(commits) if j not in used]
    return {"show_id": raw["show_id"], "expected": rows, "false_switches": false}


def write_report(scores: list[dict], out: Path, mode: str, arm_name: bool) -> str:
    exp = [r for s in scores for r in s["expected"]]
    caught = [r for r in exp if r["caught"]]
    lat = sorted(r["latency_ms"] for r in caught)
    false = sum(len(s["false_switches"]) for s in scores)
    p95 = lat[min(len(lat) - 1, int(0.95 * len(lat)))] if lat else None
    head = (f"switches caught {len(caught)}/{len(exp)}, false switches {false}, latency mean "
            f"{sum(lat) / len(lat) / 1000:.1f} s p95 {p95 / 1000:.1f} s" if lat else
            f"switches caught 0/{len(exp)}, false switches {false}")
    md = [f"# Switch eval: SWITCH_MODE={mode}, SWITCH_ARM_NAME={'on' if arm_name else 'off'}", "", head, "",
          "| Show | Line | To | Caught | Latency (s) |", "|---|---|---|---|---|"]
    for s in scores:
        for r in s["expected"]:
            md.append(f"| {s['show_id']} | {r['line']} | {r['to']} | {'yes' if r['caught'] else 'no'} | "
                      f"{'' if r['latency_ms'] is None else round(r['latency_ms'] / 1000, 1)} |")
        for f in s["false_switches"]:
            md.append(f"| {s['show_id']} | false switch | {f['to']} | | ({f['reason']}) |")
    out.with_suffix(".md").write_text("\n".join(md) + "\n", encoding="utf-8", newline="\n")
    return head


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=Path, required=True, help="JSONL, one show per line")
    ap.add_argument("--mode", choices=("two_step", "immediate"), default=None, help="SWITCH_MODE (default: settings)")
    ap.add_argument("--arm-name", choices=("on", "off"), default=None, help="SWITCH_ARM_NAME, two_step only")
    ap.add_argument("--settle-ms", type=int, default=8000, help="wait after the last line before reading events")
    ap.add_argument("--out", type=Path, required=True, help="output path without suffix (.json and .md)")
    args = ap.parse_args()
    shows = [json.loads(x) for x in args.cases.read_text(encoding="utf-8").splitlines() if x.strip()]
    over = {"LLM_PROVIDER": "vertex", "STT_PROVIDER": "mock", "STORE": "memory", "RETRIEVER": "local"}
    if args.mode:
        over["SWITCH_MODE"] = args.mode
    if args.arm_name:
        over["SWITCH_ARM_NAME"] = args.arm_name == "on"
    settings = Settings(**over)
    clock = ReplayClock()
    ctx = build_context(settings, clock=clock, scheduler=AsyncScheduler(clock))
    raw = []
    try:
        await ctx.llm.warm_up()
        for show in shows:  # one show at a time: parallel shows cause judge timeouts
            raw.append(await run_show(ctx, show, args.settle_ms))
            print(f"show {show['show_id']} done", flush=True)
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
        await ctx.llm.aclose()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    scores = [score(r, s) for r, s in zip(raw, shows)]
    args.out.with_suffix(".json").write_text(
        json.dumps({"settings": {"SWITCH_MODE": settings.SWITCH_MODE, "SWITCH_ARM_NAME": settings.SWITCH_ARM_NAME,
                                 "SWITCH_DUAL_SCOPE_SEC": settings.SWITCH_DUAL_SCOPE_SEC},
                    "shows": raw, "scores": scores}, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(write_report(scores, args.out, settings.SWITCH_MODE, settings.SWITCH_ARM_NAME))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
