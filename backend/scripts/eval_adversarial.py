"""Adversarial eval (proof-plan §3) on the real UtterancePipeline.

Each case runs on a fresh session, so post-validation, merge, dedupe and correction logic all count,
not only the raw judges. A case is one `utterance`, or `parts` fed as consecutive finals 400 ms apart.

    uv run python scripts/eval_adversarial.py --runs 3 --cases adversarial_cases.jsonl \
        --out ../docs/eval/adversarial-tune.md
    uv run python scripts/eval_adversarial.py --from-json ../docs/eval/adversarial-tune.json --cases ...

Pass lines (fixed before results): risky lines caught >= 95%, 0 wrong HIGH, false alerts on safe lines
<= 5%, 0 wrong correction texts, extra wrong alerts on risky lines <= 5%.

D-197 (full review, P1): a risky line counts as caught only with the expected rule or field, and for a fact line
with the expected correct value in the correction; an alert of the right kind with another rule or field is not a
catch. Every other alert on a risky line (another rule, another field, the other kind) is an extra wrong alert.

`expected.unverifiable` (optional, safe lines, D-235): the sheet cannot settle the fact; silence passes and a soft fact
note is not a false alert (a compliance alert still is).

`expected.also_ok_rule_ids` / `expected.also_ok_fields` (optional): a compliance alert with one of these rules,
or a fact alert on one of these fields, is accepted for an ambiguous line or a line with a second true error. It is never a wrong HIGH or a false alert (a safe line keeps no error); on a risky line
it counts as caught.
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
from app.logic.qualifier import RULE_ID as QUALIFIER  # noqa: E402
from app.models.session import AgentCall  # noqa: E402
from app.pipelines.runtime import create_session  # noqa: E402
from app.pipelines.utterances import operator_switch  # noqa: E402
from app.scheduler import AsyncScheduler  # noqa: E402

PART_GAP_S = 0.4
# D-222: --release <release_id> runs every case on that onboarded product's show (one product, so the case's
# current_product_id is ignored and cases may name the product by role)
RELEASE: str | None = None
# D-197: the labels name a fact by what the host said ("live_price", "panthenol"); the fact checker's fields are
# app.models.agent_io.FactField
LABEL_FIELDS = {"live_price": "price", "list_price": "price", "panthenol": "ingredient_amount",
                "niacinamide": "ingredient_amount"}


def _field(label: str | None) -> str | None:
    return LABEL_FIELDS.get(label, label) if label else label
PASS = {"detection": 0.95, "false_alert": 0.05, "extra_wrong": 0.05}


def load_cases(name: str) -> list[dict]:
    path = get_settings().data_path / "eval" / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


async def run_case(ctx, case: dict, run_no: int) -> dict:
    """The alerts the host would see for this case: every compliance or fact alert that became active."""
    s = await create_session(ctx, next(iter(ctx.pack.runsheets)), release_id=RELEASE)
    rt = await ctx.runtimes.get(s.session_id)
    rt.pd.agent = None  # this eval isolates the utterance pipeline
    try:
        await rt.start()
        if RELEASE is None and (await rt.current_segment()).product_id != case["current_product_id"]:
            await operator_switch(rt, case["current_product_id"])
        parts = case.get("parts") or [case["utterance"]]
        for i, text in enumerate(parts):
            await rt.utterances.submit(text, source="injected", speech_end_at=rt.now(), scenario="eval")
            if i < len(parts) - 1:
                await asyncio.sleep(PART_GAP_S)
        await rt.utterances.drain()
        alerts = [a for a in await rt.alerts() if a.shown_at is not None]
        calls = sorted(await rt.ctx.store.query(rt.path("agent_calls"), AgentCall), key=lambda c: c.started_at)
        # the fact checker's tries per line (D-203 retries once after a timeout or error): retried, final status
        tries = collections.defaultdict(list)
        for c in calls:
            if c.agent == "fact_checker":
                tries[c.input_preview].append(c)
        return {"id": case["case_id"], "run": run_no,
                # every judge and fact output with its reason, to diagnose a miss or a false alert
                "calls": [{"agent": c.agent, "input": c.input_preview, "status": c.status, "output": c.output,
                           "latency_ms": c.latency_ms}
                          | ({"retried": len(tries[c.input_preview]) > 1,
                              "final_status": tries[c.input_preview][-1].status} if c.agent == "fact_checker" else {})
                          for c in calls if c.agent in ("compliance_judge", "context_judge", "fact_checker",
                                                        "utterance_judge", "judge_single")],
                # per line: the fact check's whole time, retry included, and how it ended
                "facts": [{"input": k, "ms": sum(c.latency_ms for c in v), "tries": len(v), "final_status": v[-1].status,
                           "timeouts": sum(c.status == "timeout" for c in v)} for k, v in tries.items()],
                "alerts": [{"kind": a.kind, "rule_id": a.rule_id, "severity": a.severity, "field": a.field,
                            "span": a.span, "say_instead": a.say_instead, "stated_value": a.stated_value,
                            "correct_value": a.correct_value, "status": a.status} for a in alerts]}
    finally:
        await ctx.runtimes.drop(rt.sid)


def _kind(a: dict) -> str:
    if a["kind"] == "fact":
        return "fact"
    return "qualifier" if a["rule_id"] == QUALIFIER else "compliance"


def _lexicon():
    from app.logic.catalog import DataPack

    return DataPack.load(get_settings().data_path).lexicon


def _wrong_text(a: dict, correct: str | None) -> bool:
    """The correction shown to the host does not carry the expected right value."""
    if not correct:
        return False
    spoken_numbers = _lexicon().spoken_numbers
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
        also_ok = set(exp.get("also_ok_rule_ids") or [])
        also_fields = {_field(x) for x in exp.get("also_ok_fields") or []}
        field = _field(exp.get("field"))
        # alerts the label accepts for an ambiguous line are left out of every error count
        alerts = [a for a in r["alerts"] if not (a["kind"] == "compliance" and a["rule_id"] in also_ok)
                  and not (a["kind"] == "fact" and a["field"] in also_fields and a["field"] != field)]
        accepted = [a for a in r["alerts"] if a not in alerts]
        row = {"id": r["id"], "run": r["run"], "type": case["type"], "risky": exp["risky"], "kind": exp.get("kind"),
               "alerts": alerts + accepted}
        if exp["risky"]:
            hits = [a for a in alerts if _kind(a) == exp["kind"]]
            labelled = exp.get("rule_id") or exp.get("field")
            exact = [a for a in hits if (exp.get("rule_id") and a["rule_id"] == exp["rule_id"])
                     or (field and a["field"] == field)] if labelled else hits
            # the expected right value is compared with the alert of the expected field only
            same_field = [a for a in hits if not field or a["field"] == field]
            row["wrong_text"] = any(_wrong_text(a, exp.get("correct_value")) for a in same_field)
            # D-197: caught = the right rule or field, with the right value in a fact correction
            right = [a for a in exact if not _wrong_text(a, exp.get("correct_value"))]
            row["caught"] = bool(right) or bool(accepted)
            row["exact"] = row["caught"]
            row["extra"] = [a for a in alerts if a not in exact]
            row["extra_wrong"] = bool(row["extra"])
            # a red alert is wrong when the line's risk is not a HIGH compliance claim
            row["wrong_high"] = any(a["severity"] == "HIGH" for a in alerts) and exp["kind"] != "compliance"
        else:
            # D-235: `expected.unverifiable` (a fact the sheet cannot settle): silence passes and a soft fact note is
            # not a false alert; a compliance alert still is
            soft = [a for a in alerts if a["kind"] == "fact"] if exp.get("unverifiable") else []
            counted = [a for a in alerts if a not in soft]
            row["unverifiable_soft"] = bool(soft)
            row["false_alert"] = bool(counted)
            row["false_high"] = any(a["kind"] == "compliance" and a["severity"] == "HIGH" for a in counted)
            row["false_medium"] = any(a["kind"] == "compliance" and a["severity"] == "MEDIUM" for a in counted)
            row["false_fact"] = any(a["kind"] == "fact" for a in counted)
            row["wrong_high"] = row["false_high"]
            row["wrong_text"] = False
            row["extra_wrong"] = False
        rows.append(row)
    risky = [x for x in rows if x["risky"]]
    safe = [x for x in rows if not x["risky"]]
    detection = sum(x["caught"] for x in risky) / len(risky) if risky else 1.0
    false_rate = sum(x["false_alert"] for x in safe) / len(safe) if safe else 0.0
    wrong_high = sum(x["wrong_high"] for x in rows)
    wrong_text = sum(x["wrong_text"] for x in rows)
    extra_rate = sum(x["extra_wrong"] for x in risky) / len(risky) if risky else 0.0
    unverifiable_soft = sum(x.get("unverifiable_soft", False) for x in safe)
    lines = [f for r in raw for f in r.get("facts", [])]
    ms = sorted(f["ms"] for f in lines)
    pick = lambda q: ms[min(len(ms) - 1, int(q * len(ms)))] if ms else 0  # noqa: E731
    facts = {"lines": len(lines), "p50_ms": pick(0.5), "p95_ms": pick(0.95),
             "timeout_calls": sum(f["timeouts"] for f in lines), "retried": sum(f["tries"] > 1 for f in lines),
             "final_not_ok": sum(f["final_status"] != "ok" for f in lines)}
    return {"rows": rows, "facts": facts, "detection": detection, "false_rate": false_rate, "wrong_high": wrong_high,
            "wrong_text": wrong_text, "extra_rate": extra_rate, "unverifiable_soft": unverifiable_soft,
            "passed": detection >= PASS["detection"] and wrong_high == 0 and false_rate <= PASS["false_alert"]
            and wrong_text == 0 and extra_rate <= PASS["extra_wrong"],
            "runs": len({x["run"] for x in rows})}


def write_report(s: dict, cases: list[dict], out: Path, name: str) -> None:
    by_type: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for x in s["rows"]:
        c = by_type[x["type"]]
        if x["risky"]:
            c["risky"] += 1
            c["caught"] += x["caught"]
            c["exact"] += x["exact"]
            c["extra"] += x["extra_wrong"]
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
        f"{s['wrong_text']} (0) · risky lines with an extra wrong alert {s['extra_rate']:.1%} (≤ 5%)", "",
        f"Fact checker per line (retry included): p50 {s['facts']['p50_ms']} ms · p95 {s['facts']['p95_ms']} ms · "
        f"{s['facts']['lines']} lines · timed-out calls {s['facts']['timeout_calls']} · retried lines "
        f"{s['facts']['retried']} · lines without a completed check {s['facts']['final_not_ok']}", "",
        f"Unverifiable lines with a soft fact note (not a false alert): {s['unverifiable_soft']}", "",
        "Caught means the expected rule or field, and the right value in a fact correction (D-197).", "",
        "| type | risky caught | extra wrong alert | safe with an alert | HIGH | MEDIUM | fact note | wrong HIGH | "
        "wrong text |", "|---|---|---|---|---|---|---|---|---|",
    ]
    for t, c in sorted(by_type.items()):
        lines.append(f"| {t} | {pct(c['caught'], c['risky'])} | {pct(c['extra'], c['risky'])} | "
                     f"{pct(c['false'], c['safe'])} | {c['false_high']} | {c['false_medium']} | {c['false_fact']} | "
                     f"{c['wrong_high']} | {c['wrong_text']} |")
    misses = [x for x in s["rows"] if x["risky"] and not x["caught"]]
    falses = [x for x in s["rows"] if not x["risky"] and x["false_alert"]]
    bad = [x for x in s["rows"] if x["wrong_high"] or x["wrong_text"]]
    extra = [x for x in s["rows"] if x["extra_wrong"]]
    by_id = {c["case_id"]: c for c in cases}
    text = lambda x: " / ".join(by_id[x["id"]].get("parts") or [by_id[x["id"]]["utterance"]])  # noqa: E731
    shown = lambda x: "; ".join(f"{a['kind']} {a['rule_id'] or a['field']} {a['severity'] or ''}"  # noqa: E731
                                for a in x["alerts"]) or "none"
    for title, items in (("Missed risky lines", misses), ("Alerts on safe lines", falses),
                         ("Wrong HIGH or wrong correction text", bad), ("Extra wrong alerts on risky lines", extra)):
        lines += ["", f"## {title}", ""]
        lines += [f"- {x['id']} run {x['run']} ({x['type']}): \"{text(x)}\" → {shown(x)}" for x in items] or ["- none"]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--cases", default="adversarial_cases.jsonl")
    ap.add_argument("--release", default=None, help="an onboarded release id (ONBOARDING_DIR/releases)")
    ap.add_argument("--out", type=Path, default=REPO_DIR / "docs/eval/adversarial.md")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--from-json", type=Path, default=None, help="re-score saved outputs without calling the models")
    args = ap.parse_args()
    cases = load_cases(args.cases)
    global RELEASE
    RELEASE = args.release
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
          f"false alerts {s['false_rate']:.1%} wrong texts {s['wrong_text']} extra wrong {s['extra_rate']:.1%}")
    return 0 if s["passed"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
