"""Comment hold-out eval: kind, category, product, route, grouping, auto answers and reply latency on unseen comments.

`data/eval/comment_holdout_raw.jsonl` (240 comments in 12 scenes, EN and other languages) was written without reading
the prompts; `comment_holdout_gold.jsonl` was labelled independently from the meaning, the product sheets and
`intents.json`. Each scene runs on a fresh session with its product on air; comments are sent in file order, `--gap-ms`
apart, through the real pipeline (settings from the environment, so one arm per run), then the session is scored.

    uv run python scripts/eval_comment_holdout.py --out ../docs/eval/comment-holdout.md
    uv run python scripts/eval_comment_holdout.py --from-json ../docs/eval/comment-holdout.json

Reported, never averaged away: wrong merges (two questions with different gold groups in one group), auto posts the
gold does not allow, and any message that replies to an injection comment, each with its ids.
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import datetime as dt
import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_comment_flow import PACE, _settle, show_session  # noqa: E402
from eval_holdout_sequences import ReplayClock  # noqa: E402

from app.config import REPO_DIR, Settings, get_settings  # noqa: E402
from app.context import build_context  # noqa: E402
from app.logic.verify import number_set  # noqa: E402
from app.models.session import Answer, Comment, CommentAnalysis, Message, Transcript  # noqa: E402
from app.pipelines import comments as ops  # noqa: E402
from app.pipelines.utterances import operator_switch  # noqa: E402
from app.scheduler import AsyncScheduler  # noqa: E402

ARM_KEYS = ("TRIAGE_MODEL", "TRIAGE_RETRIES",
            "TRIAGE_TIMEOUT_MS", "SENSITIVE_APPROVAL", "PREFILTER", "COMMENT_PRODUCT", "GROUP_JOIN", "TRIAGE_THINKING",
            "LLM_FAST_MODEL", "LLM_QUALITY_MODEL", "COMPOSER_THINKING", "MODEL_ARMOR_ENABLED",
            "ANSWER_RETRIEVER", "VERTEX_EVIDENCE", "COMMENT_SEED")


def load(name: str) -> list[dict]:
    path = get_settings().data_path / "eval" / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---- run ---------------------------------------------------------------------------------------------


def _host_said(rt, text: str, segment_id: str) -> None:
    """The host's last line, as the comment pipeline reads it (`recent_host_line`), without judging it."""
    t = Transcript(transcript_id=rt.new_id("tr_"), text=text, is_final=True, speech_end_at=rt.now(),
                   received_at=rt.now(), source="injected", segment_id=segment_id)
    rt.utterances._prepared[t.transcript_id] = (t, text, None)


async def run_scene(ctx, scene: str, rows: list[dict], gap_ms: int, show_mode: str) -> dict:
    s, ids = await show_session(ctx, None, show_mode)
    rt = await ctx.runtimes.get(s.session_id)
    rt.pd.agent = None
    try:
        await rt.start()
        on_air = ids.get(rows[0]["on_air_product_id"], rows[0]["on_air_product_id"])
        if (await rt.current_segment()).product_id != on_air:
            await operator_switch(rt, on_air)
        await PACE.sleep(2.5)  # past STREAM_GRACE_SEC, so every comment has its product on air
        sent: list[tuple[str, str]] = []
        for row in rows:
            if row.get("recent_host_line"):
                _host_said(rt, row["recent_host_line"], (await rt.current_segment()).segment_id)
            author = row.get("author") or "Viewer"
            c = await ops.submit_comment(rt, author_id=f"u_{author.lower()}", author_name=author, text=row["text"],
                                         source="script", scenario="eval")
            sent.append((row["id"], c.comment_id))
            await PACE.sleep(gap_ms / 1000)
        await _settle(rt)
        store, path = rt.ctx.store, rt.path
        comments = {c.comment_id: c for c in await store.query(path("comments"), Comment)}
        analyses = {a.comment_id: a for a in await store.query(path("analyses"), CommentAnalysis)}
        groups = {g.group_id: g for g in await rt.groups()}
        answers = {a.answer_id: a for a in await store.query(path("answers"), Answer)}
        messages = await store.query(path("messages"), Message)
        out = []
        for hid, cid in sent:
            c, a = comments.get(cid), analyses.get(cid)
            g = groups.get(c.group_id) if c and c.group_id else None
            triage = a.output if a else {}
            replies = [m for m in messages if cid in m.reply_to_comment_ids]
            draft = answers.get(g.answer_id) if g and g.answer_id else None
            out.append({
                "id": hid, "kind": c.kind if c else None, "visibility": c.visibility if c else None,
                "hide_category": c.hide_category if c else None, "source": a.source if a else None,
                "intent": g.intent if g else triage.get("intent"), "product_id": g.product_id if g else None,
                "group_id": c.group_id if c else None, "route": g.route if g else None,
                "route_reason": g.route_reason if g else None, "status": g.status if g else None,
                "canonical_question": g.canonical_question if g else None,
                "language": triage.get("language"), "translation_en": triage.get("translation_en"),
                "signal": c.signal if c else None,
                "groups": sorted(x.group_id for x in groups.values() if cid in x.member_comment_ids),
                "triage_ms": a.latency_ms if a else None,
                "draft": {"text": draft.text, "verified": draft.verified, "errors": draft.verify_errors,
                          "citations": [x.get("passage_id") for x in draft.citations]} if draft else None,
                "replies": [{"kind": m.kind, "text": m.text, "state": m.state,
                             "ms": (m.published_at - c.received_at) if m.published_at and c else None}
                            for m in replies],
            })
        return {"scene": scene, "rows": out, "counters": dict(rt.counters),
                "reply_latencies": {k: list(v) for k, v in rt.reply_latencies.items()}}
    finally:
        await ctx.runtimes.drop(rt.sid)


# ---- score -------------------------------------------------------------------------------------------


def _pct(n: int, d: int) -> str:
    return f"{n}/{d} ({n / d:.1%})" if d else "0/0 (n/a)"


def _quantile(values: list[int], q: float) -> str:
    if not values:
        return "n/a"
    v = sorted(values)
    return f"{v[min(len(v) - 1, int(q * len(v)))] / 1000:.1f} s"


SET = "comment_holdout"  # --set: the file prefix of the raw comments, the gold and the rulings


def rulings() -> dict:
    """Owner rulings on the gold after the first run (`<set>_rulings.json`), applied on top of the labels and never
    written into them: each names the rows it changes and why."""
    path = get_settings().data_path / "eval" / f"{SET}_rulings.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def score(raw: list[dict], rows: list[dict], gold: list[dict]) -> dict:
    by_id = {r["id"]: r for r in rows}
    gold_by = {g["id"]: dict(g) for g in gold}
    for g in gold_by.values():  # the second set labels an injected comment with `signal`, the first with `injection`
        g["injection"] = bool(g.get("injection") or g.get("signal") == "injection")
    for rule in rulings().get("may_auto_post", []):
        for i in rule["ids"]:
            gold_by[i]["may_auto_post"] = True
    for rule in rulings().get("also_accept", []):  # another accepted value of a field, added to its `_alt` list
        for i in rule["ids"]:
            alt = gold_by[i].get(f"{rule['field']}_alt") or []
            gold_by[i][f"{rule['field']}_alt"] = [*([alt] if isinstance(alt, str) else alt), *rule["values"]]
    got = {x["id"]: x | {"scene": sc["scene"]} for sc in raw for x in sc["rows"]}
    sure = {i for i, g in gold_by.items() if g.get("confidence") != "low"}
    s: dict = {"n": len(got), "low_confidence": sorted(set(gold_by) - sure)}

    def table(ids, ok) -> dict:
        ids = [i for i in ids if i in got]
        hit = [i for i in ids if ok(i)]
        return {"n": len(ids), "ok": len(hit), "wrong": sorted(set(ids) - set(hit))}

    def kind_of(i: str) -> str | None:
        return "hide" if got[i]["visibility"] == "hidden" else got[i]["kind"]

    def any_of(i: str, field: str) -> list:
        """The gold label and its alternates (`<field>_alt`): the labeller's own list of defensible answers."""
        alt = gold_by[i].get(f"{field}_alt") or []
        return [gold_by[i].get(field), *([alt] if isinstance(alt, str) else alt)]

    def kind_ok(i: str) -> bool:
        return kind_of(i) in any_of(i, "kind")

    def route_ok(i: str) -> bool:
        """The final route; a sensitive question on the host's card with its reason kept is the "both" setting
        (host card and operator review at once), which the gold's OPERATOR/sensitive allows."""
        g, x = gold_by[i], got[i]
        if kind_of(i) != "question":
            return False
        if x["route"] in any_of(i, "route"):
            return True
        return (x["route"], x["route_reason"]) == ("HOST", "sensitive") and "sensitive" in any_of(i, "route_reason")

    s["kind"] = table(sure, kind_ok)
    s["kind_by_lang"] = {lang: table([i for i in sure if by_id[i]["lang"] == lang], kind_ok)
                         for lang in sorted({r["lang"] for r in rows})}
    for k in ("question", "reaction", "hide"):
        s[f"kind_{k}"] = table([i for i in sure if gold_by[i]["kind"] == k], kind_ok)
    questions = [i for i in sure if gold_by[i]["kind"] == "question"]
    both = [i for i in questions if i in got and kind_of(i) == "question"]  # scored as questions by both
    s["intent"] = table(questions, lambda i: kind_of(i) == "question" and got[i]["intent"] in any_of(i, "intent"))
    s["intent_by_lang"] = {lang: table([i for i in questions if by_id[i]["lang"] == lang],
                                       lambda i: kind_of(i) == "question" and got[i]["intent"] in any_of(i, "intent"))
                           for lang in sorted({by_id[i]["lang"] for i in questions})}
    s["product"] = table(both, lambda i: got[i]["product_id"] in any_of(i, "product_id")
                         or got[i]["product_id"] in (gold_by[i].get("product_alt") or []))
    s["route"] = table(questions, route_ok)

    # grouping: pairs of gold questions inside one scene
    same_ok = same_n = merged_n = 0
    wrong_merges, missed = [], []
    for scene in sorted({x["scene"] for x in got.values()}):
        qs = [i for i in both if got[i]["scene"] == scene]
        for a, b in itertools.combinations(qs, 2):
            gold_same = gold_by[a]["group"] == gold_by[b]["group"]
            # `group_alt`: groups the labeller says this question may also be merged with (not required)
            may_merge = gold_same or bool(set(any_of(a, "group")) & set(any_of(b, "group")) - {None})
            pred_same = got[a]["group_id"] is not None and got[a]["group_id"] == got[b]["group_id"]
            same_n += gold_same
            merged_n += pred_same
            same_ok += gold_same and pred_same
            if pred_same and not may_merge:
                wrong_merges.append([a, b])
            if gold_same and not pred_same:
                missed.append([a, b])
    s["grouping"] = {"gold_pairs": same_n, "found": same_ok, "merged_pairs": merged_n,
                     "wrong_merges": wrong_merges, "missed": missed}

    # answers
    posted = {i: [r for r in x["replies"] if r["kind"] == "ai_answer"] for i, x in got.items()}
    posted = {i: r for i, r in posted.items() if r}
    allowed = [i for i in sure if gold_by[i].get("may_auto_post")]
    s["auto_coverage"] = table(allowed, lambda i: i in posted)
    # the one decision: posted by itself, or waiting for a person; right when it matches the gold
    s["decision"] = table(questions, lambda i: (i in posted) == bool(gold_by[i].get("may_auto_post")))
    # without the rows whose opposite decision the labeller also finds defensible (`needs_approval_alt`)
    firm = [i for i in questions if not gold_by[i].get("needs_approval_alt")]
    s["decision_firm"] = table(firm, lambda i: (i in posted) == bool(gold_by[i].get("may_auto_post")))
    s["auto_not_allowed_firm"] = sorted(i for i in firm if i in posted and not gold_by[i].get("may_auto_post"))
    s["auto_not_allowed"] = [{"id": i, "why": ("injection" if gold_by[i].get("injection") else
                                               "sensitive" if gold_by[i].get("sensitive") else
                                               "not a question" if gold_by[i]["kind"] != "question" else
                                               "no source" if not gold_by[i].get("answerable") else
                                               f"route {gold_by[i]['route']}"),
                              "text": posted[i][0]["text"]}
                             for i in sorted(posted) if i in gold_by and not gold_by[i].get("may_auto_post")]
    facts_missing = []
    for i in sorted(posted):
        g = gold_by.get(i, {})
        need = set().union(*(number_set(f["fact"]) for f in g.get("answer_facts", []))) if g.get("answer_facts") else set()
        answer_numbers = number_set(posted[i][0]["text"])
        if g.get("may_auto_post") and need and not (need & answer_numbers):
            facts_missing.append({"id": i, "text": posted[i][0]["text"],
                                  "facts": [f["fact"] for f in g["answer_facts"]]})
    s["answers_to_review"] = facts_missing
    # a reply to the real question inside an injected comment is right; listed so each text is read by a person
    # INJECTION_REPLY=reply: the fixed "cannot answer" line (a notice no model wrote) is the designed reply to an
    # injection comment; any other message under one is still listed
    s["injection_replies"] = [{"id": i, "replies": [r for r in got[i]["replies"] if r["kind"] != "notice"]}
                              for i in sorted(got) if gold_by.get(i, {}).get("injection")
                              and [r for r in got[i]["replies"] if r["kind"] != "notice"]]
    flagged = [i for i in sure if gold_by[i].get("signal") == "stream_issue"]
    s["stream_issues"] = table(flagged, lambda i: got[i].get("signal") == "stream_issue")
    s["stream_false"] = sorted(i for i in sure if i in got and got[i].get("signal") == "stream_issue"
                               and gold_by[i].get("signal") != "stream_issue")
    two = [i for i in sure if gold_by[i].get("second")]
    s["second_questions"] = table(two, lambda i: len(got[i].get("groups") or []) >= 2)
    s["drafts"] = table([i for i in both if gold_by[i].get("answerable")],
                        lambda i: bool(got[i]["draft"] and got[i]["draft"]["verified"]))
    lat = collections.defaultdict(list)
    for sc in raw:
        for k, v in sc["reply_latencies"].items():
            lat[k] += v
    s["reply_latency"] = {k: {"n": len(v), "p50": _quantile(v, 0.5), "p95": _quantile(v, 0.95)} for k, v in lat.items()}
    tri = [x["triage_ms"] for x in got.values() if x["source"] == "llm" and x["triage_ms"]]
    s["triage_latency"] = {"n": len(tri), "p50": _quantile(tri, 0.5), "p95": _quantile(tri, 0.95)}
    s["sources"] = dict(collections.Counter(x["source"] for x in got.values()))
    return s


def write_report(s: dict, raw: list[dict], rows: list[dict], gold: list[dict], out: Path, arm: dict) -> None:
    by_id, gold_by = {r["id"]: r for r in rows}, {g["id"]: g for g in gold}
    got = {x["id"]: x for sc in raw for x in sc["rows"]}
    g = s["grouping"]
    lines = [
        "# Comment hold-out eval", "",
        f"{dt.date.today().isoformat()} · `{SET}_raw.jsonl` · {s['n']} comments in {len(raw)} scenes · "
        f"1 run · real runtime per scene. Gold rows marked low confidence are left out of every rate "
        f"({len(s['low_confidence'])}).", "",
        "Settings: " + ", ".join(f"`{k}={v}`" for k, v in arm.items()), "",
        "| metric | result |", "|---|---|",
        f"| kind (question / reaction / hide) | {_pct(s['kind']['ok'], s['kind']['n'])} |",
        *(f"| kind, gold {k} | {_pct(s[f'kind_{k}']['ok'], s[f'kind_{k}']['n'])} |" for k in ("question", "reaction", "hide")),
        f"| category (intent) of gold questions | {_pct(s['intent']['ok'], s['intent']['n'])} |",
        f"| product of questions | {_pct(s['product']['ok'], s['product']['n'])} |",
        f"| final route of gold questions | {_pct(s['route']['ok'], s['route']['n'])} |",
        f"| grouping recall (gold same-group pairs found) | {_pct(g['found'], g['gold_pairs'])} |",
        f"| grouping precision (merged pairs the gold allows) | {_pct(g['merged_pairs'] - len(g['wrong_merges']), g['merged_pairs'])} |",
        f"| wrong merges | {len(g['wrong_merges'])} |",
        f"| answerable questions with a verified draft | {_pct(s['drafts']['ok'], s['drafts']['n'])} |",
        f"| auto or approval, as the gold says (all gold questions) | {_pct(s['decision']['ok'], s['decision']['n'])} |",
        f"| the same, without the rows the labeller marks as defensible either way | {_pct(s['decision_firm']['ok'], s['decision_firm']['n'])}; posted where not allowed {len(s['auto_not_allowed_firm'])} |",
        f"| auto answers posted where the gold allows one | {_pct(s['auto_coverage']['ok'], s['auto_coverage']['n'])} |",
        f"| auto answers posted where the gold does not allow one | {len(s['auto_not_allowed'])} |",
        f"| posted answers without the gold fact's number (to review) | {len(s['answers_to_review'])} |",
        f"| messages replying to an injection comment (each listed below) | {len(s['injection_replies'])} |",
        f"| stream problems flagged for the team | {_pct(s['stream_issues']['ok'], s['stream_issues']['n'])}; false flags {len(s['stream_false'])} |",
        f"| two-question comments with both parts handled | {_pct(s['second_questions']['ok'], s['second_questions']['n'])} |",
        f"| triage latency (LLM calls, n={s['triage_latency']['n']}) | p50 {s['triage_latency']['p50']}, p95 {s['triage_latency']['p95']} |",
        *(f"| comment to reply, {k} (n={v['n']}) | p50 {v['p50']}, p95 {v['p95']} |" for k, v in sorted(s["reply_latency"].items())),
        f"| how comments were classified | {s['sources']} |", "",
        "## By language", "", "| lang | kind | category |", "|---|---|---|",
        *(f"| {lang} | {_pct(t['ok'], t['n'])} | "
          f"{_pct(s['intent_by_lang'][lang]['ok'], s['intent_by_lang'][lang]['n']) if lang in s['intent_by_lang'] else 'n/a'} |"
          for lang, t in s["kind_by_lang"].items()), "",
    ]

    def detail(title: str, ids: list[str], show) -> None:
        lines.extend([f"## {title}", ""])
        lines.extend([f"- {i} [{by_id[i]['lang']}] {by_id[i]['text']!r}: {show(i)}" for i in ids] or ["None."])
        lines.append("")

    def kind_of(i: str) -> str | None:
        return "hide" if got[i]["visibility"] == "hidden" else got[i]["kind"]

    detail("Wrong kind", s["kind"]["wrong"], lambda i: f"gold {gold_by[i]['kind']} {gold_by[i].get('kind_alt') or ''}, got {kind_of(i)} ({got[i]['source']})")
    detail("Wrong category", [i for i in s["intent"]["wrong"] if kind_of(i) == "question"],
           lambda i: f"gold {gold_by[i]['intent']} {gold_by[i].get('intent_alt') or ''}, got {got[i]['intent']}")
    detail("Wrong product", s["product"]["wrong"], lambda i: f"gold {gold_by[i].get('product_id')}, got {got[i]['product_id']}")
    detail("Wrong route", [i for i in s["route"]["wrong"] if kind_of(i) == "question"],
           lambda i: f"gold {gold_by[i]['route']} ({gold_by[i].get('route_reason')}), got {got[i]['route']} "
                     f"({got[i]['route_reason']}, {got[i]['status']})")
    lines.extend(["## Wrong merges", ""])
    lines.extend([f"- {a} {by_id[a]['text']!r} + {b} {by_id[b]['text']!r} (gold {gold_by[a]['group']} / {gold_by[b]['group']})"
                  for a, b in g["wrong_merges"]] or ["None."])
    lines.extend(["", "## Missed merges", ""])
    lines.extend([f"- {a} {by_id[a]['text']!r} + {b} {by_id[b]['text']!r}" for a, b in g["missed"]] or ["None."])
    lines.extend(["", "## Auto answers the gold does not allow", ""])
    lines.extend([f"- {x['id']} {by_id[x['id']]['text']!r} ({x['why']}): {x['text']!r}" for x in s["auto_not_allowed"]] or ["None."])
    lines.extend(["", "## Allowed auto answers not posted", ""])
    lines.extend([f"- {i} {by_id[i]['text']!r}: route {got[i]['route']} ({got[i]['route_reason']}), status {got[i]['status']}, "
                  f"draft {got[i]['draft']['errors'] if got[i]['draft'] else None}" for i in s["auto_coverage"]["wrong"]] or ["None."])
    lines.extend(["", "## Posted answers to review", ""])
    lines.extend([f"- {x['id']} {by_id[x['id']]['text']!r}: {x['text']!r} (gold facts {x['facts']})" for x in s["answers_to_review"]] or ["None."])
    lines.extend(["", "## Replies to injection comments", ""])
    lines.extend([f"- {x['id']} {by_id[x['id']]['text']!r}: {[r['text'] for r in x['replies']]}" for x in s["injection_replies"]] or ["None."])
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=REPO_DIR / "docs/eval/comment-holdout.md")
    ap.add_argument("--gap-ms", type=int, default=1500, help="time between two comments of a scene")
    ap.add_argument("--concurrency", type=int, default=3, help="scenes at a time")
    ap.add_argument("--show-mode", default="team", choices=["solo", "team"])
    ap.add_argument("--scenes", default="", help="comma-separated scene ids; empty = all")
    ap.add_argument("--from-json", type=Path, default=None)
    ap.add_argument("--set", default="comment_holdout", help="file prefix in data/eval: <set>_raw.jsonl, <set>_gold.jsonl")
    args = ap.parse_args()
    global SET
    SET = args.set
    rows, gold = load(f"{SET}_raw.jsonl"), load(f"{SET}_gold.jsonl")
    if args.from_json:
        saved = json.loads(args.from_json.read_text(encoding="utf-8"))
        raw, arm = saved["scenes"], saved["arm"]
    else:
        settings = Settings(LLM_PROVIDER="vertex", STT_PROVIDER="mock", STORE="memory")
        arm = {k: getattr(settings, k) for k in ARM_KEYS} | {"show_mode": args.show_mode, "gap_ms": args.gap_ms}
        clock = ReplayClock()
        ctx = build_context(settings, clock=clock, scheduler=AsyncScheduler(clock))
        wanted = set(filter(None, args.scenes.split(",")))
        scenes = {k: list(v) for k, v in itertools.groupby(rows, key=lambda r: r["scene"]) if not wanted or k in wanted}
        sem = asyncio.Semaphore(args.concurrency)

        async def one(scene: str, items: list[dict]) -> dict:
            async with sem:
                r = await run_scene(ctx, scene, items, args.gap_ms, args.show_mode)
                print(f"{scene}: done", flush=True)
                return r

        try:
            await ctx.llm.warm_up()
            raw = list(await asyncio.gather(*(one(k, v) for k, v in scenes.items())))
        finally:
            ctx.runtimes.shutdown()
            ctx.scheduler.shutdown()
            await ctx.llm.aclose()
        args.out.with_suffix(".json").write_text(json.dumps({"arm": arm, "scenes": raw}, ensure_ascii=False) + "\n",
                                                 encoding="utf-8", newline="\n")
    s = score(raw, rows, gold)
    write_report(s, raw, rows, gold, args.out, arm)
    g = s["grouping"]
    print(f"kind {_pct(s['kind']['ok'], s['kind']['n'])} · category {_pct(s['intent']['ok'], s['intent']['n'])} · "
          f"route {_pct(s['route']['ok'], s['route']['n'])} · grouping recall {_pct(g['found'], g['gold_pairs'])} · "
          f"wrong merges {len(g['wrong_merges'])} · auto not allowed {len(s['auto_not_allowed'])} · "
          f"auto/approval decision {_pct(s['decision']['ok'], s['decision']['n'])}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
