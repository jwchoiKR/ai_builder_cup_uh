"""Spoken-answer auto-post evaluation (D-110), data/eval/verbal_post_cases.jsonl.

Runs the production agents (split3: compliance, context, facts) on each host utterance with the
case's open questions and verified drafts, then applies the real publish decision
(`logic.publish.decide`) as the runtime would, for the matched group and every group the judge also linked
(D-196). With `--runtime`, each case runs in a real session instead (groups and verified drafts seeded, the host
slot set, the line submitted, the 2 s publish window waited out) and the committed posts are read back.

PASS (D-198, full review P1): 0 false posts (a post where the case expects none, or to a question it did not
mark), 0 missed posts and 0 duplicate posts (one group posted twice). Missed posts whose cause is a timeout (a
judge with no output, or "check incomplete" from a fact check that did not finish) are listed apart from logic
misses, but count against PASS too.

    uv run python scripts/eval_verbal_post.py --runs 3          # docs/eval/verbal-post.md and .json
    uv run python scripts/eval_verbal_post.py --runs 3 --runtime --out ../docs/eval/verbal-post-runtime.md
    uv run python scripts/eval_verbal_post.py --from-json docs/eval/verbal-post.json   # re-score only
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

from eval_agents import EVAL_DIR, run  # noqa: E402

from app.config import Settings, get_settings  # noqa: E402
from app.logic.publish import decide  # noqa: E402
from app.models.agent_io import FactCheckOutput, UtteranceJudgeOutput  # noqa: E402
from app.models.session import AgentCall, Answer, HostSlot, Message, QuestionGroup  # noqa: E402

CASES = "verbal_post_cases.jsonl"


def load_cases(name: str = CASES) -> list[dict]:
    path = get_settings().data_path / "eval" / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _group(q: dict, product_id: str) -> QuestionGroup:
    return QuestionGroup(group_id=q["group_id"], product_id=q.get("product_id", product_id), intent="other",
                         condition_slots={}, canonical_question=q["canonical_question"], member_comment_ids=["c"],
                         unique_author_ids=["u"], first_at=0, last_at=0, route="HOST", route_reason="eval",
                         status="ready", answer_id=f"ans_{q['group_id']}")


def _answer(q: dict) -> Answer:
    return Answer(answer_id=f"ans_{q['group_id']}", group_id=q["group_id"], text=q["suggested_answer"], citations=[],
                  origin="ai", verified=True, verify_errors=[], needs_human=False, created_at=0)


def _lexicon():
    from app.logic.catalog import DataPack

    return DataPack.load(get_settings().data_path).lexicon


def decisions_for(case: dict, row: dict) -> list[tuple[str, str | None, str]]:
    """The runtime's decision for the matched group, then for each group the judge also linked (D-196)."""
    first = decision_for(case, row)
    if row.get("judge") is None or first[2].startswith("relinked"):
        return [first]
    judge = UtteranceJudgeOutput.model_validate(row["judge"])
    facts = FactCheckOutput.model_validate(row["facts_validated"]) if row.get("facts_validated") else None
    qs = {q["group_id"]: q for q in case["context"]["open_questions"]}
    offered = {gid: _answer(q) for gid, q in qs.items()}
    a, out = judge.answer, [first]
    for gid in a.also_answered_group_ids:
        if gid not in qs:
            continue
        link = a.model_copy(update={"matched_group_id": gid, "consistent_with_suggested": True,
                                    "also_answered_group_ids": [a.matched_group_id,
                                                                *(g for g in a.also_answered_group_ids if g != gid)]})
        d = decide(judge.model_copy(update={"answer": link}), offered, _group(qs[gid], case["current_product_id"]),
                   offered[gid], high_alert_active=False, facts=facts, lex=_lexicon(), utterance=case["utterance"])
        out.append((d.action, d.group_id, d.reason))
    return out


def decision_for(case: dict, row: dict) -> tuple[str, str | None, str]:
    """(action, group_id, reason) the runtime would take for this agent output."""
    if row.get("judge") is None:
        return "none", None, "no judge output"
    judge = UtteranceJudgeOutput.model_validate(row["judge"])
    facts = FactCheckOutput.model_validate(row["facts_validated"]) if row.get("facts_validated") else None
    qs = {q["group_id"]: q for q in case["context"]["open_questions"]}
    offered = {gid: _answer(q) for gid, q in qs.items()}
    gid = judge.answer.matched_group_id
    group = _group(qs[gid], case["current_product_id"]) if gid in qs else None
    d = decide(judge, offered, group, offered.get(gid), high_alert_active=False, facts=facts, lex=_lexicon(),
               utterance=case["utterance"])
    relink = row.get("ctx_relink") or {}
    if d.action == "none" and gid is None and relink.get("answer"):
        # D-175: the second judge call about the one question the line seems to answer, with every usual check
        cand = relink["group_id"]
        second = judge.model_copy(update={"answer": judge.answer.model_validate(relink["answer"])})
        d = decide(second, {cand: offered[cand]}, _group(qs[cand], case["current_product_id"]), offered[cand],
                   high_alert_active=False, facts=facts, lex=_lexicon(), utterance=case["utterance"])
        return d.action, d.group_id, f"relinked: {d.reason}" if d.action != "post" else d.reason
    return d.action, d.group_id, d.reason


TIMEOUT_REASONS = ("check incomplete", "no judge output")


def score(raw: list[dict], cases: list[dict]) -> dict:
    by_id = {c["case_id"]: c for c in cases}
    rows = []
    for r in raw:
        case = by_id[r["id"]]
        exp = case["expected"]
        if "posts" in r:  # --runtime: the committed posts of a real session
            posts = [p["group"] for p in r["posts"] if p["state"] == "published"]
            decisions = [("post", g, "committed") for g in posts] or [("none", None, r.get("reason") or "no post")]
        else:
            decisions = decisions_for(case, r)
            posts = [g for action, g, _ in decisions if action == "post"]
        action, gid, reason = decisions[0]
        ok_groups = {exp.get("matched_group"), *exp.get("also_ok_groups", [])}  # one sentence may answer two
        false_post = bool(posts) and (not exp["post"] or any(g not in ok_groups for g in posts))
        missed = exp["post"] and not any(g in ok_groups for g in posts)
        timeout = (r.get("ctx_status") == "timeout" and r.get("judge") is None) or any(
            any(t in why for t in TIMEOUT_REASONS) for _, _, why in decisions) or any(
            c["status"] != "ok" for c in r.get("calls") or [])  # --runtime: a judge or fact call that did not finish
        rows.append({"id": r["id"], "run": r["run"], "category": exp["category"], "expected_post": exp["post"],
                     "action": "post" if posts else action, "group": ",".join(posts) or gid, "reason": reason,
                     "false_post": false_post, "missed_post": missed, "missed_timeout": missed and timeout,
                     "duplicate": len(posts) != len(set(posts)), "status": r.get("ctx_status")})
    false_posts = [x for x in rows if x["false_post"]]
    missed_posts = [x for x in rows if x["missed_post"]]
    duplicates = [x for x in rows if x["duplicate"]]
    return {"rows": rows, "false_posts": false_posts, "missed_posts": missed_posts, "duplicates": duplicates,
            "missed_timeouts": [x for x in missed_posts if x["missed_timeout"]],
            "passed": not false_posts and not missed_posts and not duplicates,
            "runs": len({x["run"] for x in rows})}


def write_report(s: dict, cases: list[dict], out: Path) -> None:
    by_cat: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for x in s["rows"]:
        c = by_cat[x["category"]]
        c["n"] += 1
        c["post"] += x["action"] == "post"
        c["false"] += x["false_post"]
        c["missed"] += x["missed_post"]
        c["dup"] += x["duplicate"]
    posts = sum(1 for x in s["rows"] if x["expected_post"])
    timeouts = len(s["missed_timeouts"])
    lines = [
        "# Spoken-answer auto-post (D-110)", "",
        f"{dt.date.today().isoformat()} · {len(cases)} cases × {s['runs']} runs · production agents (split3) "
        "+ `logic.publish.decide`. Cases: `data/eval/verbal_post_cases.jsonl`.", "",
        f"**{'PASS' if s['passed'] else 'FAIL'}** (0 false, 0 missed, 0 duplicate; D-198)", "",
        f"- **False posts: {len(s['false_posts'])}** (target 0)",
        f"- **Missed posts: {len(s['missed_posts'])}** of {posts} expected posts (target 0): "
        f"{len(s['missed_posts']) - timeouts} logic, {timeouts} timeout (no judge output or \"check incomplete\")",
        f"- **Duplicate posts: {len(s['duplicates'])}** (target 0)", "",
        "| category | runs | posted | false posts | missed posts | duplicates |", "|---|---|---|---|---|---|",
    ]
    for cat, c in sorted(by_cat.items()):
        lines.append(f"| {cat} | {c['n']} | {c['post']} | {c['false']} | {c['missed']} | {c['dup']} |")
    logic = [x for x in s["missed_posts"] if not x["missed_timeout"]]
    for title, items in (("False posts", s["false_posts"]), ("Missed posts (logic)", logic),
                         ("Missed posts (timeout)", s["missed_timeouts"]), ("Duplicate posts", s["duplicates"])):
        lines += ["", f"## {title}", ""]
        lines += [f"- {x['id']} run {x['run']} ({x['category']}): {x['action']} {x['group'] or ''} · {x['reason']}"
                  for x in items] or ["- none"]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


async def run_runtime_case(ctx, case: dict, run_no: int) -> dict:
    """D-198: the case in a real session: its questions and verified drafts seeded, the shown one in the host slot,
    the line submitted; after the publish window, every host-answer message with its state."""
    from app.pipelines.runtime import create_session
    from app.pipelines.utterances import operator_switch

    import logging

    s = await create_session(ctx, next(iter(ctx.pack.runsheets)))
    rt = await ctx.runtimes.get(s.session_id)
    rt.pd.agent = None
    decisions: list[str] = []  # the runtime's own "host answer ..." log lines of this session, as the reason

    class _Decisions(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            msg = record.getMessage()
            if rt.sid in msg and "answer" in msg:
                decisions.append(msg.replace(rt.sid + " ", ""))

    handler = _Decisions(logging.INFO)
    log = logging.getLogger("app.pipelines.utterances")
    log.setLevel(logging.INFO)  # cases run concurrently: the level is set once, each handler keeps its own session
    log.addHandler(handler)
    try:
        await rt.start()
        if (await rt.current_segment()).product_id != case["current_product_id"]:
            await operator_switch(rt, case["current_product_id"])
        now = rt.now()
        qs = case["context"]["open_questions"]
        async with rt.lock:
            for q in qs:
                await rt.save_answer(_answer(q))
                await rt.save_group(_group(q, case["current_product_id"]).model_copy(
                    update={"first_at": now, "last_at": now}))
            # every open question of the case is offered to the judge, as in the case context: the shown one first,
            # the others behind it (a question about the product not on air is offered only from a host slot)
            sess = await rt.load_session()
            ids = sorted((q["group_id"] for q in qs), key=lambda g: g != case["shown_group_id"])
            sess.host_slots = [HostSlot(group_id=g, on_host_since=now) for g in ids]
            await rt.save_session(sess)
        await rt.utterances.submit(case["utterance"], source="injected", speech_end_at=rt.now(), scenario="eval")
        await rt.utterances.drain()
        wait_ms = rt.settings.PUBLISH_CANCEL_WINDOW_MS + 500
        if hasattr(rt.ctx.scheduler, "advance"):  # tests: a manual scheduler
            await rt.ctx.scheduler.advance(wait_ms)
        else:
            await asyncio.sleep(wait_ms / 1000)
        msgs = await rt.ctx.store.query(rt.path("messages"), Message)
        calls = await rt.ctx.store.query(rt.path("agent_calls"), AgentCall)
        return {"id": case["case_id"], "run": run_no, "reason": " | ".join(decisions) or "no decision logged",
                "calls": [{"agent": c.agent, "status": c.status, "output": c.output} for c in calls
                          if c.agent in ("compliance_judge", "context_judge", "fact_checker")],
                "posts": [{"group": m.group_id, "state": m.state} for m in msgs if m.kind == "host_answer"]}
    finally:
        log.removeHandler(handler)
        await ctx.runtimes.drop(rt.sid)


async def run_runtime(cases: list[dict], runs: int, concurrency: int) -> list[dict]:
    from eval_holdout_sequences import ReplayClock

    from app.context import build_context
    from app.scheduler import AsyncScheduler

    settings = Settings(LLM_PROVIDER="vertex", STT_PROVIDER="mock", STORE="memory", RETRIEVER="local",
                        JUDGE_MODE="split3")
    clock = ReplayClock()
    ctx = build_context(settings, clock=clock, scheduler=AsyncScheduler(clock))
    sem = asyncio.Semaphore(concurrency)
    raw: list[dict] = []

    async def one(case: dict, run_no: int) -> dict:
        async with sem:
            return await run_runtime_case(ctx, case, run_no)

    try:
        await ctx.llm.warm_up()
        for run_no in range(runs):
            raw += await asyncio.gather(*(one(c, run_no) for c in cases))
            print(f"run {run_no + 1}/{runs} done")
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
        await ctx.llm.aclose()
    return raw


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--out", type=Path, default=EVAL_DIR / "verbal-post.md")
    ap.add_argument("--from-json", type=Path, default=None, help="re-score saved outputs without calling the models")
    ap.add_argument("--cases", default=CASES, help="case file in data/eval, e.g. verbal_post_holdout.jsonl")
    ap.add_argument("--runtime", action="store_true", help="replay each case in a real session; read committed posts")
    args = ap.parse_args()
    cases = load_cases(args.cases)
    if args.from_json:
        raw = json.loads(args.from_json.read_text(encoding="utf-8"))
    else:
        raw = (await run_runtime(cases, args.runs, args.concurrency) if args.runtime
               else await run("split3", args.runs, args.concurrency, cases))
        args.out.with_suffix(".json").write_text(json.dumps(raw, ensure_ascii=False) + "\n", encoding="utf-8",
                                                 newline="\n")
    s = score(raw, cases)
    write_report(s, cases, args.out)
    print(f"{'PASS' if s['passed'] else 'FAIL'} false posts: {len(s['false_posts'])} · missed posts: "
          f"{len(s['missed_posts'])} ({len(s['missed_timeouts'])} timeout) · duplicates: {len(s['duplicates'])}")
    return 0 if s["passed"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
