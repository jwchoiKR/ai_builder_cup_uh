"""Adversarial eval (proof-plan §3) on the real UtterancePipeline.

Each case runs on a fresh session, so post-validation, merge, dedupe and correction logic all count,
not only the raw judges. A case is one `utterance`, or `parts` fed as consecutive finals 400 ms apart.

    uv run python scripts/eval_adversarial.py --runs 3 --cases adversarial_cases.jsonl \
        --out ../docs/eval/adversarial-tune.md
    uv run python scripts/eval_adversarial.py --from-json ../docs/eval/adversarial-tune.json --cases ...

Pass lines (fixed before results): risky lines caught >= 95%, 0 wrong HIGH, false alerts on safe lines
<= 5%, 0 wrong correction texts.
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_holdout_sequences import ReplayClock  # noqa: E402

from app.config import REPO_DIR, Settings, get_settings  # noqa: E402
from app.context import build_context  # noqa: E402
from app.logic.publish import spoken_numbers  # noqa: E402
from app.logic.qualifier import RULE_ID as QUALIFIER  # noqa: E402
from app.pipelines.runtime import create_session  # noqa: E402
from app.pipelines.utterances import operator_switch  # noqa: E402
from app.scheduler import AsyncScheduler  # noqa: E402

PART_GAP_S = 0.4
PASS = {"detection": 0.95, "false_alert": 0.05}


def load_cases(name: str) -> list[dict]:
    path = get_settings().data_path / "eval" / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


async def run_case(ctx, case: dict, run_no: int) -> dict:
    """The alerts the host would see for this case: every compliance or fact alert that became active."""
    s = await create_session(ctx, next(iter(ctx.pack.runsheets)))
    rt = await ctx.runtimes.get(s.session_id)
    rt.pd.agent = None  # this eval isolates the utterance pipeline
    try:
        await rt.start()
        if (await rt.current_segment()).product_id != case["current_product_id"]:
            await operator_switch(rt, case["current_product_id"])
        parts = case.get("parts") or [case["utterance"]]
        for i, text in enumerate(parts):
            await rt.utterances.submit(text, source="injected", speech_end_at=rt.now(), scenario="eval")
            if i < len(parts) - 1:
                await asyncio.sleep(PART_GAP_S)
        await rt.utterances.drain()
        alerts = [a for a in await rt.alerts() if a.shown_at is not None]
        return {"id": case["case_id"], "run": run_no,
                "alerts": [{"kind": a.kind, "rule_id": a.rule_id, "severity": a.severity, "field": a.field,
                            "span": a.span, "say_instead": a.say_instead, "stated_value": a.stated_value,
                            "correct_value": a.correct_value, "status": a.status} for a in alerts]}
    finally:
        await ctx.runtimes.drop(rt.sid)


def _kind(a: dict) -> str:
    if a["kind"] == "fact":
        return "fact"
    return "qualifier" if a["rule_id"] == QUALIFIER else "compliance"


def _wrong_text(a: dict, correct: str | None) -> bool:
    """The correction shown to the host does not carry the expected right value."""
    if not correct:
        return False
    want = spoken_numbers(correct)
    shown = a["correct_value"] if a["kind"] == "fact" else a["say_instead"]
    if not want:
        return False
    return not want <= spoken_numbers(shown or "")


def score(raw: list[dict], cases: list[dict]) -> dict:
    by_id = {c["case_id"]: c for c in cases}
    rows = []
    for r in raw:
        case = by_id[r["id"]]
        exp = case["expected"]
        alerts = r["alerts"]
        row = {"id": r["id"], "run": r["run"], "type": case["type"], "risky": exp["risky"], "kind": exp.get("kind"),
               "alerts": alerts}
        if exp["risky"]:
            hits = [a for a in alerts if _kind(a) == exp["kind"]]
            row["caught"] = bool(hits)
            exact = [a for a in hits if (exp.get("rule_id") and a["rule_id"] == exp["rule_id"])
                     or (exp.get("field") and a["field"] == exp["field"])]
            row["exact"] = bool(exact) if (exp.get("rule_id") or exp.get("field")) else row["caught"]
            row["wrong_text"] = any(_wrong_text(a, exp.get("correct_value")) for a in hits)
            # a red alert is wrong when the line's risk is not a HIGH compliance claim
            row["wrong_high"] = any(a["severity"] == "HIGH" for a in alerts) and exp["kind"] != "compliance"
        else:
            row["false_alert"] = bool(alerts)
            row["false_high"] = any(a["kind"] == "compliance" and a["severity"] == "HIGH" for a in alerts)
            row["false_medium"] = any(a["kind"] == "compliance" and a["severity"] == "MEDIUM" for a in alerts)
            row["false_fact"] = any(a["kind"] == "fact" for a in alerts)
            row["wrong_high"] = row["false_high"]
            row["wrong_text"] = False
        rows.append(row)
    risky = [x for x in rows if x["risky"]]
    safe = [x for x in rows if not x["risky"]]
    detection = sum(x["caught"] for x in risky) / len(risky) if risky else 1.0
    false_rate = sum(x["false_alert"] for x in safe) / len(safe) if safe else 0.0
    wrong_high = sum(x["wrong_high"] for x in rows)
    wrong_text = sum(x["wrong_text"] for x in rows)
    return {"rows": rows, "detection": detection, "false_rate": false_rate, "wrong_high": wrong_high,
            "wrong_text": wrong_text,
            "passed": detection >= PASS["detection"] and wrong_high == 0 and false_rate <= PASS["false_alert"]
            and wrong_text == 0,
            "runs": len({x["run"] for x in rows})}


def write_report(s: dict, cases: list[dict], out: Path, name: str) -> None:
    by_type: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for x in s["rows"]:
        c = by_type[x["type"]]
        if x["risky"]:
            c["risky"] += 1
            c["caught"] += x["caught"]
            c["exact"] += x["exact"]
        else:
            c["safe"] += 1
            c["false"] += x["false_alert"]
            c["false_high"] += x["false_high"]
            c["false_medium"] += x["false_medium"]
            c["false_fact"] += x["false_fact"]
        c["wrong_high"] += x["wrong_high"]
        c["wrong_text"] += x["wrong_text"]
    pct = lambda a, b: f"{a}/{b} ({100 * a / b:.0f}%)" if b else "-"  # noqa: E731
    lines = [
        "# Adversarial eval (proof-plan §3)", "",
        f"{dt.date.today().isoformat()} · `{name}` · {len(cases)} cases × {s['runs']} runs · real UtterancePipeline "
        "per case (post-validation, merge, dedupe and corrections included).", "",
        f"**{'PASS' if s['passed'] else 'FAIL'}** · detection {s['detection']:.1%} (≥ 95%) · wrong HIGH "
        f"{s['wrong_high']} (0) · false alerts {s['false_rate']:.1%} (≤ 5%) · wrong correction texts "
        f"{s['wrong_text']} (0)", "",
        "| type | risky caught | right rule/field | safe with an alert | HIGH | MEDIUM | fact note | wrong HIGH | "
        "wrong text |", "|---|---|---|---|---|---|---|---|---|",
    ]
    for t, c in sorted(by_type.items()):
        lines.append(f"| {t} | {pct(c['caught'], c['risky'])} | {pct(c['exact'], c['risky'])} | "
                     f"{pct(c['false'], c['safe'])} | {c['false_high']} | {c['false_medium']} | {c['false_fact']} | "
                     f"{c['wrong_high']} | {c['wrong_text']} |")
    misses = [x for x in s["rows"] if x["risky"] and not x["caught"]]
    falses = [x for x in s["rows"] if not x["risky"] and x["false_alert"]]
    bad = [x for x in s["rows"] if x["wrong_high"] or x["wrong_text"]]
    by_id = {c["case_id"]: c for c in cases}
    text = lambda x: " / ".join(by_id[x["id"]].get("parts") or [by_id[x["id"]]["utterance"]])  # noqa: E731
    shown = lambda x: "; ".join(f"{a['kind']} {a['rule_id'] or a['field']} {a['severity'] or ''}"  # noqa: E731
                                for a in x["alerts"]) or "none"
    for title, items in (("Missed risky lines", misses), ("Alerts on safe lines", falses),
                         ("Wrong HIGH or wrong correction text", bad)):
        lines += ["", f"## {title}", ""]
        lines += [f"- {x['id']} run {x['run']} ({x['type']}): \"{text(x)}\" → {shown(x)}" for x in items] or ["- none"]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--cases", default="adversarial_cases.jsonl")
    ap.add_argument("--out", type=Path, default=REPO_DIR / "docs/eval/adversarial.md")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--from-json", type=Path, default=None, help="re-score saved outputs without calling the models")
    args = ap.parse_args()
    cases = load_cases(args.cases)
    if args.from_json:
        raw = json.loads(args.from_json.read_text(encoding="utf-8"))
    else:
        settings = Settings(LLM_PROVIDER="vertex", STT_PROVIDER="mock", STORE="memory", RETRIEVER="local",
                            JUDGE_MODE="split3")
        clock = ReplayClock()
        ctx = build_context(settings, clock=clock, scheduler=AsyncScheduler(clock))
        sem = asyncio.Semaphore(args.concurrency)
        raw = []

        async def one(case: dict, run_no: int) -> dict:
            async with sem:
                return await run_case(ctx, case, run_no)

        try:
            await ctx.llm.warm_up()
            for run_no in range(args.runs):
                raw += await asyncio.gather(*(one(c, run_no) for c in cases))
                print(f"run {run_no + 1}/{args.runs} done")
        finally:
            ctx.runtimes.shutdown()
            ctx.scheduler.shutdown()
            await ctx.llm.aclose()
        args.out.with_suffix(".json").write_text(json.dumps(raw, ensure_ascii=False) + "\n", encoding="utf-8",
                                                 newline="\n")
    s = score(raw, cases)
    write_report(s, cases, args.out, args.cases)
    print(f"{'PASS' if s['passed'] else 'FAIL'} detection {s['detection']:.1%} wrong HIGH {s['wrong_high']} "
          f"false alerts {s['false_rate']:.1%} wrong texts {s['wrong_text']}")
    return 0 if s["passed"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
