"""Show replay eval (D-349): every live feature of one show, on the real UtterancePipeline. A show's ordered host lines
are replayed with their real gaps through ONE sequential session (a multi-release show, D-279), so switch state,
alerts, prompter coverage and holds carry from line to line, as on air.

Input: a JSONL file, one show per line:
    {"show_id": "S1", "release_ids": ["rel_a", "rel_b"],
     "lines": [{"id": "L1", "text": "...", "gap_ms": 1800, "expect": "stay", "labels": {...}},
               {"id": "L2", "text": "...", "gap_ms": 2400, "expect": "switch_to:2"}, ...]}
`gap_ms` is the pause before the line. `expect` is "stay" (default) or "switch_to:<n>" (n is 1-based in `release_ids`,
or a release id). `labels` is optional and copied to the output untouched, for the scorer.

    uv run python scripts/eval_show.py --cases shows.jsonl --mode immediate --out ../results/show_immediate
    uv run python scripts/eval_show.py --cases shows.jsonl --mode two_step --arm-name off --out ...

Output: <out>/<show_id>.json per show and <out>/summary.md. Times are ms on the session clock; `line_end` is the line's
final, and each `ms_*` is from it. Per show:
- `lines`: id, text, labels, expect, transcript id, line end, the release on air when it was said, the context judge's
  verdict on it (covered_point_ids, covered_cue_ids, switch verdict, reason) and its model calls (status, failure,
  latency, usage).
- `switch_events`: decided (with the judge's reason and confidence), counting, pending, cancelled, committed, undone.
- `alerts`: kind, rule or field, severity, release it was checked against, provisional reflex chip, shown, escalated,
  resolved (corrected or cleared, and by which line), and for the qualifier rule the 10 s re-say prompt.
- `prompter`: every coverage update with the required points left, attributed to the line said just before.
- `chips`: question holds (hold.started/ended) and "checking" (verify.started/done, provisional alerts).
- `judge`: failures and health changes; `calls`: every model call with usage.
- `timeline`: the live events above in order, as emitted.
- `switch_score`: caught switches with latency, false switches (see `switch_score`).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_holdout_sequences import ReplayClock  # noqa: E402

from app.config import Settings  # noqa: E402
from app.context import build_context  # noqa: E402
from app.logic.qualifier import RULE_ID as QUALIFIER  # noqa: E402
from app.models.session import AgentCall, Event, Segment, Transcript  # noqa: E402
from app.pipelines.runtime import create_session  # noqa: E402
from app.scheduler import AsyncScheduler  # noqa: E402

SWITCH_EVENTS = {"segment.switch_decided": "decided", "segment.switch_counting": "counting",
                 "segment.switch_pending": "pending", "segment.switch_cancelled": "cancelled",
                 "segment.started": "committed", "segment.undone": "undone"}
LIVE_EVENTS = {*SWITCH_EVENTS, "transcript.final", "alert.created", "alert.updated", "alert.escalated",
               "prompter.updated", "cue.updated", "segment.missing_points", "segment.overtime", "hold.started",
               "hold.ended", "verify.started", "verify.done", "verify.health", "judge.failed", "judge.health",
               "line.check"}
QUALIFIER_RESAY_MS = 10_000  # the host screen's QUALIFIER_ADDON_MS (D-341): after it, the host must say the result again
JUDGES = ("compliance_judge", "context_judge", "fact_checker", "utterance_judge", "judge_single", "verifier")
SETTINGS_LOGGED = ("STORE", "FIRESTORE_DATABASE", "SWITCH_MODE", "SWITCH_ARM_NAME", "SWITCH_DUAL_SCOPE_SEC",
                   "JUDGE_ARM", "JUDGE_MODE", "FACT_PROMPT", "COMPLIANCE_RESAY", "CORRECTION_CHECK", "REFLEX_SCAN",
                   "JUDGE_PRODUCTS", "QUESTION_HOLD", "COMPLIANCE_ESCALATE_SEC")


def _target(show: dict, expect: str) -> str | None:
    """The release id an expect names ("switch_to:2" or "switch_to:<release id>"); None for "stay"."""
    if not expect.startswith("switch_to:"):
        return None
    ref = expect.split(":", 1)[1]
    return show["release_ids"][int(ref) - 1] if ref.isdigit() else ref


def _line_of_text(lines: list[dict], preview: str) -> str | None:
    """The line a model call judged (its input preview holds the line's text; a merged utterance names its last)."""
    hits = [x["id"] for x in lines if x["text"].strip() and x["text"].strip()[:80] in preview]
    return hits[-1] if hits else None


async def run_show(ctx, show: dict, settle_ms: int) -> dict:
    s = await create_session(ctx, "", release_ids=show["release_ids"])
    rt = await ctx.runtimes.get(s.session_id)
    rt.pd.agent = None  # the utterance pipeline only
    try:
        await rt.start()
        release_of = dict(rt.pack.releases)  # product id -> release id
        lines = []
        for line in show["lines"]:
            await asyncio.sleep(line.get("gap_ms", 0) / 1000)
            on_air = (await rt.current_segment()).product_id
            t = await rt.utterances.submit(line["text"], source="injected", speech_end_at=rt.now(), scenario="eval")
            lines.append({"id": line["id"], "text": line["text"], "expect": line.get("expect", "stay"),
                          "labels": line.get("labels"), "gap_ms": line.get("gap_ms", 0),
                          "transcript_id": t.transcript_id, "line_end": t.speech_end_at or t.received_at,
                          "on_air_release": release_of.get(on_air)})
        await asyncio.sleep(settle_ms / 1000)  # a pending switch, an escalation or a held question resolves
        await rt.utterances.drain()
        return await _collect(rt, show, lines, release_of)
    finally:
        await ctx.runtimes.drop(rt.sid)


async def _collect(rt, show: dict, lines: list[dict], release_of: dict) -> dict:
    store = rt.ctx.store
    evs = await store.query(rt.path("events"), Event, order_by="seq")
    # every transcript is one replayed line; a merged utterance is judged under its last line's id, and the line it
    # joined is recorded on that line (`merged_with`)
    line_of = {x["transcript_id"]: x["id"] for x in lines}
    end_of = {x["id"]: x["line_end"] for x in lines}
    for t in await store.query(rt.path("transcripts"), Transcript):
        if t.transcript_id in line_of and t.merged_from_transcript_id:
            next(x for x in lines if x["transcript_id"] == t.transcript_id)["merged_with"] = line_of.get(
                t.merged_from_transcript_id)
    merged_line = line_of.get

    def said_before(at: int) -> str | None:
        prior = [x for x in lines if x["line_end"] <= at]
        return prior[-1]["id"] if prior else None

    def ms(line: str | None, at: int | None) -> int | None:
        return at - end_of[line] if line in end_of and at is not None else None

    timeline, switch, prompter, chips, judge = [], [], [], [], []
    for e in evs:
        if e.type not in LIVE_EVENTS:
            continue
        p = e.payload or {}
        tid = p.get("transcript_id")
        line = merged_line(tid) if tid else None
        timeline.append({"seq": e.seq, "at": e.at, "type": e.type, "line": line, "transcript_id": tid,
                         "payload": p})
        if e.type in SWITCH_EVENTS and not (e.type == "segment.started" and p.get("start_reason") == "session_start"):
            row = {"event": SWITCH_EVENTS[e.type], "at": e.at, "transcript_id": tid, "line": line,
                   "ms_from_line": ms(line, e.at)}
            if e.type == "segment.started":
                row |= {"release": release_of.get(p["product_id"]), "reason": p.get("start_reason"),
                        "after_line": said_before(e.at)}
            elif e.type == "segment.switch_decided":
                row |= {k: p.get(k) for k in ("switch", "target_product_id", "confidence", "is_quote",
                                               "utterance_type", "reason")}
            elif e.type in ("segment.switch_counting", "segment.switch_pending"):
                row |= {"target_product_id": p.get("target_product_id"), "cue_count": p.get("cue_count")}
            elif e.type == "segment.switch_cancelled":
                row["reason"] = p.get("reason")
            elif e.type == "segment.undone":
                row["after_line"] = said_before(e.at)
            switch.append(row)
        elif e.type == "prompter.updated":
            after = said_before(e.at)
            prompter.append({"at": e.at, "after_line": after, "ms_from_line": ms(after, e.at),
                             "release": release_of.get(p.get("product_id")),
                             "covered_point_ids": p.get("covered_point_ids"),
                             "required_left": (p.get("required_total") or 0) - (p.get("required_covered") or 0)})
        elif e.type in ("hold.started", "hold.ended", "verify.started", "verify.done", "line.check"):
            chips.append({"event": e.type, "at": e.at, "line": line, "ms_from_line": ms(line, e.at)}
                         | {k: v for k, v in p.items() if k != "transcript_id"})
        elif e.type in ("judge.failed", "judge.health", "verify.health"):
            judge.append({"event": e.type, "at": e.at, "line": line, "ms_from_line": ms(line, e.at)}
                         | {k: v for k, v in p.items() if k != "transcript_id"})

    alerts = []
    for a in sorted(await rt.alerts(), key=lambda a: a.created_at):
        line = merged_line(a.transcript_id)
        resolved_by = merged_line(a.corrected_by_transcript_id) if a.corrected_by_transcript_id else None
        row = {"alert_id": a.alert_id, "line": line, "transcript_id": a.transcript_id, "kind": a.kind,
               "rule_id": a.rule_id, "field": a.field, "severity": a.severity,
               "checked_against": release_of.get(a.product_id), "status": a.status, "span": a.span,
               "say_instead": a.say_instead, "stated_value": a.stated_value, "correct_value": a.correct_value,
               "unverified": a.unverified, "resolved_by_line": resolved_by,
               "ms_to_provisional": ms(line, a.provisional_at), "ms_to_shown": ms(line, a.shown_at),
               "ms_to_escalated": ms(line, a.escalated_at), "ms_to_resolved": ms(line, a.resolved_at)}
        if a.rule_id == QUALIFIER and a.shown_at is not None:
            # the host's banner asks to say the result again once the late add-on window is over (D-341)
            resay = a.created_at + QUALIFIER_RESAY_MS
            row["qualifier"] = {"shown": True, "ms_to_resay_prompt": (ms(line, resay) if a.resolved_at is None
                                                                      or a.resolved_at > resay else None),
                                "cleared": a.status in ("corrected", "cleared")}
        alerts.append(row)
    for a in alerts:  # D-306/"checking": a provisional reflex chip that never became an alert
        if a["ms_to_provisional"] is not None and a["ms_to_shown"] is None:
            chips.append({"event": "provisional_only", "line": a["line"], "rule_id": a["rule_id"],
                          "ms_from_line": a["ms_to_provisional"], "status": a["status"]})

    calls = sorted(await store.query(rt.path("agent_calls"), AgentCall), key=lambda c: c.started_at)
    call_rows = [{"agent": c.agent, "line": _line_of_text(lines, c.input_preview), "status": c.status,
                  "failure": c.failure, "latency_ms": c.latency_ms, "usage": c.usage, "model": c.model,
                  "started_at": c.started_at} for c in calls if c.agent in JUDGES]
    for x in lines:
        ctx_calls = [c for c in calls if c.agent in ("context_judge", "utterance_judge")
                     and _line_of_text(lines, c.input_preview) == x["id"] and c.output]
        if ctx_calls:
            out = ctx_calls[-1].output
            pr = out.get("prompter") or {}
            x["context"] = {"covered_point_ids": pr.get("covered_point_ids"), "covered_cue_ids": pr.get("covered_cue_ids"),
                            "switch": pr.get("switch"), "utterance_type": (out.get("answer") or {}).get("utterance_type"),
                            "reason": out.get("reason")}
        x["calls"] = [{k: c[k] for k in ("agent", "status", "failure", "latency_ms", "usage")}
                      for c in call_rows if c["line"] == x["id"]]
    segments = sorted(await store.query(rt.path("segments"), Segment), key=lambda x: x.started_at)
    raw = {"show_id": show["show_id"], "release_ids": show["release_ids"], "session_id": rt.sid,
           "settings": {k: getattr(rt.ctx.settings, k, None) for k in SETTINGS_LOGGED},  # the effective ones
           "lines": lines, "switch_events": switch, "alerts": alerts, "prompter": prompter, "chips": chips,
           "judge": judge, "calls": call_rows, "timeline": timeline,
           "segments": [{"release": release_of.get(x.product_id), "started_at": x.started_at, "ended_at": x.ended_at,
                         "reason": x.start_reason, "covered_point_ids": x.covered_point_ids} for x in segments]}
    raw["switch_score"] = switch_score(raw, show)
    return raw


def switch_score(raw: dict, show: dict) -> dict:
    """An expected switch is caught when the show commits to that release after its line's final and before the next
    expected switch's line; latency is commit time minus the line's final. Any other commit is a false switch (an
    early one counts as a false switch and a miss). The same rule in both modes."""
    commits = [e for e in raw["switch_events"] if e["event"] == "committed"]
    expected = [(x, _target(show, x["expect"])) for x in raw["lines"] if _target(show, x["expect"])]
    used, rows = set(), []
    for i, (line, rel) in enumerate(expected):
        until = expected[i + 1][0]["line_end"] if i + 1 < len(expected) else float("inf")
        hit = next((j for j, c in enumerate(commits) if j not in used and c["release"] == rel
                    and line["line_end"] <= c["at"] < until), None)
        if hit is not None:
            used.add(hit)
        rows.append({"line": line["id"], "to": rel, "caught": hit is not None,
                     "latency_ms": commits[hit]["at"] - line["line_end"] if hit is not None else None})
    false = [{"at": c["at"], "to": c["release"], "reason": c["reason"], "after_line": c.get("after_line")}
             for j, c in enumerate(commits) if j not in used]
    return {"expected": rows, "false_switches": false}


def write_summary(shows: list[dict], out: Path) -> str:
    exp = [r for s in shows for r in s["switch_score"]["expected"]]
    lat = sorted(r["latency_ms"] for r in exp if r["caught"])
    false = sum(len(s["switch_score"]["false_switches"]) for s in shows)
    p95 = lat[min(len(lat) - 1, int(0.95 * len(lat)))] if lat else None
    head = (f"switches caught {len(lat)}/{len(exp)}, false switches {false}"
            + (f", latency mean {sum(lat) / len(lat) / 1000:.1f} s p95 {p95 / 1000:.1f} s" if lat else ""))
    st = shows[0]["settings"] if shows else {}
    md = ["# Show replay", "", ", ".join(f"{k}={v}" for k, v in st.items()), "", head, "",
          "| Show | Lines | Alerts shown | Escalated | Resolved | Holds | Judge failures | Calls failed |",
          "|---|---|---|---|---|---|---|---|"]
    for s in shows:
        al = s["alerts"]
        md.append(f"| {s['show_id']} | {len(s['lines'])} | {sum(a['ms_to_shown'] is not None for a in al)} | "
                  f"{sum(a['ms_to_escalated'] is not None for a in al)} | {sum(a['ms_to_resolved'] is not None for a in al)} | "
                  f"{sum(c['event'] == 'hold.started' for c in s['chips'])} | "
                  f"{sum(j['event'] == 'judge.failed' for j in s['judge'])} | "
                  f"{sum(c['status'] != 'ok' for c in s['calls'])} |")
    md += ["", "| Show | Line | To | Caught | Latency (s) |", "|---|---|---|---|---|"]
    for s in shows:
        for r in s["switch_score"]["expected"]:
            md.append(f"| {s['show_id']} | {r['line']} | {r['to']} | {'yes' if r['caught'] else 'no'} | "
                      f"{'' if r['latency_ms'] is None else round(r['latency_ms'] / 1000, 1)} |")
        for f in s["switch_score"]["false_switches"]:
            md.append(f"| {s['show_id']} | false switch after {f['after_line']} | {f['to']} | | ({f['reason']}) |")
    (out / "summary.md").write_text("\n".join(md) + "\n", encoding="utf-8", newline="\n")
    return head


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=Path, required=True, help="JSONL, one show per line")
    ap.add_argument("--mode", choices=("two_step", "immediate"), default=None, help="SWITCH_MODE (default: settings)")
    ap.add_argument("--arm-name", choices=("on", "off"), default=None, help="SWITCH_ARM_NAME, two_step only")
    ap.add_argument("--settle-ms", type=int, default=8000, help="wait after the last line before reading events")
    ap.add_argument("--out", type=Path, required=True, help="output directory: <show_id>.json per show, summary.md")
    args = ap.parse_args()
    shows = [json.loads(x) for x in args.cases.read_text(encoding="utf-8").splitlines() if x.strip()]
    over = {"LLM_PROVIDER": "vertex", "STT_PROVIDER": "mock", "RETRIEVER": "local"}
    if not os.environ.get("STORE"):  # STORE from the environment when set (firestore needs GCP_PROJECT); else memory
        over["STORE"] = "memory"
    if args.mode:
        over["SWITCH_MODE"] = args.mode
    if args.arm_name:
        over["SWITCH_ARM_NAME"] = args.arm_name == "on"
    settings = Settings(**over)
    clock = ReplayClock()
    ctx = build_context(settings, clock=clock, scheduler=AsyncScheduler(clock))
    args.out.mkdir(parents=True, exist_ok=True)
    done = []
    try:
        await ctx.llm.warm_up()
        for show in shows:  # one show at a time: parallel shows cause judge timeouts
            raw = await run_show(ctx, show, args.settle_ms)
            (args.out / f"{show['show_id']}.json").write_text(json.dumps(raw, ensure_ascii=False) + "\n",
                                                              encoding="utf-8", newline="\n")
            done.append(raw)
            print(f"show {show['show_id']} done", flush=True)
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
        if hasattr(ctx.store, "aclose"):  # STORE=firestore: the queued writes go out before the exit
            await ctx.store.aclose(30.0)
        await ctx.llm.aclose()
    print(write_summary(done, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
