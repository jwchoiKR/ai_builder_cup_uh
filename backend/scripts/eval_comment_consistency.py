"""Comment consistency eval: the same viewer comment, sent again and again, must end the same way, for any product.

Accuracy evals send each comment once. This one sends each comment `--runs` times, every time on a fresh session of
the show (no triage cache, no answer cache, no open question to join), through the real comment pipeline, and reports
how often the runs agree, stage by stage:

    triage    kind, needs_approval, approval_reason, product   (the decision that routes the question)
    wording   the normalised English question                  (it is the search query and the answer-cache key)
    evidence  the passages the composer was given
    draft     grounded, needs_human                            (is there a usable draft, may it post by itself)
    outcome   where the question ended: posted by itself, the host's card, the operator's list (with or without a
              draft), a reaction, hidden, or the fixed "cannot answer" reply

A question is consistent when every run has the same outcome. For one that is not, the report names the first stage
whose value differs between runs: that is where to look. A run in which a model call failed (a timeout, a 429) is
counted apart: it says something about the service, not about the logic.

The question file holds no product: every question reads "it" or "this", so the same file runs on any onboarded
product (`--show`, repeatable). With two or more shows the report adds how often the triage decision of a question is
the same on every product (it is made from the comment alone, so it should be).

    uv run python scripts/eval_comment_consistency.py --show prd_xxxxxxxxxxxx:reg_xxxxxxxxxxxx --runs 5 \
        --out ../docs/eval/comment-consistency.md
    uv run python scripts/eval_comment_consistency.py --local ../my_products --runs 5   # products not onboarded yet
    uv run python scripts/eval_comment_consistency.py --compare a.json b.json      # two arms side by side

`--local DIR` runs products straight from a folder, without the onboarding bucket or the search data store: one
sub-folder per product with its PDF and `info.json` (brand, product_name, currency, list_price, live_price, points:
what onboarding's read stores), and `DIR/regulation.pdf` for all of them. A new kind of product can be checked this
way before it is onboarded. Its document is read whole (VERTEX_EVIDENCE=document); one longer than
WHOLE_DOCUMENT_MAX_CHARS would need the search, which does not know a local product.

Paid model and search calls (never on --help or --compare): about 2 model calls and 1 search per run. One arm per
run: the settings come from the environment (COMMENT_SEED, VERTEX_EVIDENCE, TRIAGE_MODEL, ...).
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import REPO_DIR, Settings  # noqa: E402

ARM_KEYS = ("COMMENT_SEED", "VERTEX_EVIDENCE", "WHOLE_DOCUMENT_MAX_CHARS", "ANSWER_RETRIEVER", "TRIAGE_MODEL", "TRIAGE_THINKING",
            "LLM_QUALITY_MODEL", "COMPOSER_THINKING", "MODEL_ARMOR_ENABLED", "INJECTION_REPLY", "SENSITIVE_APPROVAL")
STAGES = ("triage", "wording", "evidence", "draft", "outcome")
SETTLE_S = 90
GRACE_S = 2.5  # past STREAM_GRACE_SEC, so the comment has its product on air


# ---- one run -----------------------------------------------------------------------------------------


def outcome(row: dict) -> str:
    """Where the comment ended, as the viewer, the host and the operator see it."""
    if row["visibility"] == "hidden":
        return "hidden"
    if row["notice"]:
        return "cannot_answer_reply"
    if row["kind"] != "question":
        return row["kind"] or "pending"
    if "ai_answer" in row["reply_kinds"]:
        return "posted_by_itself"
    draft = "with_draft" if row["grounded"] else "no_draft"
    if row["route"] == "HOST":
        return f"host_card_{draft}"
    if row["route"] == "OPERATOR":
        return f"operator_{draft}"
    return f"{(row['route'] or 'none').lower()}_{row['status']}"


def signature(row: dict) -> dict[str, str]:
    """The value of each stage in one run, as a string two runs can be compared by."""
    return {
        "triage": json.dumps([row["kind"], row["needs_approval"], row["approval_reason"], row["product_id"]]),
        "wording": row["canonical_question"] or "",
        "evidence": json.dumps(row["evidence"]),
        "draft": json.dumps([row["grounded"], row["needs_human"]]),
        "outcome": outcome(row),
    }


async def _settle(rt) -> None:
    from app.models.session import Comment

    until = time.monotonic() + SETTLE_S
    while time.monotonic() < until:
        pending = [g for g in await rt.groups() if g.status in ("new", "composing")]
        waiting = [c for c in await rt.ctx.store.query(rt.path("comments"), Comment) if c.kind == "pending"]
        if not pending and not waiting:
            await asyncio.sleep(3)  # a post's cancel window ends
            return
        await asyncio.sleep(0.5)


async def run_once(ctx, searches: dict[str, list[str]], show: str, question: dict, run_no: int, show_mode: str) -> dict:
    from app.models.session import Answer, CommentAnalysis, Message
    from app.pipelines import comments as ops
    from app.pipelines.runtime import create_session

    s = await create_session(ctx, "", show_mode, release_id=show)
    rt = await ctx.runtimes.get(s.session_id)
    rt.pd.agent = None
    try:
        await rt.start()
        await asyncio.sleep(GRACE_S)
        c = await ops.submit_comment(rt, author_id=f"u_eval_{run_no}", author_name="Viewer", text=question["text"],
                                     source="script", scenario="eval")
        await _settle(rt)
        c = await rt.get_comment(c.comment_id)
        analyses = [a for a in await rt.ctx.store.query(rt.path("analyses"), CommentAnalysis)
                    if a.comment_id == c.comment_id]
        a = analyses[0] if analyses else None
        triage = a.output if a else {}
        g = await rt.get_group(c.group_id) if c.group_id else None
        answers = await rt.ctx.store.query(rt.path("answers"), Answer)
        draft = next((x for x in answers if g and x.answer_id == g.answer_id), None)
        replies = [m for m in await rt.ctx.store.query(rt.path("messages"), Message)
                   if c.comment_id in m.reply_to_comment_ids and m.state != "cancelled"]
        product = rt.catalog.get_product(g.product_id).name if g and g.product_id else ""
        return {
            "show": show, "id": question["id"], "run": run_no, "kind": c.kind, "visibility": c.visibility,
            "source": a.source if a else None, "armor": c.armor, "signal": c.signal,
            "needs_approval": triage.get("needs_approval"), "approval_reason": triage.get("approval_reason"),
            "intent": g.intent if g else triage.get("intent"), "product_id": g.product_id if g else None,
            "canonical_question": g.canonical_question if g else None,
            "route": g.route if g else None, "route_reason": g.route_reason if g else None,
            "status": g.status if g else None,
            "evidence": searches.get(f"{product} {g.canonical_question}") if g else None,
            "grounded": draft.verified if draft else None, "needs_human": draft.needs_human if draft else None,
            "draft_text": draft.text if draft else None,
            "reply_kinds": sorted(m.kind for m in replies), "notice": any(m.kind == "notice" for m in replies),
            "reply_text": replies[0].text if replies else None,
            # a model call that failed says nothing about the logic: reported apart
            "failed_call": (a is not None and a.source in ("fallback", "unscreened"))
                           or (g is not None and g.status == "needs_review" and g.route_reason == "no_verified_answer"
                               and draft is None),
        }
    finally:
        await ctx.runtimes.drop(rt.sid)


def local_shows(folder: Path) -> tuple[object, list[str]]:
    """A bucket in memory holding the folder's products as onboarding would have stored them, and their show keys.
    A product's id is made from its folder name, so it is the same id on every run."""
    import hashlib

    from app.onboarding.storage import MemoryBucket

    bucket = MemoryBucket()
    rid = "reg_" + hashlib.sha1(b"regulation").hexdigest()[:12]
    bucket.upload(f"regulations/{rid}/regulation.pdf", (folder / "regulation.pdf").read_bytes(), create_only=True)
    shows = []
    for d in sorted(x for x in folder.iterdir() if x.is_dir()):
        pid = "prd_" + hashlib.sha1(d.name.encode()).hexdigest()[:12]
        for pdf in sorted(d.glob("*.pdf")):
            bucket.upload(f"products/{pid}/{pdf.name}", pdf.read_bytes(), create_only=True)
        info = json.loads((d / "info.json").read_text(encoding="utf-8"))
        bucket.upload(f"products/{pid}/approved.json", json.dumps({"product_id": pid, "info": info}).encode(),
                      create_only=False)
        shows.append(f"{pid}:{rid}")
        print(f"local product {d.name}: {pid}", flush=True)
    return bucket, shows


def record_searches(retriever) -> dict[str, list[str]]:
    """The passages each search returned, by query, so a run can say what its composer was given."""
    seen: dict[str, list[str]] = {}
    if retriever is None:
        return seen
    search = retriever.search

    async def recording(query: str, **kw):
        out = await search(query, **kw)
        # a written answer has a new id whenever its words change; a passage of the document keeps its id
        seen[query] = [p.passage_id for p in out]
        return out

    retriever.search = recording
    return seen


# ---- score -------------------------------------------------------------------------------------------


def failed(row: dict) -> bool:
    """A run that says nothing about the logic: a model call failed, or triage had not answered when the run was
    read (the comment is still pending: its call timed out and was waiting for another try)."""
    return bool(row["failed_call"]) or row["kind"] == "pending"


def _mode_share(values: list[str]) -> tuple[str, float]:
    top, n = collections.Counter(values).most_common(1)[0]
    return top, n / len(values)


def score(rows: list[dict], questions: list[dict]) -> dict:
    """Per show and question: how far its runs agree at each stage, and the first stage where they part."""
    expect = {q["id"]: q.get("expect") or {} for q in questions}
    cells: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for r in rows:
        cells[(r["show"], r["id"])].append(r)
    per_cell = []
    for (show, qid), runs in sorted(cells.items()):
        clean = [r for r in runs if not failed(r)] or runs
        sigs = [signature(r) for r in clean]
        share = {st: _mode_share([s[st] for s in sigs]) for st in STAGES}
        first = next((st for st in STAGES if share[st][1] < 1.0), None)
        want = expect[qid]
        right = [all(r.get(k) == v for k, v in want.items()) for r in clean] if want else []
        per_cell.append({
            "show": show, "id": qid, "runs": len(runs), "failed_calls": sum(failed(r) for r in runs),
            "consistent": share["outcome"][1] == 1.0, "share": {st: share[st][1] for st in STAGES},
            "mode": {st: share[st][0] for st in STAGES}, "first_split": first,
            "outcomes": dict(collections.Counter(s["outcome"] for s in sigs)),
            "replies": len({r["reply_text"] or r["draft_text"] or "" for r in clean}),
            "expected_ok": sum(right), "expected_n": len(right),
        })
    n = len(per_cell)
    by_show: dict[str, list[dict]] = collections.defaultdict(list)
    for c in per_cell:
        by_show[c["show"]].append(c)
    # the triage decision of one question on every product: made from the comment alone, so it should not move
    across: dict[str, set[str]] = collections.defaultdict(set)
    for c in per_cell:
        across[c["id"]].add(json.dumps(json.loads(c["mode"]["triage"])[:3]))  # without the product id
    shows = sorted(by_show)
    return {
        "cells": per_cell, "questions": len({c["id"] for c in per_cell}), "shows": shows,
        "runs": len(rows), "failed_calls": sum(failed(r) for r in rows),
        "consistent": sum(c["consistent"] for c in per_cell), "cells_n": n,
        "stage_consistent": {st: sum(c["share"][st] == 1.0 for c in per_cell) for st in STAGES},
        "mean_share": {st: (sum(c["share"][st] for c in per_cell) / n if n else 0.0) for st in STAGES},
        "first_split": dict(collections.Counter(c["first_split"] for c in per_cell if c["first_split"])),
        "per_show": {s: {"consistent": sum(c["consistent"] for c in cs), "n": len(cs)} for s, cs in by_show.items()},
        "same_decision_on_every_show": (sum(len(v) == 1 for v in across.values()), len(across)) if len(shows) > 1 else None,
        "expected": (sum(c["expected_ok"] for c in per_cell), sum(c["expected_n"] for c in per_cell)),
    }


def _pct(n: int, d: int) -> str:
    return f"{n}/{d} ({n / d:.1%})" if d else "0/0 (n/a)"


def write_report(s: dict, arm: dict, questions: list[dict], out: Path) -> None:
    text = {q["id"]: q["text"] for q in questions}
    lines = [
        "# Comment consistency", "",
        f"{s['questions']} questions × {len(s['shows'])} show(s) × runs = {s['runs']} runs, each on a fresh session.",
        f"Arm: `{json.dumps(arm, ensure_ascii=False)}`", "",
        "| | |", "|---|---|",
        f"| questions whose every run ended the same way | **{_pct(s['consistent'], s['cells_n'])}** |",
        *[f"| … same {st} in every run | {_pct(s['stage_consistent'][st], s['cells_n'])} (mean share of the most common "
          f"value {s['mean_share'][st]:.1%}) |" for st in STAGES],
        f"| runs with a failed model call (counted apart) | {_pct(s['failed_calls'], s['runs'])} |",
        f"| triage decision as expected (kind, needs_approval) | {_pct(*s['expected'])} |",
    ]
    if s["same_decision_on_every_show"]:
        lines.append(f"| questions with the same triage decision on every product | "
                     f"**{_pct(*s['same_decision_on_every_show'])}** |")
    lines += ["", "## Per show", "", "| show | consistent questions |", "|---|---|",
              *[f"| `{k}` | {_pct(v['consistent'], v['n'])} |" for k, v in s["per_show"].items()],
              "", "## Where inconsistent questions first part", "",
              "| stage | questions |", "|---|---|",
              *([f"| {st} | {s['first_split'][st]} |" for st in STAGES if st in s["first_split"]] or ["| none | 0 |"]),
              "", "## Questions that did not end the same way every time", ""]
    bad = [c for c in s["cells"] if not c["consistent"]]
    for c in bad:
        lines.append(f"- `{c['show']}` {c['id']} {text.get(c['id'], '')!r}: {c['outcomes']}; first split at "
                     f"**{c['first_split']}**; {c['replies']} different reply texts")
    lines += [] if bad else ["None."]
    lines += ["", "## Every question", "",
              "| show | id | question | outcome (runs) | triage | wording | evidence | draft | reply texts |",
              "|---|---|---|---|---|---|---|---|---|"]
    for c in s["cells"]:
        sh = c["share"]
        lines.append(f"| `{c['show'][:16]}` | {c['id']} | {text.get(c['id'], '')[:48]} | {c['outcomes']} | "
                     f"{sh['triage']:.0%} | {sh['wording']:.0%} | {sh['evidence']:.0%} | {sh['draft']:.0%} | {c['replies']} |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def compare(paths: list[Path]) -> str:
    """Two or more saved runs side by side: one line per arm."""
    head = "| arm | consistent | triage | wording | evidence | draft | failed calls |\n|---|---|---|---|---|---|---|"
    rows = []
    for p in paths:
        saved = json.loads(p.read_text(encoding="utf-8"))
        s = score(saved["rows"], saved["questions"])
        arm = ", ".join(f"{k}={v}" for k, v in saved["arm"].items() if k in ("COMMENT_SEED", "VERTEX_EVIDENCE"))
        rows.append(f"| {p.stem} ({arm}) | {_pct(s['consistent'], s['cells_n'])} | "
                    + " | ".join(_pct(s["stage_consistent"][st], s["cells_n"]) for st in STAGES[:4])
                    + f" | {_pct(s['failed_calls'], s['runs'])} |")
    return "\n".join([head, *rows])


# ---- main --------------------------------------------------------------------------------------------


def load_questions(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--show", action="append", default=[], help="an onboarded show, <product_id>:<regulation_id>; repeatable")
    ap.add_argument("--local", type=Path, default=None, help="a folder of products that are not onboarded (see above)")
    ap.add_argument("--questions", type=Path, default=REPO_DIR / "data" / "eval" / "consistency_questions.jsonl")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--concurrency", type=int, default=4, help="sessions at a time")
    ap.add_argument("--show-mode", default="team", choices=["solo", "team"])
    ap.add_argument("--only", default="", help="comma-separated question ids; empty = all")
    ap.add_argument("--out", type=Path, default=REPO_DIR / "docs/eval/comment-consistency.md")
    ap.add_argument("--from-json", type=Path, default=None, help="score a saved run again, no calls")
    ap.add_argument("--compare", type=Path, nargs="+", default=None, help="saved runs to put side by side, no calls")
    args = ap.parse_args()
    if args.compare:
        print(compare(args.compare))
        return 0
    if args.from_json:
        saved = json.loads(args.from_json.read_text(encoding="utf-8"))
        rows, arm, questions = saved["rows"], saved["arm"], saved["questions"]
    else:
        if not args.show and not args.local:
            ap.error("--show (an onboarded product's show key) or --local (a folder of products) is required")
        from app.context import build_context

        local = {}
        if args.local:
            from app.onboarding import storage

            bucket, shows = local_shows(args.local)
            storage.bucket_for = lambda name, project=None: bucket  # every bucket read of this run
            args.show += shows
            local = {"ONBOARDING_GCS_BUCKET": "local"}

        wanted = set(filter(None, args.only.split(",")))
        questions = [q for q in load_questions(args.questions) if not wanted or q["id"] in wanted]
        settings = Settings(LLM_PROVIDER="vertex", STT_PROVIDER="mock", STORE="memory",
                            COMMENT_RATE_LIMIT_PER_MIN=100000, **local)
        arm = {k: getattr(settings, k) for k in ARM_KEYS} | {"show_mode": args.show_mode, "runs": args.runs}
        ctx = build_context(settings)
        searches = record_searches(ctx.answer_retriever)
        sem = asyncio.Semaphore(args.concurrency)
        done = 0

        async def one(show: str, q: dict, n: int) -> dict:
            nonlocal done
            async with sem:
                r = await run_once(ctx, searches, show, q, n, args.show_mode)
                done += 1
                print(f"[{done}] {show[:16]} {q['id']} run {n}: {outcome(r)}", flush=True)
                return r

        try:
            await ctx.llm.warm_up()
            rows = list(await asyncio.gather(*(one(show, q, n) for show in args.show for q in questions
                                               for n in range(1, args.runs + 1))))
        finally:
            ctx.runtimes.shutdown()
            ctx.scheduler.shutdown()
            await ctx.llm.aclose()
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.with_suffix(".json").write_text(
            json.dumps({"arm": arm, "questions": questions, "rows": rows}, ensure_ascii=False) + "\n",
            encoding="utf-8", newline="\n")
    s = score(rows, questions)
    write_report(s, arm, questions, args.out)
    print(f"consistent {_pct(s['consistent'], s['cells_n'])} · "
          + " · ".join(f"{st} {_pct(s['stage_consistent'][st], s['cells_n'])}" for st in STAGES[:4])
          + f" · failed calls {_pct(s['failed_calls'], s['runs'])} → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
