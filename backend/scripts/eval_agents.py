"""Baseline for the two utterance agents (split mode): how accurate is each in its own area, and how
often does it answer in the other's area? Every run is scored (run_eval.py scores run 1 only).

Inputs are the 39 utterance eval cases (data/eval/utterance_cases.jsonl) built exactly as run_eval.py
does: text in as the final transcript, real UtteranceJudge and FactChecker on Vertex AI, in parallel.
No orchestrator code runs. The fact checker is scored twice: its raw model answer, and after its own
quote check (`post_validate`, which downgrades a "contradicted" claim without a quoted source).

    uv run python scripts/eval_agents.py [--runs 20] [--out ../docs/eval/agents-baseline.md]
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

import app.agents.fact_checker as fc_module  # noqa: E402
from app.agents.fact_checker import FactChecker, FactInput, gather_fact_passages  # noqa: E402
from app.agents.inputs import BUILDERS  # noqa: E402
from app.agents.utterance_judge import JudgeInput, UtteranceJudge  # noqa: E402
from app.clock import SystemClock  # noqa: E402
from app.config import REPO_DIR, get_settings  # noqa: E402
from app.logic.catalog import Catalog, DataPack  # noqa: E402
from app.logic.reflex import Reflex  # noqa: E402
from app.models.session import Alert, SwitchState  # noqa: E402
from app.providers.prompts import load_prompts  # noqa: E402
from app.providers.retriever import LocalRetriever  # noqa: E402
from run_eval import _group, _same_value, load_cases, make_client, pct  # noqa: E402

VIOLATION = [f"U{i:02d}" for i in range(1, 13)] + ["U23"]
CLEAN = [f"U{i:02d}" for i in range(13, 19)]
FACT_WRONG = ["U19", "U21", "U23", "U27"]
FACT_RIGHT = ["U20", "U22", "U24", "U26", "U25", "U39"]
ANSWER_YES, ANSWER_NO = ["U28", "U31"], ["U29", "U30"]

# Keep the raw model answer: run() normally applies post_validate before returning.
_post_validate = fc_module.post_validate
fc_module.post_validate = lambda out, *a, **k: out


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--out", type=Path, default=REPO_DIR / "docs" / "eval" / "agents-baseline.md")
    ap.add_argument("--from-json", type=Path, default=None, help="re-score saved outputs without calling the models")
    args = ap.parse_args()
    settings = get_settings()
    if args.from_json:
        saved = json.loads(args.from_json.read_text(encoding="utf-8"))
        return report(saved, load_cases("utterance_cases.jsonl"), max(x["run"] for x in saved) + 1, settings, args.out)
    pack = DataPack.load(settings.data_path)
    catalog = Catalog(pack)
    prompts = load_prompts(settings.prompts_path, BUILDERS)
    client, _ = make_client(False)
    judge = UtteranceJudge(client, prompts, catalog, Reflex(pack.rules))
    facts = FactChecker(client, prompts["fact_checker"], catalog)
    retriever = LocalRetriever(pack.passages)
    prefetched: dict = {}
    print("warm-up:", await client.warm_up())
    now = SystemClock().now_ms()
    cases = load_cases("utterance_cases.jsonl")
    sem = asyncio.Semaphore(args.concurrency)

    async def one(case: dict, run_no: int) -> dict:
        ctx = case.get("context") or {}
        on_air = case["current_product_id"]
        sw = ctx.get("switch_state") or {}
        switch = SwitchState(status=sw.get("status", "idle"), target_product_id=sw.get("target_product_id"),
                             cue_count=sw.get("cue_count", 0))
        promo = pack.promos_by_id.get(ctx.get("active_promo_id") or "")
        alerts = [Alert(alert_id=a["alert_id"], kind="compliance", status="active", transcript_id="tr_prev",
                        product_id=on_air, rule_id=a["rule_id"], severity=pack.rules_by_id[a["rule_id"]].severity,
                        span=a["span"], say_instead=a.get("say_instead"), created_at=now, shown_at=now)
                  for a in ctx.get("active_alerts", [])]
        questions = [(_group({**q, "intent": "skin_type_suitability"}, now), q.get("suggested_answer"))
                     for q in ctx.get("open_questions", [])]
        previous = ctx.get("recent_transcript", [])
        async with sem:
            passages = await gather_fact_passages(retriever, catalog, prefetched, utterance=case["utterance"],
                                                  on_air=on_air, switch=switch,
                                                  search_timeout_ms=settings.FACT_SEARCH_TIMEOUT_MS)
            jin = JudgeInput(utterance=case["utterance"], on_air=on_air, active_alerts=alerts, open_questions=questions,
                             previous=previous, scenario="eval", switch=switch, promo=promo, passages=passages)
            j, f = await asyncio.gather(
                judge.run(jin, deadline_ms=settings.JUDGE_TIMEOUT_MS),
                facts.run(FactInput(utterance=case["utterance"], on_air=on_air, switch=switch, promo=promo,
                                    passages=passages, previous=previous, scenario="eval"),
                          deadline_ms=settings.FACT_TIMEOUT_MS))
        validated = _post_validate(f.output, passages, catalog, promo) if f.output is not None else None
        return {"id": case["case_id"], "run": run_no, "judge": j, "facts": f, "validated": validated}

    results = []
    for r in range(args.runs):
        results += await asyncio.gather(*(one(c, r) for c in cases))
        print(f"run {r + 1}/{args.runs} done")
    await client.aclose()
    raw = [{"id": x["id"], "run": x["run"], "judge_status": x["judge"].status, "judge_ms": x["judge"].latency_ms,
            "judge": x["judge"].output.model_dump(mode="json") if x["judge"].output else None,
            "facts_status": x["facts"].status, "facts_ms": x["facts"].latency_ms,
            "facts_raw": x["facts"].output.model_dump(mode="json") if x["facts"].output else None,
            "facts_validated": x["validated"].model_dump(mode="json") if x["validated"] else None} for x in results]
    args.out.with_suffix(".json").write_text(json.dumps(raw, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return report(raw, cases, args.runs, settings, args.out)


SWITCH_CASES = ("U34", "U35", "U36", "U37")


def report(raw: list[dict], cases: list[dict], runs: int, settings, out: Path) -> int:
    """Score every case run. A timed-out agent counts as a timeout, never as a right or wrong answer."""
    by_id = {c["case_id"]: c for c in cases}
    non_compliance = [c["case_id"] for c in cases if c["case_id"] not in VIOLATION + CLEAN]
    non_fact = [c["case_id"] for c in cases if c["case_id"] not in FACT_WRONG + FACT_RIGHT]
    tally: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    misses: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)

    def mark(key: str, cid: str, status: str, ok: bool, what: str) -> None:
        if status != "ok":
            tally[key]["timeout"] += 1
            return
        tally[key]["ok" if ok else "wrong"] += 1
        if not ok:
            misses[key][f"{cid}: {what}"] += 1

    judge_ms = [x["judge_ms"] for x in raw if x["judge_status"] == "ok"]
    facts_ms = [x["facts_ms"] for x in raw if x["facts_status"] == "ok"]
    wall_ms = [max(x["judge_ms"], x["facts_ms"]) for x in raw if x["judge_status"] == "ok" and x["facts_status"] == "ok"]
    statuses = collections.Counter(f"judge {x['judge_status']}" for x in raw)
    statuses.update(f"facts {x['facts_status']}" for x in raw)
    for x in raw:
        cid, exp, jo, js = x["id"], by_id[x["id"]]["expected"], x["judge"] or {}, x["judge_status"]
        active = [v for v in (jo["compliance"]["violations"] if jo else []) if not v["is_negated"] and not v["is_quoted"]]
        av = ",".join(v["rule_id"] for v in active) or "none"
        if cid in VIOLATION:
            mark("judge · catches the violation (right rule)", cid, js, any(v["rule_id"] == exp["rule_id"] for v in active), f"got {av}")
        if cid in CLEAN:
            mark("judge · no alert on negated/quoted/approved wording", cid, js, not active, f"got {av}")
        if cid in non_compliance:
            mark("judge · leak: alert on a sentence with no compliance claim", cid, js, not active, f"got {av}")
        a = jo.get("answer") or {}
        pr = jo.get("prompter") or {"covered_point_ids": [], "switch": {}}
        sw = pr.get("switch") or {}
        if cid in ANSWER_YES:
            mark("judge · answer linking", cid, js, bool(a) and a["is_answer"] and a["consistent_with_suggested"]
                 and a["matched_group_id"] == exp["matched_group"], f"is_answer={a.get('is_answer')}")
        if cid in ANSWER_NO:
            mark("judge · answer linking", cid, js, bool(a) and not a["is_answer"], "read-out taken as an answer")
        if cid == "U35":
            mark("judge · switch", cid, js, bool(sw.get("is_transition")) and sw.get("target_product_id") == "ampoule_deep_hydration", "no transition")
        if cid == "U34":
            mark("judge · switch", cid, js, not sw.get("is_transition") or bool(sw.get("is_quote")), "mention taken as a transition")
        if cid == "U36":
            mark("judge · switch", cid, js, "am-p2" in pr["covered_point_ids"], f"covered={pr['covered_point_ids']}")
        if cid == "U37":
            mark("judge · switch", cid, js, bool(sw.get("is_transition")) and sw.get("target_product_id") == "cream_hydra_barrier", "not back to cream")
        if cid == "U38":
            mark("judge · correction", cid, js, "al_u01" in ((jo.get("correction") or {}).get("corrects_alert_ids") or []), "not corrected")
        if "covered_points" in exp:
            mark("judge · prompter points", cid, js, set(exp["covered_points"]) <= set(pr["covered_point_ids"]),
                 f"covered={pr['covered_point_ids']}")
        for label, key in (("raw", "facts_raw"), ("after quote check", "facts_validated")):
            fo, fs = x[key], x["facts_status"]
            wrong = [c for c in (fo["claims"] if fo else []) if c["verdict"] == "contradicted"]
            wtxt = "; ".join(f"{c['field']}: {c['stated_value']} -> {c['correct_value']}" for c in wrong) or "none"
            if cid in FACT_WRONG:
                mark(f"facts ({label}) · catches the wrong fact", cid, fs,
                     any(c["field"] == exp["field"] and _same_value(c["correct_value"], exp["correct_value"]) for c in wrong), f"got {wtxt}")
            if cid in FACT_RIGHT:
                mark(f"facts ({label}) · no note on a right fact", cid, fs, not wrong, f"got {wtxt}")
            if cid in non_fact:
                mark(f"facts ({label}) · leak: note on a sentence that is not about facts", cid, fs, not wrong, f"got {wtxt}")

    def row(key: str) -> str:
        c = tally[key]
        answered = c["ok"] + c["wrong"]
        acc = f"{100 * c['ok'] / answered:.1f}%" if answered else "n/a"
        return f"| {key} | {c['ok']}/{answered} ({acc}) | {c['wrong']} | {c['timeout']} |"

    def lat(v: list[int]) -> str:
        return f"p50 {pct(v, 0.5):.0f} ms · p95 {pct(v, 0.95):.0f} ms · max {max(v)} ms" if v else "n/a"

    keys = sorted(tally, key=lambda k: (not k.startswith("judge"), "leak" in k, k))
    md = [
        f"# Utterance agents baseline (split, 2 agents) · {dt.date.today().isoformat()}",
        "",
        "**What runs:**",
        "- The 39 utterance eval cases (`data/eval/utterance_cases.jsonl`), text in as the final transcript.",
        f"- The real UtteranceJudge and FactChecker on `{settings.LLM_FAST_MODEL}` (thinking {settings.LLM_FAST_THINKING}), "
        f"called in parallel, deadlines {settings.JUDGE_TIMEOUT_MS} / {settings.FACT_TIMEOUT_MS} ms.",
        f"- {runs} runs, so {runs * len(cases)} case runs, 6 cases at a time (12 calls in flight). Every run is scored.",
        "- No orchestrator code: the agents' outputs are scored directly.",
        "- The fact checker is scored twice: its raw model answer, and after its own quote check (`post_validate`).",
        "- Script: `backend/scripts/eval_agents.py` (`--from-json` re-scores saved outputs).",
        "",
        "**Leak** means an agent answering in the other agent's area:",
        "- judge: a compliance alert on a sentence with no compliance claim (prices, facts, answers, transitions);",
        "- fact checker: a \"wrong fact\" note on a sentence that is not about facts (compliance claims, answers, transitions).",
        "",
        "**Accuracy** is over the runs where the agent answered in time; timeouts are counted separately.",
        "",
        "## Accuracy",
        "| Check | Correct / answered | Wrong | Timeout |",
        "|---|---|---|---|",
        *[row(k) for k in keys],
        "",
        "## Latency (each agent, and both done = the slower of the two)",
        f"- **Judge:** {lat(judge_ms)}",
        f"- **Fact checker:** {lat(facts_ms)}",
        f"- **Both done:** {lat(wall_ms)}",
        f"- **Statuses:** {dict(statuses)}",
        "",
        "## Wrong answers (case: what came back × runs)",
    ]
    for k in keys:
        if misses[k]:
            md.append(f"- **{k}:** " + "; ".join(f"{w[:160]} ×{n}" for w, n in misses[k].most_common(8)))
    out.write_text("\n".join(md) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(md[17:]))
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
