"""Real-model holdout finals through the production runtime.

uv run python scripts/eval_holdout_sequences.py --runs 1
uv run python scripts/eval_holdout_sequences.py --from-json ../docs/eval/holdout-sequences.json

gap_ms is the delay AFTER this final, before the next final (including a final
tail observation window). A wall-time-driven test clock preserves overlapping
inference and production timers. Speech-end is injection time: STT and browser
rendering are outside the measured latency.
"""
from __future__ import annotations

import argparse
import asyncio
import contextvars
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.clock import ManualClock
from app.config import REPO_DIR, Settings
from app.context import build_context
from app.models.session import Answer, Event
from app.pipelines.runtime import create_session
from app.pipelines.utterances import operator_switch
from app.scheduler import AsyncScheduler
from eval_expectations import expectation_checks
from eval_common import _group, _same_value, latency_line, load_cases


class ReplayClock(ManualClock):
    """Test epoch, advancing with monotonic elapsed time while models run."""

    def __init__(self, start_ms: int = 1_790_000_000_000):
        super().__init__(start_ms)
        self._origin = time.monotonic()

    def now_ms(self) -> int:
        return self._now + int((time.monotonic() - self._origin) * 1000)


async def feed_turns(rt, turns: list[dict]) -> list:
    """Never drain between finals: inference can extend across several gaps."""
    transcripts = []
    for turn in turns:
        gap = turn.get("gap_ms", 0)
        if not isinstance(gap, int) or gap < 0:
            raise ValueError(f"gap_ms must be a nonnegative integer: {gap!r}")
        transcripts.append(await rt.utterances.submit(turn["utterance"], source="injected",
                                                    speech_end_at=rt.now(), scenario="eval"))
        await asyncio.sleep(gap / 1000)
    await rt.utterances.drain()
    return transcripts


def alert_latencies(events: list[dict], transcript_id: str, speech_end_at: int) -> list[dict]:
    """First active visibility per alert; provisional/dismissed chips are not red alerts.

    Use event timestamps so a later correction cannot erase the original latency.
    None timestamps fall back to event time; zero is a valid timestamp.
    """
    found = {}
    for event in events:
        a = event["payload"]
        if event["type"] not in ("alert.created", "alert.updated") or a.get("transcript_id") != transcript_id:
            continue
        if a.get("status") != "active" or a["alert_id"] in found:
            continue
        shown = a.get("shown_at")
        shown = event["at"] if shown is None else shown
        if shown < speech_end_at:
            raise ValueError("Alert shown before its transcript speech end")
        found[a["alert_id"]] = {"alert_id": a["alert_id"], "kind": a["kind"],
                                "rule_id": a.get("rule_id"), "field": a.get("field"),
                                "speech_end_to_alert_ms": shown - speech_end_at}
    return list(found.values())


def runtime_effects(events, transcript_id, latency, judge, state, publish_effect):
    """Convert committed per-turn effects to the common scorer's output shape."""
    active_ids = {a["alert_id"] for a in latency}
    active_by_id = {}
    for event in events:
        a = event["payload"]
        if (event["type"].startswith("alert.") and a.get("alert_id") in active_ids
                and a.get("transcript_id") == transcript_id and a.get("status") == "active"):
            active_by_id.setdefault(a["alert_id"], a)
    active = list(active_by_id.values())
    corrected = {e["payload"]["alert_id"] for e in events if e["type"] == "alert.updated"
                 and e["payload"].get("status") == "corrected"
                 and e["payload"].get("corrected_by_transcript_id") == transcript_id}
    effective = {**judge, "compliance": {"violations": [
        {"rule_id": a.get("rule_id"), "severity": a.get("severity")}
        for a in active if a["kind"] == "compliance"]},
        "correction": {"corrects_alert_ids": sorted(corrected)}}
    facts = {"claims": [{"verdict": "contradicted", "field": a.get("field"),
                         "correct_value": a.get("correct_value")}
                        for a in active if a["kind"] == "fact"]}
    covered = {p for s in state.get("segments", []) for p in s["covered_point_ids"]}
    covered.update(p for points in state.get("pre_covered", {}).values() for p in points)
    sw = dict((judge.get("prompter") or {}).get("switch") or {})
    if sw.get("is_transition") and not sw.get("is_quote"):
        before, after = state.get("switch_before", {}), state.get("switch", {})
        target = sw.get("target_product_id")
        committed = any(s["product_id"] == target and s.get("ended_at") is None
                        for s in state.get("segments", []))
        counted = after.get("target_product_id") == target and after.get("cue_count", 0) > before.get("cue_count", 0)
        cancelled = before.get("status") in ("counting", "pending") and after.get("status") == "idle" and committed
        sw["is_transition"] = bool(counted or cancelled)
    accepted = covered & set((judge.get("prompter") or {}).get("covered_point_ids", []))
    effective["prompter"] = {**(judge.get("prompter") or {}), "covered_point_ids": sorted(accepted), "switch": sw}
    # The matched read-out label is a model context signal. Whether an answer
    # was actually linked is always a runtime effect, including negative labels.
    effective["answer"] = {**(judge.get("answer") or {}), "is_answer": bool(publish_effect)}
    if publish_effect:
        effective["answer"]["matched_group_id"] = publish_effect[0]
    return effective, facts


async def run_sequence(ctx, sequence: dict, run_no: int) -> dict:
    session = await create_session(ctx, next(iter(ctx.pack.runsheets)))
    rt = await ctx.runtimes.get(session.session_id)
    if hasattr(rt, "pd"):
        rt.pd.agent = None  # This evaluation isolates the utterance pipeline.
    await rt.start()
    if (await rt.current_segment()).product_id != sequence["current_product_id"]:
        await operator_switch(rt, sequence["current_product_id"])
    initial = sequence.get("initial_context") or {}
    if initial.get("active_promo_id"):
        await rt.start_promo(initial["active_promo_id"])
    symbols = {}
    for q in initial.get("open_questions", []):
        gid = rt.new_id("grp_")
        symbols[q["group_id"]] = gid
        group = _group({**q, "group_id": gid, "product_id": q.get("product_id", sequence["current_product_id"]),
                        "intent": q.get("intent", "suitability")}, rt.now())
        if q.get("suggested_answer"):
            aid = rt.new_id("ans_")
            await rt.save_answer(Answer(answer_id=aid, group_id=gid, text=q["suggested_answer"], citations=[],
                                       origin="operator_written", verified=True, verify_errors=[],
                                       needs_human=False, created_at=rt.now()))
            group.answer_id = aid
        await rt.save_group(group)
    await rt.recompute_host_queue_locked()
    observations = {}
    current = contextvars.ContextVar("eval_transcript", default=None)
    original_infer = rt.utterances._infer

    async def infer(t, *args, **kwargs):
        token = current.set(t.transcript_id)
        observations.setdefault(t.transcript_id, {})
        try:
            return await original_infer(t, *args, **kwargs)
        finally:
            current.reset(token)

    rt.utterances._infer = infer
    for name in ("compliance", "context", "judge", "facts"):
        agent = getattr(rt.utterances, name)
        original = agent.run

        async def capture(*args, _name=name, _original=original, **kwargs):
            result = await _original(*args, **kwargs)
            tid = current.get()
            if tid:
                observations[tid][_name] = {"status": result.status, "ms": result.latency_ms,
                                           "usage": result.meta.get("usage"),
                                           "output": result.output.model_dump(mode="json") if result.output else None}
            return result

        agent.run = capture
    original_context = rt.utterances._apply_context_locked

    async def apply_context(t, verdict, merge):
        before = (await rt.load_session()).switch.model_dump(mode="json")
        await original_context(t, verdict, merge)
        session_state = await rt.load_session()
        observations.setdefault(t.transcript_id, {})["state_after_context"] = {
            "switch_before": before, "switch": session_state.switch.model_dump(mode="json"),
            "pre_covered": session_state.pre_covered,
            "segments": [s.model_dump(mode="json") for s in await rt.segments()]}

    rt.utterances._apply_context_locked = apply_context
    original_publish = rt.utterances._publish_locked

    async def publish(t, *args, **kwargs):
        await original_publish(t, *args, **kwargs)
        judged = rt.utterances._judged.get(t.transcript_id)
        observations.setdefault(t.transcript_id, {})["publish_effect"] = judged.publish if judged else None

    rt.utterances._publish_locked = publish
    try:
        transcripts = await feed_turns(rt, sequence["turns"])
        events = [e.model_dump(mode="json") for e in await ctx.store.query(rt.path("events"), Event, order_by="seq")]
        # Dataset aliases al_sXX name that sequence's compliance alert. Bind by
        # expected rule + originating final, never by generated-ID order.
        positives = [(t, turn["expected"]) for t, turn in zip(transcripts, sequence["turns"])
                     if turn["expected"].get("compliance") is True]
        aliases = {a for turn in sequence["turns"] for a in turn["expected"].get("corrects_alert_ids", [])}
        if len(aliases) > 1 or (aliases and len(positives) != 1):
            raise ValueError("Ambiguous symbolic compliance alert mapping")
        for alias in aliases:
            t, exp = positives[0]
            matches = {e["payload"]["alert_id"] for e in events if e["type"].startswith("alert.")
                       and e["payload"].get("transcript_id") == t.transcript_id
                       and e["payload"].get("rule_id") == exp["rule_id"]}
            if len(matches) == 1:
                symbols[alias] = next(iter(matches))
        rows = []
        for index, (t, turn) in enumerate(zip(transcripts, sequence["turns"]), 1):
            ob = observations.get(t.transcript_id, {})
            comp = ob.get("compliance", ob.get("judge", {}))
            context = ob.get("context", ob.get("judge", {}))
            facts = ob.get("facts", {})
            judge = {**(comp.get("output") or {}), **(context.get("output") or {})}
            state = ob.get("state_after_context", {})
            before, after = state.get("switch_before", {}), state.get("switch", {})
            target = before.get("target_product_id")
            continuation = bool(target and (after.get("cue_count", 0) > before.get("cue_count", 0)
                                or any(s["product_id"] == target and s.get("ended_at") is None for s in state.get("segments", []))))
            # Once a switch committed, continued speech belongs to the current
            # target segment. A continuation must not introduce a new transition.
            if not target and index > 1:
                earlier_targets = [p["expected"].get("target") for p in sequence["turns"][:index - 1]
                                   if p["expected"].get("switch") is True]
                if earlier_targets:
                    continuation = any(s["product_id"] == earlier_targets[-1] and s.get("ended_at") is None
                                       for s in state.get("segments", []))
            latency = alert_latencies(events, t.transcript_id, t.speech_end_at)
            # Score server effects, not claims the pipeline rejected. Keep model
            # outputs separately in observations for diagnosing disagreements.
            effective, effect_facts = runtime_effects(events, t.transcript_id, latency, judge, state,
                                                     ob.get("publish_effect"))
            checks = expectation_checks(turn["expected"], effective, effect_facts, _same_value,
                                        ids=symbols, continuation=continuation)
            statuses = {"comp": comp.get("status", "error"), "ctx": context.get("status", "error"),
                        "facts": facts.get("status", "error")}
            # Deterministic reflex/correction reconciliation can produce a
            # successful runtime effect despite a failed model call. Negative
            # checks still require an answered agent, never empty defaults.
            runtime_checks = []
            for area, name, ok, detail in checks:
                status = statuses[area]
                positive_effect = ((area == "comp" and name in ("correction", "catches the violation (right rule)"))
                                   or (area == "facts" and name == "catches the wrong fact"))
                runtime_checks.append({"area": area, "check": name,
                                       "status": "ok" if ok and positive_effect else status,
                                       "ok": ok if status == "ok" or (ok and positive_effect) else None,
                                       "detail": detail})
            rows.append({"turn": index, "transcript_id": t.transcript_id, "speech_end_at": t.speech_end_at,
                         "expected": turn["expected"], "observations": ob, "alerts": latency,
                         "checks": runtime_checks})
        return {"seq_id": sequence["seq_id"], "run": run_no, "symbols": symbols, "turns": rows, "events": events}
    finally:
        await ctx.runtimes.drop(rt.sid)


def write_report(raw: list[dict], out: Path) -> None:
    turns = [t for seq in raw for t in seq["turns"]]
    checks = [c for t in turns for c in t["checks"]]
    latency = [a["speech_end_to_alert_ms"] for t in turns for a in t["alerts"]]
    lines = ["# Holdout sequences", "", f"{len(raw)} sequence runs; {len(turns)} turns.",
             "Gaps follow each final; inference overlaps. Each verdict is scored against that turn's labels.",
             "State is captured after each turn's ordered context application, before later context applies.",
             "Supported/none facts require no contradicted note. Missing agent results count as failures/timeouts.",
             "Compliance, fact notes, corrections, coverage and answer links are scored from runtime effects; raw model outputs remain in JSON.",
             "Read-out group matching and answer consistency are model context labels. AI PD model calls are disabled in this utterance evaluation.",
             f"Speech-end (injected final) to first active server alert: {latency_line(latency)}.",
             "STT and browser rendering are excluded. Provisional chips are excluded; later resolution preserves latency.",
             "", "| Sequence | Turn | Correct | Wrong | Non-ok | Alert ms |", "|---|---|---|---|---|---|"]
    for seq in raw:
        for turn in seq["turns"]:
            cs = turn["checks"]
            lines.append(f"| {seq['seq_id']} run {seq['run'] + 1} | {turn['turn']} | "
                         f"{sum(c['ok'] is True for c in cs)} | {sum(c['ok'] is False for c in cs)} | "
                         f"{sum(c['ok'] is None for c in cs)} | "
                         f"{', '.join(str(a['speech_end_to_alert_ms']) for a in turn['alerts']) or 'none'} |")
    lines += ["", f"Checks: {sum(c['ok'] is True for c in checks)} correct; "
              f"{sum(c['ok'] is False for c in checks)} wrong; {sum(c['ok'] is None for c in checks)} non-ok."]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps(raw, ensure_ascii=False) + "\n", encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--out", type=Path, default=REPO_DIR / "docs/eval/holdout-sequences.md")
    parser.add_argument("--from-json", type=Path)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    if args.from_json:
        write_report(json.loads(args.from_json.read_text(encoding="utf-8")), args.out)
        return
    settings = Settings(LLM_PROVIDER="vertex", STT_PROVIDER="mock", STORE="memory", RETRIEVER="local",
                        JUDGE_MODE="split3")
    clock = ReplayClock()
    ctx = build_context(settings, clock=clock, scheduler=AsyncScheduler(clock))
    raw = []
    try:
        await ctx.llm.warm_up()
        for run_no in range(args.runs):
            for seq in load_cases("holdout_sequences.jsonl"):
                raw.append(await run_sequence(ctx, seq, run_no))
                print(f"{seq['seq_id']} run {run_no + 1}: done")
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
        await ctx.llm.aclose()
    write_report(raw, args.out)


if __name__ == "__main__":
    asyncio.run(main())
