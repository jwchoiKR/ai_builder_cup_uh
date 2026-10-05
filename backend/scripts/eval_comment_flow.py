"""Comment-flow eval (proof-plan): reaction vs question, clustering, routing, parallel draft, answers
and cache, on a real runtime per scenario.

Each scenario of `data/eval/comment_flow_cases.jsonl` runs on a fresh session. Events are replayed at
their `t_ms` on the wall clock (comments, promo_start, promo_end, document_change, host_confirm), then
the runtime settles and the session state is scored.

    uv run python scripts/eval_comment_flow.py --runs 1 --cases comment_flow_cases.jsonl \
        --out ../docs/eval/comment-flow.md
    uv run python scripts/eval_comment_flow.py --from-json ../docs/eval/comment-flow.json

Pass lines (fixed before results): kind 100%, must_not_merge violations 0, route 100%, stale or wrong
posted answers 0, HOST answers posted before the host confirmed 0, cache reuse 100% where expected, undelivered
answers 0.

D-199 (full review P1): every gold question is scored for its route, also one that never reached a group (a miss);
an answer counts as delivered only when a published message replies to the asker (AUTO, or HOST after the host
confirmed; `post_to_all_askers` means every asker); cache reuse counts only when exactly one AI draft served the
question and, where the answer is posted, every later asker got it.
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import datetime as dt
import itertools
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_holdout_sequences import ReplayClock  # noqa: E402

from app.config import REPO_DIR, Settings, get_settings  # noqa: E402
from app.context import build_context  # noqa: E402
from app.logic.verify import number_set  # noqa: E402
from app.models.session import Answer, Comment, CommentAnalysis, Message  # noqa: E402
from app.pipelines import comments as ops  # noqa: E402
from app.pipelines.runtime import ActionError, create_session  # noqa: E402
from app.pipelines.utterances import operator_switch  # noqa: E402
from app.scheduler import AsyncScheduler  # noqa: E402

SETTLE_S = 60  # at most this long after the last event for drafts to finish


class Pace:
    """Wall-clock pacing of the replay; tests swap in an instant one."""

    def now(self) -> float:
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


PACE = Pace()


def load_cases(name: str) -> list[dict]:
    path = get_settings().data_path / "eval" / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---- run ---------------------------------------------------------------------------------------------


async def _settle(rt) -> None:
    until = PACE.now() + SETTLE_S
    while PACE.now() < until:
        groups = await rt.groups()
        pending = [g for g in groups if g.status in ("new", "composing")]
        comments = [c for c in await rt.ctx.store.query(rt.path("comments"), Comment) if c.kind == "pending"]
        if not pending and not comments:
            await PACE.sleep(3)  # pending posts (2 s cancel window) finish
            return
        await PACE.sleep(0.5)


async def run_scenario(ctx, case: dict, run_no: int) -> dict:
    s = await create_session(ctx, next(iter(ctx.pack.runsheets)), case.get("show_mode", "solo"))
    rt = await ctx.runtimes.get(s.session_id)
    rt.pd.agent = None
    try:
        await rt.start()
        if (await rt.current_segment()).product_id != case["current_product_id"]:
            await operator_switch(rt, case["current_product_id"])
        for pid in case.get("active_promos", []):
            await rt.start_promo(pid if isinstance(pid, str) else pid["promo_id"])
        t0 = PACE.now()
        comment_ids: list[tuple[str, dict, str]] = []  # (comment_id, gold, text)
        event_at: dict[str, int] = {}  # event kind -> runtime ms
        confirms: dict[str, int] = {}  # cluster -> runtime ms of the host's confirmation
        for e in sorted(case["events"], key=lambda x: x["t_ms"]):
            wait = e["t_ms"] / 1000 - (PACE.now() - t0)
            if wait > 0:
                await PACE.sleep(wait)
            kind = e["type"]
            if kind == "comment":
                author = e.get("author", "Viewer")
                c = await ops.submit_comment(rt, author_id=f"u_{author.lower()}", author_name=author, text=e["text"],
                                             source="script", scenario="eval")
                comment_ids.append((c.comment_id, e.get("gold", {}), e["text"]))
            elif kind == "promo_start":
                await rt.start_promo(e["promo_id"])
                event_at["promo_start"] = rt.now()
            elif kind == "promo_end":
                try:
                    await rt.stop_promo(e["promo_id"], reason="expired")
                except ActionError:
                    pass  # its own timer already ended it (a slow run)
                event_at["promo_end"] = rt.now()
            elif kind == "document_change":
                pid = e["product_id"]
                ctx.retriever.replace_product(pid, [p for p in ctx.pack.passages if p.product_id == pid])
                rt.sync_doc_version()
                event_at["document_change"] = rt.now()
            elif kind == "host_confirm":
                gold_ids = [cid for cid, g, _ in comment_ids if g.get("cluster") == e["cluster"]]
                groups = {g.group_id for g in await rt.groups() if set(g.member_comment_ids) & set(gold_ids)}
                # the confirmation time is when the host pressed, before approve() posts (it took 16 ms once,
                # and the post then counted as "before the host confirmed")
                confirms[e["cluster"]] = rt.now()
                for gid in groups:
                    try:
                        await ops.approve(rt, gid)
                    except Exception as err:  # noqa: BLE001 - recorded, the eval goes on
                        print(f"{case['scenario_id']}: approve {gid} failed: {err}")
        await _settle(rt)
        store, path = rt.ctx.store, rt.path
        comments = {c.comment_id: c for c in await store.query(path("comments"), Comment)}
        analyses = {a.comment_id: a for a in await store.query(path("analyses"), CommentAnalysis)}
        return {
            "id": case["scenario_id"], "run": run_no, "event_at": event_at, "confirms": confirms,
            "comments": [{"comment_id": cid, "gold": gold, "text": text, "kind": comments[cid].kind,
                          "received_at": comments[cid].received_at,
                          "triage_ms": analyses[cid].latency_ms if cid in analyses else None}
                         for cid, gold, text in comment_ids if cid in comments],
            "groups": [g.model_dump(mode="json") for g in await rt.groups()],
            "answers": [a.model_dump(mode="json") for a in await store.query(path("answers"), Answer)],
            "messages": [m.model_dump(mode="json") for m in await store.query(path("messages"), Message)],
        }
    finally:
        await ctx.runtimes.drop(rt.sid)


# ---- score -------------------------------------------------------------------------------------------


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def _includes(text: str, want: str) -> bool:
    """Substring match; money and amounts compare by number ("S$36" = "S$36.00")."""
    if _norm(want) in _norm(text):
        return True
    nums = number_set(want)
    return bool(nums) and nums <= number_set(text) and _norm(re.sub(r"[\d.$S]", "", want)).strip() in _norm(text)


def score_scenario(case: dict, r: dict) -> dict:
    exp = case["expect"]
    group_of = {cid: g["group_id"] for g in r["groups"] for cid in g["member_comment_ids"]}
    groups = {g["group_id"]: g for g in r["groups"]}
    answers = {a["answer_id"]: a for a in r["answers"]}
    out: dict = {"id": r["id"], "run": r["run"], "problems": []}

    # (a) kind
    kinds = [(c["gold"].get("kind"), c["kind"], c) for c in r["comments"] if c["gold"].get("kind")]
    out["kind_total"] = len(kinds)
    out["kind_ok"] = sum(g == k for g, k, _ in kinds)
    odd = [(g, k) for g, k, c in kinds if len(re.sub(r"[^A-Za-z]", "", c["text"])) <= 3]
    out["kind_short_total"], out["kind_short_ok"] = len(odd), sum(g == k for g, k in odd)
    for g, k, c in kinds:
        if g != k:
            out["problems"].append(f"kind {c['comment_id']}: {k} (gold {g})")

    # (b) clustering, pairwise over gold question comments
    qs = [c for c in r["comments"] if c["gold"].get("cluster") and c["comment_id"] in group_of]
    may = {frozenset(p) for p in exp.get("may_merge", [])}
    tp = fp = fn = 0
    for a, b in itertools.combinations(qs, 2):
        same_gold = a["gold"]["cluster"] == b["gold"]["cluster"]
        same_pred = group_of[a["comment_id"]] == group_of[b["comment_id"]]
        if not same_gold and frozenset((a["gold"]["cluster"], b["gold"]["cluster"])) in may:
            continue
        tp += same_gold and same_pred
        fp += same_pred and not same_gold
        fn += same_gold and not same_pred
    out["pair_precision"] = tp / (tp + fp) if tp + fp else 1.0
    out["pair_recall"] = tp / (tp + fn) if tp + fn else 1.0
    clusters_in: dict[str, set[str]] = collections.defaultdict(set)
    for c in qs:
        clusters_in[group_of[c["comment_id"]]].add(c["gold"]["cluster"])
    out["must_not_merge_violations"] = 0
    for x, y in exp.get("must_not_merge", []):
        if any({x, y} <= cl for cl in clusters_in.values()):
            out["must_not_merge_violations"] += 1
            out["problems"].append(f"merged {x} with {y}")

    # (c) route and sensitive. D-199: every gold question, also one that never reached a group
    out["route_total"] = out["route_ok"] = 0
    for c in r["comments"]:
        gold = c["gold"].get("route")
        if not gold or not c["gold"].get("cluster"):
            continue
        if c["comment_id"] not in group_of:
            out["route_total"] += 1
            out["problems"].append(f"route {c['comment_id']} ({c['gold']['cluster']}): no group, kind {c['kind']} "
                                   f"(gold {gold})")
            continue
        g = groups[group_of[c["comment_id"]]]
        verified = any(a["verified"] for a in answers.values() if a["group_id"] == g["group_id"])
        ok = (not verified and g["status"] != "auto_answered") if gold == "NO_EVIDENCE" else g["route"] == gold
        out["route_total"] += 1
        out["route_ok"] += ok
        if not ok:
            out["problems"].append(f"route {c['comment_id']} ({c['gold']['cluster']}): {g['route']}/{g['status']} "
                                   f"(gold {gold})")

    # (d) parallelism: time to a verified draft vs triage alone
    drafts, triages = [], []
    for gid, g in groups.items():
        first = min((c for c in r["comments"] if c["comment_id"] in g["member_comment_ids"]),
                    key=lambda c: c["received_at"], default=None)
        ans = sorted((a for a in answers.values() if a["group_id"] == gid and a["verified"]), key=lambda a: a["created_at"])
        if first and ans:
            drafts.append(ans[0]["created_at"] - first["received_at"])
            if first["triage_ms"] is not None:
                triages.append(first["triage_ms"])
    out["draft_ms"], out["triage_ms"] = drafts, triages

    # (e) answers and (f) cache
    out["stale_or_wrong_posts"] = out["host_posted_before_confirm"] = 0
    out["cache_expected"] = out["cache_ok"] = 0
    out["delivery_expected"] = out["undelivered"] = 0
    posted = [m for m in r["messages"] if m["state"] == "published"]
    for name, spec in (exp.get("clusters") or exp.get("all_clusters") or {}).items():
        if not isinstance(spec, dict):
            continue
        cids = {c["comment_id"] for c in qs if c["gold"]["cluster"] == name}
        golds = [c["gold"] for c in qs if c["gold"]["cluster"] == name]
        gids = {group_of[c] for c in cids}
        msgs = [m for m in posted if set(m["reply_to_comment_ids"]) & cids]
        texts = [m["text"] for m in msgs] or [a["text"] for a in answers.values() if a["group_id"] in gids]
        must = {w for g in golds for w in g.get("answer_must_include", [])}
        must_not = {w for g in golds for w in g.get("answer_must_not_include", [])}
        for m_text in texts:
            missing = [w for w in must if not _includes(m_text, w)]
            banned = [w for w in must_not if _norm(w) in _norm(m_text)]
            if (missing or banned) and msgs:
                out["stale_or_wrong_posts"] += 1
                out["problems"].append(f"{name}: posted '{m_text}' missing {missing} banned {banned}")
        route = golds[0].get("route") if golds else None
        # D-199: delivered = a published reply to the asker; AUTO at once, HOST once the host confirmed
        replied = {cid for m in msgs for cid in m["reply_to_comment_ids"]}
        due = route == "AUTO" or (route == "HOST" and name in r["confirms"])
        if due and cids:
            every = spec.get("post_to_all_askers") or spec.get("post_to_all_askers_after_host_confirm")
            out["delivery_expected"] += 1
            if not (cids <= replied if every else replied & cids):
                out["undelivered"] += 1
                out["problems"].append(f"{name}: answer not delivered to {sorted(cids - replied)} (route {route})")
        if route == "HOST":
            confirm = r["confirms"].get(name)
            early = [m for m in msgs if confirm is None or m["published_at"] < confirm]
            out["host_posted_before_confirm"] += len(early)
            if early:
                out["problems"].append(f"{name}: host answer posted before the host confirmed")
        if route in ("OPERATOR", "NO_EVIDENCE") and any(m["kind"] == "ai_answer" for m in msgs):
            out["stale_or_wrong_posts"] += 1
            out["problems"].append(f"{name}: auto-posted although route is {route}")
        after = spec.get("must_reanswer_after")
        if after and after in r["event_at"]:
            at = r["event_at"][after]
            for m in msgs:
                src = next((a for a in answers.values() if a["group_id"] == m["group_id"] and a["text"] == m["text"]), None)
                if m["published_at"] >= at and src is not None and src["created_at"] < at:
                    out["stale_or_wrong_posts"] += 1
                    out["problems"].append(f"{name}: posted an answer drafted before {after}")
        if spec.get("later_askers_source") == "cache" and len(cids) > 1:
            out["cache_expected"] += 1
            limit = r["event_at"].get(after) if after else None
            ai = [a for a in answers.values() if a["group_id"] in gids and a["origin"] == "ai"
                  and (limit is None or a["created_at"] < limit)]
            # D-199: a hit is observed: one draft served the question, and every later asker got it where it posts
            later_served = not due or cids <= replied
            if len(ai) == 1 and later_served:
                out["cache_ok"] += 1
            else:
                out["problems"].append(f"{name}: {len(ai)} drafts for one question, later askers served "
                                       f"{later_served} (cache reuse not observed)")
    return out


def score(raw: list[dict], cases: list[dict]) -> dict:
    by_id = {c["scenario_id"]: c for c in cases}
    rows = [score_scenario(by_id[r["id"]], r) for r in raw]
    tot = lambda k: sum(x[k] for x in rows)  # noqa: E731
    s = {
        "rows": rows, "runs": len({x["run"] for x in rows}),
        "kind": tot("kind_ok") / max(1, tot("kind_total")),
        "kind_short": tot("kind_short_ok") / max(1, tot("kind_short_total")),
        "route": tot("route_ok") / max(1, tot("route_total")),
        "must_not_merge": tot("must_not_merge_violations"),
        "stale_or_wrong": tot("stale_or_wrong_posts"),
        "host_early": tot("host_posted_before_confirm"),
        "cache": tot("cache_ok") / max(1, tot("cache_expected")),
        "undelivered": tot("undelivered"), "delivery_expected": tot("delivery_expected"),
        "precision": sum(x["pair_precision"] for x in rows) / max(1, len(rows)),
        "recall": sum(x["pair_recall"] for x in rows) / max(1, len(rows)),
    }
    s["passed"] = (s["kind"] == 1 and s["must_not_merge"] == 0 and s["route"] == 1 and s["stale_or_wrong"] == 0
                   and s["host_early"] == 0 and s["cache"] == 1 and s["undelivered"] == 0)
    return s


def _p(values: list[int], q: float) -> str:
    if not values:
        return "–"
    v = sorted(values)
    return f"{v[min(len(v) - 1, round(q * (len(v) - 1)))] / 1000:.1f}s"


def write_report(s: dict, cases: list[dict], out: Path, name: str) -> None:
    rows = s["rows"]
    drafts = [d for x in rows for d in x["draft_ms"]]
    triages = [d for x in rows for d in x["triage_ms"]]
    lines = [
        "# Comment-flow eval", "",
        f"{dt.date.today().isoformat()} · `{name}` · {len(cases)} scenarios × {s['runs']} runs · real runtime per "
        "scenario, events replayed on the wall clock.", "",
        f"**{'PASS' if s['passed'] else 'FAIL'}** · kind {s['kind']:.1%} (100%; short or odd {s['kind_short']:.1%}) · "
        f"must_not_merge {s['must_not_merge']} (0) · route {s['route']:.1%} (100%) · stale or wrong posts "
        f"{s['stale_or_wrong']} (0) · host answers before confirm {s['host_early']} (0) · cache reuse "
        f"{s['cache']:.1%} (100%) · undelivered answers {s['undelivered']} of {s['delivery_expected']} (0)", "",
        f"Clustering (mean per scenario): pairwise precision {s['precision']:.1%}, recall {s['recall']:.1%}.", "",
        f"Parallelism: first comment to verified draft p50 {_p(drafts, .5)}, p95 {_p(drafts, .95)}; triage alone "
        f"p50 {_p(triages, .5)}, p95 {_p(triages, .95)}.", "",
        "| scenario | run | kind | route | pairs P/R | must_not_merge | stale/wrong | host early | cache |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for x in rows:
        lines.append(f"| {x['id']} | {x['run']} | {x['kind_ok']}/{x['kind_total']} | {x['route_ok']}/{x['route_total']} | "
                     f"{x['pair_precision']:.0%}/{x['pair_recall']:.0%} | {x['must_not_merge_violations']} | "
                     f"{x['stale_or_wrong_posts']} | {x['host_posted_before_confirm']} | "
                     f"{x['cache_ok']}/{x['cache_expected']} |")
    lines += ["", "## Problems", ""]
    lines += [f"- {x['id']} run {x['run']}: {p}" for x in rows for p in x["problems"]] or ["- none"]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def refresh_gold(raw: list[dict], cases: list[dict]) -> list[dict]:
    """Re-scoring saved outputs: take each comment's gold from the current case file (labels may have been
    fixed since the run), matched by scenario and comment text in order."""
    for r in raw:
        case = next((c for c in cases if c["scenario_id"] == r["id"]), None)
        if case is None:
            continue
        pool = collections.defaultdict(list)
        for e in case["events"]:
            if e.get("type") == "comment":
                pool[e["text"]].append(e.get("gold", {}))
        for c in r["comments"]:
            if pool.get(c["text"]):
                c["gold"] = pool[c["text"]].pop(0)
    return raw


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--cases", default="comment_flow_cases.jsonl")
    ap.add_argument("--out", type=Path, default=REPO_DIR / "docs/eval/comment-flow.md")
    ap.add_argument("--concurrency", type=int, default=4, help="scenarios at a time")
    ap.add_argument("--from-json", type=Path, default=None)
    args = ap.parse_args()
    cases = load_cases(args.cases)
    if args.from_json:
        raw = refresh_gold(json.loads(args.from_json.read_text(encoding="utf-8")), cases)
    else:
        settings = Settings(LLM_PROVIDER="vertex", STT_PROVIDER="mock", STORE="memory", RETRIEVER="local",
                            JUDGE_MODE="split3")
        clock = ReplayClock()
        ctx = build_context(settings, clock=clock, scheduler=AsyncScheduler(clock))
        sem = asyncio.Semaphore(args.concurrency)

        async def one(case: dict, run_no: int) -> dict:
            async with sem:
                r = await run_scenario(ctx, case, run_no)
                print(f"{case['scenario_id']} run {run_no + 1}: done")
                return r

        raw = []
        try:
            await ctx.llm.warm_up()
            # a document change bumps the shared retriever's version, which changes every running scenario's
            # answer keys: those scenarios run alone, after the others
            alone = [c for c in cases if any(e.get("type") == "document_change" for e in c["events"])]
            together = [c for c in cases if c not in alone]
            for run_no in range(args.runs):
                raw += await asyncio.gather(*(one(c, run_no) for c in together))
                for c in alone:
                    raw.append(await one(c, run_no))
        finally:
            ctx.runtimes.shutdown()
            ctx.scheduler.shutdown()
            await ctx.llm.aclose()
        args.out.with_suffix(".json").write_text(json.dumps(raw, ensure_ascii=False) + "\n", encoding="utf-8",
                                                 newline="\n")
    s = score(raw, cases)
    write_report(s, cases, args.out, args.cases)
    print(f"{'PASS' if s['passed'] else 'FAIL'} kind {s['kind']:.1%} route {s['route']:.1%} must_not_merge "
          f"{s['must_not_merge']} stale/wrong {s['stale_or_wrong']} host early {s['host_early']} cache {s['cache']:.1%}")
    return 0 if s["passed"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
