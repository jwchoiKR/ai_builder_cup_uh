"""Spoken-answer auto-post evaluation (D-110), data/eval/verbal_post_cases.jsonl.

Runs the production agents (split3: compliance, context, facts) on each host utterance with the
case's open questions and verified drafts, then applies the real publish decision
(`logic.publish.decide`) as the runtime would. The target is zero false posts: a post where the case
expects none, or a post to a question the case did not mark. Missed posts are allowed and counted.

    uv run python scripts/eval_verbal_post.py --runs 3          # docs/eval/verbal-post.md and .json
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

from app.config import get_settings  # noqa: E402
from app.logic.publish import decide  # noqa: E402
from app.models.agent_io import FactCheckOutput, UtteranceJudgeOutput  # noqa: E402
from app.models.session import Answer, QuestionGroup  # noqa: E402

CASES = "verbal_post_cases.jsonl"


def load_cases() -> list[dict]:
    path = get_settings().data_path / "eval" / CASES
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _group(q: dict, product_id: str) -> QuestionGroup:
    return QuestionGroup(group_id=q["group_id"], product_id=q.get("product_id", product_id), intent="other",
                         condition_slots={}, canonical_question=q["canonical_question"], member_comment_ids=["c"],
                         unique_author_ids=["u"], first_at=0, last_at=0, route="HOST", route_reason="eval",
                         status="ready", answer_id=f"ans_{q['group_id']}")


def _answer(q: dict) -> Answer:
    return Answer(answer_id=f"ans_{q['group_id']}", group_id=q["group_id"], text=q["suggested_answer"], citations=[],
                  origin="ai", verified=True, verify_errors=[], needs_human=False, created_at=0)


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
    d = decide(judge, offered, group, offered.get(gid), high_alert_active=False, facts=facts,
               utterance=case["utterance"])
    return d.action, d.group_id, d.reason


def score(raw: list[dict], cases: list[dict]) -> dict:
    by_id = {c["case_id"]: c for c in cases}
    rows = []
    for r in raw:
        case = by_id[r["id"]]
        exp = case["expected"]
        action, gid, reason = decision_for(case, r)
        posted = action == "post"
        ok_groups = {exp.get("matched_group"), *exp.get("also_ok_groups", [])}  # one sentence may answer two
        false_post = posted and (not exp["post"] or gid not in ok_groups)
        rows.append({"id": r["id"], "run": r["run"], "category": exp["category"], "expected_post": exp["post"],
                     "action": action, "group": gid, "reason": reason, "false_post": false_post,
                     "missed_post": exp["post"] and not (posted and gid in ok_groups),
                     "status": r.get("ctx_status")})
    return {"rows": rows,
            "false_posts": [x for x in rows if x["false_post"]],
            "missed_posts": [x for x in rows if x["missed_post"]],
            "runs": len({x["run"] for x in rows})}


def write_report(s: dict, cases: list[dict], out: Path) -> None:
    by_cat: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for x in s["rows"]:
        c = by_cat[x["category"]]
        c["n"] += 1
        c["post"] += x["action"] == "post"
        c["false"] += x["false_post"]
        c["missed"] += x["missed_post"]
    posts = sum(1 for x in s["rows"] if x["expected_post"])
    lines = [
        "# Spoken-answer auto-post (D-110)", "",
        f"{dt.date.today().isoformat()} · {len(cases)} cases × {s['runs']} runs · production agents (split3) "
        "+ `logic.publish.decide`. Cases: `data/eval/verbal_post_cases.jsonl`.", "",
        f"- **False posts: {len(s['false_posts'])}** (target 0)",
        f"- Missed posts: {len(s['missed_posts'])} of {posts} expected posts (allowed; the card stays and "
        "\"Confirm and post\" still works)", "",
        "| category | runs | posted | false posts | missed posts |", "|---|---|---|---|---|",
    ]
    for cat, c in sorted(by_cat.items()):
        lines.append(f"| {cat} | {c['n']} | {c['post']} | {c['false']} | {c['missed']} |")
    for title, items in (("False posts", s["false_posts"]), ("Missed posts", s["missed_posts"])):
        lines += ["", f"## {title}", ""]
        lines += [f"- {x['id']} run {x['run']} ({x['category']}): {x['action']} {x['group'] or ''} · {x['reason']}"
                  for x in items] or ["- none"]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--out", type=Path, default=EVAL_DIR / "verbal-post.md")
    ap.add_argument("--from-json", type=Path, default=None, help="re-score saved outputs without calling the models")
    args = ap.parse_args()
    cases = load_cases()
    if args.from_json:
        raw = json.loads(args.from_json.read_text(encoding="utf-8"))
    else:
        raw = await run("split3", args.runs, args.concurrency, cases)
        args.out.with_suffix(".json").write_text(json.dumps(raw, ensure_ascii=False) + "\n", encoding="utf-8",
                                                 newline="\n")
    s = score(raw, cases)
    write_report(s, cases, args.out)
    print(f"false posts: {len(s['false_posts'])} · missed posts: {len(s['missed_posts'])}")
    return 1 if s["false_posts"] else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
