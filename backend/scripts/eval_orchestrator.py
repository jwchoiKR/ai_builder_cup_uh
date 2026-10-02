"""Does the utterance orchestrator route tricky sentences to the right branch with the real agents?

Each case is text injected as a final STT transcript (no audio) into a fresh live session, with the
real UtteranceJudge and FactChecker on Vertex AI. The checks look at what the orchestrator did:
compliance alerts, fact notes, prompter points, host-answer posts and the product switch. The same
branches are unit-tested with scripted agents in tests/test_orchestrator_cases.py.

    uv run python scripts/eval_orchestrator.py [--runs 3] [--out ../docs/eval/orchestrator-cases.md]
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import datetime as dt
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import REPO_DIR, get_settings  # noqa: E402
from app.context import build_context  # noqa: E402
from app.models.session import AgentCall, Message  # noqa: E402
from app.pipelines.runtime import create_session  # noqa: E402

CREAM, AMPOULE = "cream_hydra_barrier", "ampoule_deep_hydration"


@dataclass
class Case:
    id: str
    lines: list[str]
    why: str  # what makes it tricky
    compliance: set[str] | str | None = None  # rule ids, or "HIGH"/"MEDIUM" for any rule of that severity
    facts: set[str] = field(default_factory=set)  # fact note fields
    covered: set[str] = field(default_factory=set)  # prompter points
    answer: bool = False  # host answer posted
    switch: str | None = None  # "idle" or "switched"
    setup: str | None = None  # comment burst fired first

    def expected(self) -> str:
        parts = []
        if isinstance(self.compliance, str):
            parts.append(f"{self.compliance} alert")
        elif self.compliance:
            parts.append("alert " + ", ".join(sorted(self.compliance)))
        else:
            parts.append("no alert")
        parts.append(("fact note " + ", ".join(sorted(self.facts))) if self.facts else "no fact note")
        if self.covered:
            parts.append("prompter " + ", ".join(sorted(self.covered)))
        if self.answer:
            parts.append("host answer posted")
        if self.switch:
            parts.append({"idle": "no switch", "switched": "switch to the ampoule"}[self.switch])
        return "; ".join(parts)


CASES = [
    Case("explicit claim", ["This cream cures eczema."],
         "plain disease claim", compliance={"ASEAN-2D-DISEASE"}),
    Case("claim without keywords", ["Your breakouts will be gone in a week."],
         "acne claim with no listed keyword", compliance={"ASEAN-3-SKIN-ACNE"}),
    Case("negated claim", ["It doesn't cure eczema, it's just a moisturiser."],
         "risky words, but negated"),
    Case("question read out", ["Jun is asking if it heals acne scars."],
         "risky words inside a viewer's question"),
    Case("off-topic risky word", ["My cat literally cured my bad mood today, haha."],
         "'cured' but not about the product"),
    Case("superlative", ["Honestly, it's the best moisturiser in Singapore."],
         "MEDIUM rule, not HIGH", compliance="MEDIUM"),
    Case("approved test result", ["In our in-house test, twenty-nine of thirty-two people said their skin felt less dry after two weeks."],
         "numbers and a benefit, all approved"),
    Case("mixed-up ingredient amount", ["The cream has five percent ceramide NP."],
         "5% belongs to panthenol; ceramide NP is 1%", facts={"ingredient_amount"}),
    Case("correct price", ["The live price today is thirty-six dollars."],
         "a price that is right"),
    Case("claim and wrong price together", ["It repairs damaged skin, and it's only thirty dollars today."],
         "two branches at once", compliance="HIGH", facts={"price"}),
    Case("prompter point", ["It's a lightweight gel-cream, so it absorbs really quickly."],
         "plain product talk", covered={"cr-p1"}),
    Case("answer to a question on screen", ["Raj is asking if it's OK for oily skin. Yes, it's lightweight, so just use a smaller amount on oily areas."],
         "a question read out, then answered", answer=True, setup="B2"),
    Case("next product mentioned in passing", ["We'll get to the Deep Hydration Ampoule a bit later."],
         "names the next product, no transition", switch="idle"),
    Case("product switch", ["Okay, now let me show you our Deep Hydration Ampoule.",
                            "It has four percent niacinamide and helps skin look more radiant."],
         "named transition, then a fact about it", switch="switched"),
]


async def wait_idle(rt, extra_s: float = 0.3) -> None:
    for _ in range(3):
        await rt.utterances.drain()
        await asyncio.sleep(extra_s)


async def run_case(ctx, case: Case) -> dict:
    s = await create_session(ctx, "daon_skincare_demo")
    rt = await ctx.runtimes.get(s.session_id)
    await rt.start()
    await asyncio.sleep(2.5)  # past the comment grace window
    if case.setup:
        await rt.feed.fire(case.setup)
        for _ in range(120):  # until a question with a verified answer is on the host screen
            sess = await rt.load_session()
            if sess.host_slots:
                g = await rt.get_group(sess.host_slots[0].group_id)
                ans = await rt.get_answer(g.answer_id) if g and g.answer_id else None
                if ans is not None and ans.verified:
                    break
            await asyncio.sleep(0.5)
        await asyncio.sleep(1)
    ids: list[str] = []
    for line in case.lines:
        t = await rt.inject_transcript(line)
        ids.append(t.transcript_id)
        await wait_idle(rt)
        await asyncio.sleep(1.5)
    if case.answer:
        await asyncio.sleep(2.5)  # the 2 s cancel window of a host post
    if case.switch == "switched":
        await asyncio.sleep(6)  # the 5 s switch countdown
    await wait_idle(rt)

    alerts = [a for a in await rt.alerts() if a.transcript_id in ids and a.status == "active"]
    got_rules = {a.rule_id for a in alerts if a.kind == "compliance"}
    got_sev = {a.severity for a in alerts if a.kind == "compliance"}
    got_facts = {a.field for a in alerts if a.kind == "fact"}
    seg = await rt.current_segment()
    segs = await rt.segments()
    cream_seg = next(x for x in segs if x.product_id == CREAM)
    posted = [m for m in await rt.ctx.store.query(rt.path("messages"), Message) if m.kind == "host_answer"]
    sess = await rt.load_session()
    calls = await rt.ctx.store.query(rt.path("agent_calls"), AgentCall, order_by="started_at")

    checks = {}
    if isinstance(case.compliance, str):
        checks["compliance"] = case.compliance in got_sev
    else:
        checks["compliance"] = got_rules == (case.compliance or set())
    checks["facts"] = got_facts == case.facts
    if case.covered:
        checks["prompter"] = case.covered <= set(cream_seg.covered_point_ids)
    if case.answer:
        checks["answer"] = bool(posted)
    if case.switch == "switched":
        checks["switch"] = seg.product_id == AMPOULE
    elif case.switch == "idle":
        checks["switch"] = seg.product_id == CREAM and sess.switch.status == "idle"

    judged = []
    for c in calls:
        if c.agent in ("utterance_judge", "fact_checker") and c.input_preview in case.lines and c.output:
            o = c.output
            if c.agent == "utterance_judge":
                judged.append({
                    "agent": "judge", "line": c.input_preview, "ms": c.latency_ms,
                    "type": o["answer"]["utterance_type"],
                    "violations": [(v["rule_id"], "negated" if v["is_negated"] else "quoted" if v["is_quoted"] else "claim")
                                   for v in o["compliance"]["violations"]],
                    "covered": o["prompter"]["covered_point_ids"], "answered": o["answer"]["is_answer"],
                    "transition": o["prompter"]["switch"]["is_transition"]})
            else:
                judged.append({"agent": "facts", "line": c.input_preview, "ms": c.latency_ms,
                               "claims": [(x["field"], x["verdict"], x["stated_value"], x.get("correct_value"))
                                          for x in o["claims"]]})
        elif c.agent in ("utterance_judge", "fact_checker") and c.input_preview in case.lines:
            judged.append({"agent": c.agent, "line": c.input_preview, "status": c.status})
    return {
        "case": case.id, "pass": all(checks.values()), "checks": checks,
        "got": {"rules": sorted(got_rules), "severity": sorted(got_sev), "facts": sorted(got_facts),
                "covered": cream_seg.covered_point_ids, "posted": len(posted), "on_air": seg.product_id},
        "agents": judged,
    }


def describe(r: dict) -> str:
    g = r["got"]
    bits = [("alert " + ", ".join(g["rules"])) if g["rules"] else "no alert",
            ("fact note " + ", ".join(g["facts"])) if g["facts"] else "no fact note"]
    if "prompter" in r["checks"]:
        bits.append("prompter " + (", ".join(g["covered"]) or "nothing"))
    if "answer" in r["checks"]:
        bits.append("host answer posted" if g["posted"] else "no host answer")
    if "switch" in r["checks"]:
        bits.append("on air: " + ("ampoule" if g["on_air"] == AMPOULE else "cream"))
    return "; ".join(bits)


def judge_line(r: dict) -> str:
    out = []
    for a in r["agents"]:
        if a["agent"] == "judge":
            v = ", ".join(f"{rule} ({kind})" for rule, kind in a["violations"]) or "no violation"
            extra = []
            if a["covered"]:
                extra.append("points " + ",".join(a["covered"]))
            if a["answered"]:
                extra.append("answer")
            if a["transition"]:
                extra.append("transition")
            out.append(f"judge: {a['type']}, {v}" + (f", {', '.join(extra)}" if extra else "") + f" ({a['ms']} ms)")
        elif a["agent"] == "facts":
            cl = ", ".join(f"{f} {verdict} ({stated}" + (f" → {correct}" if correct and verdict == "contradicted" else "") + ")"
                           for f, verdict, stated, correct in a["claims"]) or "no claim"
            out.append(f"facts: {cl} ({a['ms']} ms)")
        else:
            out.append(f"{a['agent']}: {a['status']}")
    return "<br>".join(out)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--out", type=Path, default=REPO_DIR / "docs" / "eval" / "orchestrator-cases.md")
    args = ap.parse_args()
    settings = get_settings()
    ctx = build_context(settings)
    print("warm-up:", await ctx.llm.warm_up())
    results: dict[str, list[dict]] = collections.defaultdict(list)
    for run in range(1, args.runs + 1):
        for case in CASES:
            r = await run_case(ctx, case)
            results[case.id].append(r)
            print(f"run {run} {'PASS' if r['pass'] else 'FAIL'} {case.id}: {describe(r)}")
    ctx.runtimes.shutdown()
    ctx.scheduler.shutdown()
    await ctx.llm.aclose()

    total = sum(len(v) for v in results.values())
    passed = sum(r["pass"] for v in results.values() for r in v)
    rows = []
    for i, case in enumerate(CASES, 1):
        rs = results[case.id]
        n_ok = sum(r["pass"] for r in rs)
        last_fail = next((r for r in reversed(rs) if not r["pass"]), rs[-1])
        lines = " / ".join(f"“{x}”" for x in case.lines)
        setup = f" (after burst {case.setup})" if case.setup else ""
        rows.append(f"| {i} | {lines}{setup} | {case.why} | {case.expected()} | {n_ok}/{len(rs)} | "
                    f"{describe(last_fail)} | {judge_line(last_fail)} |")
    lines_md = [
        f"# Orchestrator branching on tricky sentences · {dt.date.today().isoformat()}",
        "",
        "**What runs:**",
        "- Each case is text injected as a final transcript (what STT would send) into a fresh live session.",
        f"- The agents are real: `{settings.LLM_FAST_MODEL}` on Vertex AI for the UtteranceJudge and the FactChecker; "
        "the Comment Triage and Answer Composer also run for the case with a comment burst.",
        "- The checks look only at what the orchestrator did with the agents' answers: compliance alerts, fact notes, "
        "prompter points, the host-answer post and the product switch.",
        f"- **Runs:** {args.runs} per case, because model answers can vary. Script: `backend/scripts/eval_orchestrator.py`.",
        "- **Unit tests:** the same branches with scripted agents are in `backend/tests/test_orchestrator_cases.py`.",
        "",
        f"**Result:** {passed}/{total} case runs passed.",
        "",
        "| # | Input (STT text) | Why it is tricky | Expected | Pass | What happened (a failing run if any, else the last) | What the agents said |",
        "|---|---|---|---|---|---|---|",
        *rows,
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines_md) + "\n", encoding="utf-8", newline="\n")
    args.out.with_suffix(".json").write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n",
                                             encoding="utf-8", newline="\n")
    print(f"{passed}/{total} passed · report: {args.out}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
