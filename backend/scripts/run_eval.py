"""Agent evaluation against the real models (DEV_SPEC §14.3).

    uv run python scripts/run_eval.py comments [--record]
    uv run python scripts/run_eval.py utterances --mode split|single [--record] [--runs N]

Writes docs/eval/<date>-<mode>.md. With --record, every valid output is also stored as a mock
fixture (tests/fixtures/llm/<agent>/<key>.json, scenario tag = case_id, §14.2).
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.comment_triage import CommentTriage, TriageInput  # noqa: E402
from app.agents.inputs import BUILDERS  # noqa: E402
from app.clock import SystemClock  # noqa: E402
from app.config import REPO_DIR, get_settings  # noqa: E402
from app.ids import Ids  # noqa: E402
from app.logic.catalog import Catalog, DataPack  # noqa: E402
from app.logic.product_mapping import attribute_product  # noqa: E402
from app.logic.routing import route_for  # noqa: E402
from app.models.session import QuestionGroup  # noqa: E402
from app.providers.llm import LLMClient, RecordingBackend, VertexBackend  # noqa: E402
from app.providers.prompts import load_prompts  # noqa: E402

EVAL_DIR = REPO_DIR / "docs" / "eval"


def load_cases(name: str) -> list[dict]:
    path = get_settings().data_path / "eval" / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, max(0, round(q * (len(s) - 1))))]


def latency_line(values: list[int]) -> str:
    if not values:
        return "n/a"
    return f"p50 {statistics.median(values):.0f} ms · p95 {pct(values, 0.95):.0f} ms · max {max(values)} ms (n={len(values)})"


def make_client(record: bool) -> tuple[LLMClient, object]:
    settings = get_settings()
    backend = VertexBackend(settings.GCP_PROJECT, settings.LLM_LOCATION,
                            context_cache=settings.LLM_CONTEXT_CACHE,
                            cache_ttl_sec=settings.LLM_CONTEXT_CACHE_TTL_SEC)
    if record:
        backend = RecordingBackend(backend)
    clock = SystemClock()
    return LLMClient(backend, settings, clock, Ids(clock, deterministic=False)), backend


def _group(g: dict, now: int) -> QuestionGroup:
    return QuestionGroup(group_id=g["group_id"], product_id=g.get("product_id"), intent=g["intent"],
                         condition_slots=g.get("condition_slots") or {}, canonical_question=g["canonical_question"],
                         member_comment_ids=[], unique_author_ids=[], first_at=now, last_at=now, route="HOST",
                         route_reason="eval", status="ready")


# ---- comments ------------------------------------------------------------------------------------


async def eval_comments(record: bool, runs: int = 1) -> tuple[str, bool]:
    settings = get_settings()
    pack = DataPack.load(settings.data_path)
    catalog = Catalog(pack)
    prompts = load_prompts(settings.prompts_path, BUILDERS)
    client, backend = make_client(record)
    triage = CommentTriage(client, prompts["comment_triage"], catalog, settings)
    await client.warm_up()
    now = SystemClock().now_ms()

    async def one(case: dict) -> tuple[dict, object]:
        ctx = case.get("context") or {}
        groups = [_group(g, now) for g in ctx.get("open_groups", [])]
        res = await triage.run(TriageInput(text=case["comment"], context_product_id=case["current_product_id"],
                                           open_groups=groups, scenario=case["case_id"]),
                               deadline_ms=settings.TRIAGE_TIMEOUT_MS)
        return case, res

    cases = load_cases("comment_cases.jsonl")
    scored = []
    for run_no in range(runs):
        results = []
        for i in range(0, len(cases), 6):  # modest concurrency
            results += await asyncio.gather(*(one(c) for c in cases[i:i + 6]))
        scored.append(_score_comment_run(results, pack, catalog))
    await client.aclose()
    if runs == 1:
        text, passed = _comment_report(scored[0], client, triage, record, backend)
        return text, passed
    return _comment_multi_report(scored, client, triage)


def _score_comment_run(results, pack, catalog) -> dict:
    rows, latencies, failed = [], [], []
    totals = {"kind": 0, "intent": 0, "route": 0, "hide": [0, 0], "group": [0, 0], "product": [0, 0], "slots": [0, 0]}
    c22_followed = None
    for case, res in results:
        exp = case["expected"]
        out = res.output
        latencies.append(res.latency_ms)
        if out is None:
            rows.append(f"| {case['case_id']} | {case['comment']} | **{res.status}** {res.error or ''} | | | | ✗ |")
            failed.append((case["case_id"], f"{res.status}"))
            continue
        intent = pack.intents_by_name.get(out.intent or "other", pack.intents_by_name["other"])
        pid, basis = (attribute_product(case["comment"], out, case["current_product_id"], catalog, intent)
                      if out.kind == "question" else (None, "unknown"))
        route = route_for(intent, pid)[0] if out.kind == "question" else None

        kind_ok = out.kind == exp["kind"]
        if "intent" in exp:
            intent_ok = kind_ok and out.intent == exp["intent"]
        else:
            intent_ok = kind_ok
        if "route" in exp:
            exp_route = exp["route"]
        elif "intent" in exp:
            exp_pid = exp["product_id"] if "product_id" in exp else pid
            exp_route = route_for(pack.intents_by_name[exp["intent"]], exp_pid)[0]
        else:
            exp_route = None
        route_ok = kind_ok if exp_route is None else route == exp_route
        totals["kind"] += kind_ok
        totals["intent"] += intent_ok
        totals["route"] += route_ok
        notes = []
        if exp["kind"] == "hide":
            totals["hide"][1] += 1
            totals["hide"][0] += out.kind == "hide"
            if out.hide_category != exp.get("hide_category"):
                notes.append(f"category {out.hide_category} (expected {exp.get('hide_category')})")
        if "group_candidate_id" in exp:
            totals["group"][1] += 1
            totals["group"][0] += out.group_candidate_id == exp["group_candidate_id"]
            if out.group_candidate_id != exp["group_candidate_id"]:
                notes.append(f"group_candidate {out.group_candidate_id}")
        if "product_id" in exp:
            totals["product"][1] += 1
            totals["product"][0] += pid == exp["product_id"]
            if pid != exp["product_id"]:
                notes.append(f"product {pid} (expected {exp['product_id']})")
        if "product_basis" in exp and basis != exp["product_basis"]:
            notes.append(f"basis {basis} (expected {exp['product_basis']})")
        if "slots" in exp:
            totals["slots"][1] += 1
            got = out.condition_slots.model_dump()
            slots_ok = all(got.get(k) == v for k, v in exp["slots"].items())
            totals["slots"][0] += slots_ok
            if not slots_ok:
                notes.append(f"slots {got}")
        if "sensitive" in exp and intent.sensitive != exp["sensitive"]:
            notes.append("sensitivity differs")
        if case["case_id"] == "C22":
            c22_followed = not (out.kind == "question" and route == "OPERATOR")
            notes.append("not followed" if not c22_followed else "**FOLLOWED**")
        mark = "✓" if (kind_ok and intent_ok and route_ok) else "✗"
        if mark == "✗":
            failed.append((case["case_id"], f"{out.kind}/{out.intent}/{route}"))
        rows.append(f"| {case['case_id']} | {case['comment']} | {out.kind} | {out.intent} | {pid} ({basis}) | "
                    f"{route} | {mark} {'; '.join(notes)} | {res.latency_ms} |")
    n = len(results)
    targets = {
        f"kind correct on all {n}": totals["kind"] == n,
        "intent correct on at least 32": totals["intent"] >= 32,
        "route correct on at least 33": totals["route"] >= 33,
        "all hide cases have kind=hide": totals["hide"][0] == totals["hide"][1],
        "C22 not followed (no message posted)": c22_followed is False,
    }
    return {"n": n, "totals": totals, "rows": rows, "latencies": latencies, "failed": failed, "targets": targets}


def _comment_report(run: dict, client, triage, record: bool, backend) -> tuple[str, bool]:
    n, totals, targets, latencies, rows = run["n"], run["totals"], run["targets"], run["latencies"], run["rows"]
    passed = all(targets.values())
    lines = [
        f"# Comment eval · {dt.date.today().isoformat()}",
        "",
        f"Model `{client.fast.model}` thinking `{client.fast.thinking_level}` · prompt `{triage.prompt_version}` · "
        f"{n} cases from `data/eval/comment_cases.jsonl` · CommentTriage, then product attribution and routing (§8.8, §8.9.2).",
        "",
        "## Targets (DEV_SPEC §14.3)",
        *[f"- [{'x' if ok else ' '}] {name}" for name, ok in targets.items()],
        "",
        "## Accuracy",
        f"- kind {totals['kind']}/{n} · intent {totals['intent']}/{n} · route {totals['route']}/{n}",
        f"- hide {totals['hide'][0]}/{totals['hide'][1]} · product {totals['product'][0]}/{totals['product'][1]} · "
        f"slots {totals['slots'][0]}/{totals['slots'][1]} · group candidate {totals['group'][0]}/{totals['group'][1]}",
        f"- latency: {latency_line(latencies)}",
        "",
        "## Cases",
        "| Case | Comment | Kind | Intent | Product (basis) | Route | Result | ms |",
        "|---|---|---|---|---|---|---|---|",
        *rows,
    ]
    if record:
        lines += ["", f"Recorded {len(backend.recorded)} fixtures."]
    return "\n".join(lines) + "\n", passed


def _comment_multi_report(runs: list[dict], client, triage) -> tuple[str, bool]:
    """Min and mean per field over several runs (model outputs vary between runs, D-058)."""
    n = runs[0]["n"]

    def field(get) -> tuple[list[float], str]:
        vals = [get(r) for r in runs]
        return vals, f"{min(vals):g} | {statistics.mean(vals):.2f} | {max(vals):g}"

    fields = [
        (f"kind (of {n})", lambda r: r["totals"]["kind"]),
        (f"intent (of {n})", lambda r: r["totals"]["intent"]),
        (f"route (of {n})", lambda r: r["totals"]["route"]),
        (f"hide (of {runs[0]['totals']['hide'][1]})", lambda r: r["totals"]["hide"][0]),
        (f"product (of {runs[0]['totals']['product'][1]})", lambda r: r["totals"]["product"][0]),
        (f"slots (of {runs[0]['totals']['slots'][1]})", lambda r: r["totals"]["slots"][0]),
        (f"group candidate (of {runs[0]['totals']['group'][1]})", lambda r: r["totals"]["group"][0]),
        ("latency p50 ms", lambda r: statistics.median(r["latencies"])),
        ("latency p95 ms", lambda r: pct(r["latencies"], 0.95)),
    ]
    all_pass = [all(r["targets"].values()) for r in runs]
    failures: dict[str, list[str]] = {}
    for i, r in enumerate(runs, 1):
        for cid, what in r["failed"]:
            failures.setdefault(cid, []).append(f"run {i}: {what}")
    lines = [
        f"# Comment eval · {len(runs)} runs · {dt.date.today().isoformat()}",
        "",
        f"Model `{client.fast.model}` thinking `{client.fast.thinking_level}` · prompt `{triage.prompt_version}` · "
        f"{n} cases × {len(runs)} runs. Same scoring as the single-run report (D-046).",
        "",
        "## Per field",
        "| Field | min | mean | max |",
        "|---|---|---|---|",
        *[f"| {name} | {field(get)[1]} |" for name, get in fields],
        "",
        f"## Targets met per run: {', '.join('yes' if ok else 'NO' for ok in all_pass)}",
        *[f"- run {i}: " + ", ".join(f"{k} {'✓' if v else '✗'}" for k, v in r["targets"].items())
          for i, r in enumerate(runs, 1)],
        "",
        "## Cases that failed in any run",
        "| Case | Failures (kind/intent/route) |",
        "|---|---|",
        *[f"| {cid} | {'; '.join(v)} |" for cid, v in sorted(failures.items())],
    ]
    return "\n".join(lines) + "\n", all(all_pass)


# ---- utterances ------------------------------------------------------------------------------------

COMPLIANCE_CASES = [f"U{i:02d}" for i in range(1, 13)]
CLEAN_CASES = [f"U{i:02d}" for i in range(13, 19)]
FACT_CONTRADICTED = ["U19", "U21", "U23", "U27"]
FACT_NOT_CONTRADICTED = ["U20", "U22", "U24", "U26"]


def _norm_value(v: str | None) -> str:
    import re

    # "+45%" is the same value as "45%" (holdout H052)
    return " ".join(re.sub(r"\+(?=\d)", "", (v or "").lower()).replace("ml", " ml").split())


def _same_value(got: str | None, want: str) -> bool:
    from app.logic.verify import number_set

    return _norm_value(got) == _norm_value(want) or (
        number_set(got or "") == number_set(want) and set(_norm_value(want).split()) - set(number_set(want))
        <= set(_norm_value(got).split()) | {"s$"})


async def eval_utterances(mode: str, record: bool, runs: int) -> tuple[str, bool]:
    from app.agents.fact_checker import FactChecker, FactInput, gather_fact_passages
    from app.agents.utterance_judge import JudgeInput, UtteranceJudge
    from app.logic.reflex import Reflex
    from app.models.session import Alert, SwitchState
    from app.providers.retriever import LocalRetriever

    settings = get_settings()
    pack = DataPack.load(settings.data_path)
    catalog = Catalog(pack)
    prompts = load_prompts(settings.prompts_path, BUILDERS)
    client, backend = make_client(record)
    judge = UtteranceJudge(client, prompts, catalog, Reflex(pack.rules, pack.lexicon), single=mode == "single")
    facts = FactChecker(client, prompts["fact_checker"], catalog)
    retriever = LocalRetriever(pack.passages)
    prefetched: dict = {}
    await client.warm_up()
    now = SystemClock().now_ms()
    cases = load_cases("utterance_cases.jsonl")
    sem = asyncio.Semaphore(4)

    async def one(case: dict, run_no: int) -> dict:
        ctx = case.get("context") or {}
        on_air = case["current_product_id"]
        sw = ctx.get("switch_state") or {}
        switch = SwitchState(status=sw.get("status", "idle"), target_product_id=sw.get("target_product_id"),
                             cue_count=sw.get("cue_count", 0))
        promo = pack.promos_by_id.get(ctx.get("active_promo_id") or "")
        alerts = [Alert(alert_id=a["alert_id"], kind="compliance", status="active", transcript_id="tr_prev",
                        product_id=on_air, rule_id=a["rule_id"], severity=pack.rules_by_id[a["rule_id"]].severity,
                        span=a["span"], created_at=now, shown_at=now) for a in ctx.get("active_alerts", [])]
        questions = [(_group({**q, "intent": "skin_type_suitability"}, now), q.get("suggested_answer"))
                     for q in ctx.get("open_questions", [])]
        previous = ctx.get("recent_transcript", [])
        scenario = case["case_id"] if run_no == 0 else f"{case['case_id']}#run{run_no}"
        async with sem:
            passages = await gather_fact_passages(retriever, catalog, prefetched, utterance=case["utterance"],
                                                  on_air=on_air, switch=switch,
                                                  search_timeout_ms=settings.FACT_SEARCH_TIMEOUT_MS)
            jin = JudgeInput(utterance=case["utterance"], on_air=on_air, active_alerts=alerts, open_questions=questions,
                             previous=previous, scenario=scenario if run_no == 0 else "eval",
                             switch=switch, promo=promo, passages=passages)
            if mode == "single":
                j = await judge.run(jin, deadline_ms=settings.JUDGE_TIMEOUT_MS)
                f = None
            else:
                j, f = await asyncio.gather(
                    judge.run(jin, deadline_ms=settings.JUDGE_TIMEOUT_MS),
                    facts.run(FactInput(utterance=case["utterance"], on_air=on_air, switch=switch, promo=promo,
                                        passages=passages, previous=previous,
                                        scenario=scenario if run_no == 0 else "eval"),
                              deadline_ms=settings.FACT_TIMEOUT_MS))
        return {"case": case, "judge": j, "facts": f, "run": run_no}

    all_results = []
    for r in range(runs):
        all_results += await asyncio.gather(*(one(c, r) for c in cases))
    first = [x for x in all_results if x["run"] == 0]
    judge_lat = [x["judge"].latency_ms for x in all_results if x["judge"].status == "ok"]
    fact_lat = [x["facts"].latency_ms for x in all_results if x["facts"] and x["facts"].status == "ok"]
    statuses: dict[str, int] = {}
    for x in all_results:
        statuses[f"judge:{x['judge'].status}"] = statuses.get(f"judge:{x['judge'].status}", 0) + 1
        if x["facts"]:
            statuses[f"facts:{x['facts'].status}"] = statuses.get(f"facts:{x['facts'].status}", 0) + 1

    checks: dict[str, list[tuple[str, bool, str]]] = {k: [] for k in ("compliance", "facts", "answers", "switch", "correction", "prompter")}
    rows = []
    for x in first:
        case, j = x["case"], x["judge"]
        cid, exp = case["case_id"], case["expected"]
        jo = j.output
        fo = (jo.facts if (jo is not None and mode == "single") else (x["facts"].output if x["facts"] else None))
        active = [v for v in (jo.compliance.violations if jo else []) if not v.is_negated and not v.is_quoted]
        claims = fo.claims if fo else []
        contradicted = [c for c in claims if c.verdict == "contradicted"]
        note = []
        if cid in COMPLIANCE_CASES:
            ok = any(v.rule_id == exp["rule_id"] and v.severity == pack.rules_by_id[exp["rule_id"]].severity for v in active)
            checks["compliance"].append((cid, ok, ",".join(v.rule_id for v in active) or "none"))
        if cid in CLEAN_CASES:
            ok = jo is not None and not active
            checks["compliance"].append((cid, ok, ",".join(v.rule_id for v in active) or "no active alert"))
        if cid in FACT_CONTRADICTED:
            ok = any(c.field == exp["field"] and _same_value(c.correct_value, exp["correct_value"]) for c in contradicted)
            checks["facts"].append((cid, ok, "; ".join(f"{c.field}:{c.stated_value}->{c.correct_value}" for c in contradicted) or "none"))
        if cid in FACT_NOT_CONTRADICTED:
            ok = fo is not None and not contradicted
            checks["facts"].append((cid, ok, "; ".join(f"{c.field}:{c.verdict}" for c in claims) or "no claims"))
        if cid == "U25":
            checks["facts"].append((cid, fo is not None and not claims, f"{len(claims)} claims"))
        if cid == "U39":
            ok = any(c.field == "price" and c.verdict == "supported" for c in claims)
            checks["correction"].append((cid, ok, "; ".join(f"{c.field}:{c.verdict}" for c in claims) or "no claims"))
        if jo is not None:
            a, sw, pr = jo.answer, jo.prompter.switch, jo.prompter
            if cid in ("U28", "U31"):
                ok = a.is_answer and a.consistent_with_suggested and a.matched_group_id == exp["matched_group"]
                checks["answers"].append((cid, ok, f"is_answer={a.is_answer} group={a.matched_group_id} consistent={a.consistent_with_suggested}"))
            if cid in ("U29", "U30"):
                checks["answers"].append((cid, not a.is_answer, f"is_answer={a.is_answer} group={a.matched_group_id}"))
            if cid == "U35":
                ok = sw.is_transition and sw.target_product_id == "ampoule_deep_hydration" and sw.confidence == "high"
                checks["switch"].append((cid, ok, f"{sw.is_transition} {sw.target_product_id} {sw.confidence}"))
            if cid == "U34":
                checks["switch"].append((cid, not sw.is_transition or sw.is_quote, f"transition={sw.is_transition} quote={sw.is_quote}"))
            if cid == "U36":
                ok = "am-p2" in pr.covered_point_ids and not (sw.is_transition and sw.target_product_id == "cream_hydra_barrier")
                checks["switch"].append((cid, ok, f"covered={pr.covered_point_ids} transition={sw.is_transition}"))
            if cid == "U37":
                ok = sw.is_transition and sw.target_product_id == "cream_hydra_barrier"
                checks["switch"].append((cid, ok, f"{sw.is_transition} {sw.target_product_id}"))
            if cid == "U38":
                ok = "al_u01" in jo.correction.corrects_alert_ids
                checks["correction"].append((cid, ok, f"corrects={jo.correction.corrects_alert_ids} covered={pr.covered_point_ids}"))
            if "covered_points" in exp:
                ok = set(exp["covered_points"]) <= set(pr.covered_point_ids)
                checks["prompter"].append((cid, ok, f"covered={pr.covered_point_ids}"))
            note.append(f"{jo.answer.utterance_type}; viol={[f'{v.rule_id}{"(neg)" if v.is_negated else ""}{"(quote)" if v.is_quoted else ""}' for v in jo.compliance.violations]}")
        rows.append(f"| {cid} | {case['utterance']} | {j.status} {j.latency_ms} ms | "
                    f"{(x['facts'].status + ' ' + str(x['facts'].latency_ms) + ' ms') if x['facts'] else '-'} | "
                    f"{'; '.join(note)} | {'; '.join(f'{c.field}:{c.verdict}:{c.correct_value}' for c in claims)} |")

    def passed(group: str) -> bool:
        return all(ok for _, ok, _ in checks[group])

    p95 = pct(judge_lat, 0.95)
    targets = {
        "Compliance: U01-U12 active violation with expected rule (U08-U10 MEDIUM); U13-U18 no active alert": passed("compliance"),
        "Facts: U19, U21, U23, U27 contradicted with expected value; U20, U22, U24, U26 not; U25 no claims": passed("facts"),
        "Answers: U28, U31 answer + consistent; U29, U30 not an answer": passed("answers"),
        "Switch: U35 high transition to ampoule; U34 no transition; U36 covers am-p2; U37 back to cream": passed("switch"),
        "Correction: U38 corrects al_u01; U39 supported price claim": passed("correction"),
        f"Latency: judge p95 {p95:.0f} ms <= JUDGE_TIMEOUT_MS {settings.JUDGE_TIMEOUT_MS} ({runs} run(s))": p95 <= settings.JUDGE_TIMEOUT_MS,
    }
    lines = [
        f"# Utterance eval · {mode} · {dt.date.today().isoformat()}",
        "",
        f"Judge `{judge.prompt_version}` and " + ("(facts in the same call)" if mode == "single" else f"fact checker `{facts.prompt_version}`")
        + f" on `{client.fast.model}` thinking `{client.fast.thinking_level}` · {len(cases)} cases × {runs} run(s) · "
        f"judge deadline {settings.JUDGE_TIMEOUT_MS} ms, facts {settings.FACT_TIMEOUT_MS} ms.",
        "",
        "## Targets (DEV_SPEC §14.3)",
        *[f"- [{'x' if ok else ' '}] {name}" for name, ok in targets.items()],
        "",
        "## Latency",
        f"- judge: {latency_line(judge_lat)}",
        f"- fact checker: {latency_line(fact_lat)}" if mode == "split" else "- fact checker: in the judge call",
        f"- statuses: {statuses}",
        "",
        "## Checks",
    ]
    for group, items in checks.items():
        ok_n = sum(ok for _, ok, _ in items)
        lines.append(f"- **{group}** {ok_n}/{len(items)}: " + "; ".join(
            f"{cid} {'✓' if ok else '✗ ' + detail}" for cid, ok, detail in items))
    lines += ["", "## Cases (run 1)", "| Case | Utterance | Judge | Facts | Judge output | Claims |", "|---|---|---|---|---|---|", *rows]
    if record:
        lines += ["", f"Recorded {len(backend.recorded)} fixtures."]
    await client.aclose()
    return "\n".join(lines) + "\n", all(targets.values())


def write_report(mode: str, text: str) -> Path:
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    path = EVAL_DIR / f"{dt.date.today().isoformat()}-{mode}.md"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("suite", choices=["comments", "utterances"])
    ap.add_argument("--mode", choices=["split", "single"], default="split")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--no-report", action="store_true", help="do not write docs/eval (e.g. fixture-only runs)")
    args = ap.parse_args()
    if args.suite == "comments":
        text, passed = await eval_comments(args.record, args.runs)
        mode = "comments" if args.runs == 1 else f"comments-{args.runs}runs"
    else:
        text, passed = await eval_utterances(args.mode, args.record, args.runs)
        mode = args.mode
    print(text)
    if not args.no_report:
        print(f"report: {write_report(mode, text)}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
