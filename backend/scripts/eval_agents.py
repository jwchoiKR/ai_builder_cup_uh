"""Utterance agents on the eval cases: accuracy in each agent's own area, leaks into the other
agents' areas, latency and timeouts. Every run is scored (run_eval.py scores run 1 only).

Structures:
  split2 (production): UtteranceJudge (compliance, correction, answer, prompter, switch) + FactChecker.
  split3 (experiment): ComplianceJudge (compliance, correction) + ContextJudge (answer, prompter,
         switch) + FactChecker, all in parallel. Prompts in scripts/experiments/prompts/, cut from
         prompts/utterance_judge.md with the same wording.

Inputs are the 39 utterance eval cases (data/eval/utterance_cases.jsonl) built as run_eval.py does:
text in as the final transcript, real models on Vertex AI. No orchestrator code runs. Judge outputs
get the production post_validate (unknown ids dropped, severity from the rule). The fact checker is
scored twice: raw, and after its own quote check (post_validate).

    uv run python scripts/eval_agents.py --structure split2 --runs 20      # docs/eval/agents-baseline.md
    uv run python scripts/eval_agents.py --structure split3 --runs 20      # docs/eval/agents-split3.md
    uv run python scripts/eval_agents.py --compare A.json B.json           # docs/eval/agents-2vs3.md
    uv run python scripts/eval_agents.py --from-json A.json                # re-score saved outputs
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import datetime as dt
import json
import sys
from pathlib import Path

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import app.agents.fact_checker as fc_module  # noqa: E402
from app.agents.fact_checker import FactChecker, FactInput, gather_fact_passages  # noqa: E402
from app.agents.inputs import BUILDERS  # noqa: E402
from app.agents.utterance_judge import JudgeInput, UtteranceJudge  # noqa: E402
from app.agents.utterance_judge import post_validate as judge_post_validate  # noqa: E402
from app.clock import SystemClock  # noqa: E402
from app.config import REPO_DIR, get_settings  # noqa: E402
from app.logic.catalog import Catalog, DataPack  # noqa: E402
from app.logic.reflex import Reflex  # noqa: E402
from app.models.agent_io import AnswerLink, Compliance, Correction, PrompterJudgement, UtteranceJudgeOutput  # noqa: E402
from app.models.session import Alert, SwitchState  # noqa: E402
from app.providers.llm import LLMRequest  # noqa: E402
from app.providers.prompts import (  # noqa: E402
    _examples_text, _parse_file, _template, _until_rule, _with_examples, load_prompts,
)
from app.providers.retriever import LocalRetriever  # noqa: E402
from run_eval import _group, _same_value, load_cases, make_client, pct  # noqa: E402

VIOLATION = [f"U{i:02d}" for i in range(1, 13)] + ["U23"]
CLEAN = [f"U{i:02d}" for i in range(13, 19)]
FACT_WRONG = ["U19", "U21", "U23", "U27"]
FACT_RIGHT = ["U20", "U22", "U24", "U26", "U25", "U39"]
ANSWER_YES, ANSWER_NO = ["U28", "U31"], ["U29", "U30"]
EXP_PROMPTS = Path(__file__).resolve().parent / "experiments" / "prompts"
EVAL_DIR = REPO_DIR / "docs" / "eval"

# Keep the fact checker's raw model answer: run() normally applies post_validate before returning.
_fact_post_validate = fc_module.post_validate
fc_module.post_validate = lambda out, *a, **k: out


class ComplianceOutput(BaseModel):
    compliance: Compliance
    correction: Correction
    reason: str


class ContextOutput(BaseModel):
    answer: AnswerLink
    prompter: PrompterJudgement
    reason: str


def exp_template(name: str):
    pf = _parse_file(EXP_PROMPTS / f"{name}.md")
    return _template(pf, _with_examples(_until_rule(pf.require("SYSTEM INSTRUCTION").lines), _examples_text(pf)))


# ---- running ---------------------------------------------------------------------------------------


async def run(structure: str, runs: int, concurrency: int) -> list[dict]:
    settings = get_settings()
    pack = DataPack.load(settings.data_path)
    catalog = Catalog(pack)
    prompts = load_prompts(settings.prompts_path, BUILDERS)
    client, _ = make_client(False)
    judge = UtteranceJudge(client, prompts, catalog, Reflex(pack.rules))
    facts = FactChecker(client, prompts["fact_checker"], catalog)
    comp_t, ctx_t = (exp_template("compliance_judge"), exp_template("context_judge")) if structure == "split3" else (None, None)
    retriever = LocalRetriever(pack.passages)
    prefetched: dict = {}
    print("warm-up:", await client.warm_up())
    now = SystemClock().now_ms()
    cases = load_cases("utterance_cases.jsonl")
    sem = asyncio.Semaphore(concurrency)

    def call(template, output_model, values: dict, utterance: str, agent: str):
        return client.call(LLMRequest(
            agent=agent, model=client.fast.model, thinking_level=client.fast.thinking_level,
            prompt_version=template.version, system_instruction=template.system_instruction,
            user_message=template.render(values), output_model=output_model,
            deadline_ms=settings.JUDGE_TIMEOUT_MS, mock_primary_text=utterance, mock_scenario="eval", preview=utterance))

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
        utt = case["utterance"]
        async with sem:
            passages = await gather_fact_passages(retriever, catalog, prefetched, utterance=utt, on_air=on_air,
                                                  switch=switch, search_timeout_ms=settings.FACT_SEARCH_TIMEOUT_MS)
            jin = JudgeInput(utterance=utt, on_air=on_air, active_alerts=alerts, open_questions=questions,
                             previous=previous, scenario="eval", switch=switch, promo=promo, passages=passages)
            fin = FactInput(utterance=utt, on_air=on_air, switch=switch, promo=promo, passages=passages,
                            previous=previous, scenario="eval")
            row: dict = {"id": case["case_id"], "run": run_no}
            if structure == "split2":
                j, f = await asyncio.gather(judge.run(jin, deadline_ms=settings.JUDGE_TIMEOUT_MS),
                                            facts.run(fin, deadline_ms=settings.FACT_TIMEOUT_MS))
                row |= {"comp_status": j.status, "comp_ms": j.latency_ms, "ctx_status": j.status, "ctx_ms": j.latency_ms,
                        "judge": j.output.model_dump(mode="json") if j.output else None}
            else:
                values = judge.build_values(jin)
                c, x, f = await asyncio.gather(call(comp_t, ComplianceOutput, values, utt, "compliance_judge"),
                                               call(ctx_t, ContextOutput, values, utt, "context_judge"),
                                               facts.run(fin, deadline_ms=settings.FACT_TIMEOUT_MS))
                merged = UtteranceJudgeOutput.model_validate({
                    "compliance": c.output.compliance.model_dump() if c.output else {"violations": []},
                    "correction": c.output.correction.model_dump() if c.output else {"corrects_alert_ids": []},
                    "answer": x.output.answer.model_dump() if x.output else {
                        "utterance_type": "other", "matched_group_id": None, "is_answer": False, "consistent_with_suggested": False},
                    "prompter": x.output.prompter.model_dump() if x.output else {
                        "covered_point_ids": [], "covered_cue_ids": [],
                        "switch": {"is_transition": False, "is_quote": False, "target_product_id": None, "confidence": "low"}},
                    "reason": " | ".join(o.output.reason for o in (c, x) if o.output),
                })
                row |= {"comp_status": c.status, "comp_ms": c.latency_ms, "ctx_status": x.status, "ctx_ms": x.latency_ms,
                        "judge": judge_post_validate(merged, catalog, values).model_dump(mode="json")}
        validated = _fact_post_validate(f.output, passages, catalog, promo) if f.output is not None else None
        return row | {"facts_status": f.status, "facts_ms": f.latency_ms,
                      "facts_raw": f.output.model_dump(mode="json") if f.output else None,
                      "facts_validated": validated.model_dump(mode="json") if validated else None}

    results = []
    for r in range(runs):
        results += await asyncio.gather(*(one(c, r) for c in cases))
        print(f"run {r + 1}/{runs} done")
    await client.aclose()
    return results


# ---- scoring ---------------------------------------------------------------------------------------

COMP_KEYS = ("judge · catches the violation (right rule)", "judge · no alert on negated/quoted/approved wording",
             "judge · correction", "judge · leak: alert on a sentence with no compliance claim")


def _st(x: dict, key: str) -> str:
    return x.get(key, x.get("judge_status"))  # runs saved before split3 have one judge_status


def _ms(x: dict, key: str) -> int:
    return x.get(key, x.get("judge_ms"))


def score(raw: list[dict], cases: list[dict]) -> dict:
    """A timed-out agent counts as a timeout, never as a right or wrong answer."""
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

    for x in raw:
        cid, exp, jo = x["id"], by_id[x["id"]]["expected"], x["judge"] or {}
        cs, xs = _st(x, "comp_status"), _st(x, "ctx_status")
        active = [v for v in ((jo.get("compliance") or {}).get("violations") or []) if not v["is_negated"] and not v["is_quoted"]]
        av = ",".join(v["rule_id"] for v in active) or "none"
        if cid in VIOLATION:
            mark(COMP_KEYS[0], cid, cs, any(v["rule_id"] == exp["rule_id"] for v in active), f"got {av}")
        if cid in CLEAN:
            mark(COMP_KEYS[1], cid, cs, not active, f"got {av}")
        if cid in non_compliance:
            mark(COMP_KEYS[3], cid, cs, not active, f"got {av}")
        if cid == "U38":
            mark(COMP_KEYS[2], cid, cs, "al_u01" in ((jo.get("correction") or {}).get("corrects_alert_ids") or []), "not corrected")
        a = jo.get("answer") or {}
        pr = jo.get("prompter") or {"covered_point_ids": [], "switch": {}}
        sw = pr.get("switch") or {}
        if cid in ANSWER_YES:
            mark("judge · answer linking", cid, xs, bool(a) and a["is_answer"] and a["consistent_with_suggested"]
                 and a["matched_group_id"] == exp["matched_group"], f"is_answer={a.get('is_answer')}")
        if cid in ANSWER_NO:
            mark("judge · answer linking", cid, xs, bool(a) and not a["is_answer"], "read-out taken as an answer")
        if cid == "U35":
            mark("judge · switch", cid, xs, bool(sw.get("is_transition")) and sw.get("target_product_id") == "ampoule_deep_hydration", "no transition")
        if cid == "U34":
            mark("judge · switch", cid, xs, not sw.get("is_transition") or bool(sw.get("is_quote")), "mention taken as a transition")
        if cid == "U36":
            mark("judge · switch", cid, xs, "am-p2" in pr["covered_point_ids"], f"covered={pr['covered_point_ids']}")
        if cid == "U37":
            mark("judge · switch", cid, xs, bool(sw.get("is_transition")) and sw.get("target_product_id") == "cream_hydra_barrier", "not back to cream")
        if "covered_points" in exp:
            mark("judge · prompter points", cid, xs, set(exp["covered_points"]) <= set(pr["covered_point_ids"]),
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

    comp_ms = [_ms(x, "comp_ms") for x in raw if _st(x, "comp_status") == "ok"]
    ctx_ms = [_ms(x, "ctx_ms") for x in raw if _st(x, "ctx_status") == "ok"]
    facts_ms = [x["facts_ms"] for x in raw if x["facts_status"] == "ok"]
    all_ms = [max(_ms(x, "comp_ms"), _ms(x, "ctx_ms"), x["facts_ms"]) for x in raw
              if _st(x, "comp_status") == "ok" and _st(x, "ctx_status") == "ok" and x["facts_status"] == "ok"]
    timeouts = collections.Counter()
    for x in raw:
        for name, key in (("compliance part", "comp_status"), ("context part", "ctx_status"), ("fact checker", "facts_status")):
            if (_st(x, key) if key != "facts_status" else x["facts_status"]) != "ok":
                timeouts[name] += 1
    return {"tally": tally, "misses": misses, "comp_ms": comp_ms, "ctx_ms": ctx_ms, "facts_ms": facts_ms,
            "all_ms": all_ms, "timeouts": timeouts, "n": len(raw)}


def acc(c: collections.Counter) -> str:
    answered = c["ok"] + c["wrong"]
    return f"{c['ok']}/{answered} ({100 * c['ok'] / answered:.1f}%)" if answered else "n/a"


def lat(v: list[int]) -> str:
    return f"p50 {pct(v, 0.5):.0f} · p95 {pct(v, 0.95):.0f} · max {max(v)} ms" if v else "n/a"


def ordered(keys) -> list[str]:
    return sorted(keys, key=lambda k: (not k.startswith("judge"), k not in COMP_KEYS, "leak" in k, k))


def write_report(structure: str, raw: list[dict], cases: list[dict], out: Path, settings) -> None:
    s = score(raw, cases)
    runs = max(x["run"] for x in raw) + 1
    agents = ("UtteranceJudge + FactChecker" if structure == "split2"
              else "ComplianceJudge + ContextJudge + FactChecker (experiment prompts in scripts/experiments/prompts/)")
    md = [
        f"# Utterance agents · {structure} · {dt.date.today().isoformat()}",
        "",
        f"- **Agents:** {agents}, in parallel, on `{settings.LLM_FAST_MODEL}` (thinking {settings.LLM_FAST_THINKING}).",
        f"- **Runs:** 39 eval cases × {runs} runs = {s['n']} case runs; every run scored. Timeouts are counted apart from wrong answers.",
        "- **Script:** `backend/scripts/eval_agents.py`. No orchestrator code; judge outputs get the production `post_validate`.",
        "",
        "| Check | Correct / answered | Wrong | Timeout |",
        "|---|---|---|---|",
        *[f"| {k} | {acc(s['tally'][k])} | {s['tally'][k]['wrong']} | {s['tally'][k]['timeout']} |" for k in ordered(s["tally"])],
        "",
        f"- **Compliance verdict ready (red alert path):** {lat(s['comp_ms'])}",
        f"- **Answer / prompter / switch verdict ready:** {lat(s['ctx_ms'])}",
        f"- **Fact checker:** {lat(s['facts_ms'])}",
        f"- **All agents done:** {lat(s['all_ms'])}",
        f"- **Timeouts:** {dict(s['timeouts']) or 'none'} of {s['n']} each",
        "",
        "## Wrong answers (case: what came back × runs)",
    ]
    for k in ordered(s["tally"]):
        if s["misses"][k]:
            md.append(f"- **{k}:** " + "; ".join(f"{w[:150]} ×{n}" for w, n in s["misses"][k].most_common(6)))
    out.write_text("\n".join(md) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(md[6:]))
    print(f"report: {out}")


def write_compare(a_raw: list[dict], b_raw: list[dict], cases: list[dict], out: Path, settings) -> None:
    a, b = score(a_raw, cases), score(b_raw, cases)
    keys = ordered(set(a["tally"]) | set(b["tally"]))

    def to(s: dict, name: str) -> str:
        return f"{s['timeouts'].get(name, 0)}/{s['n']} ({100 * s['timeouts'].get(name, 0) / s['n']:.1f}%)"

    md = [
        f"# 2 agents vs 3 agents (utterance path) · {dt.date.today().isoformat()}",
        "",
        "**What is compared:**",
        "- **2 agents (production):** one UtteranceJudge (compliance, correction, answer, prompter, switch) and the FactChecker.",
        "- **3 agents (experiment):** a ComplianceJudge (compliance and correction), a ContextJudge (answer, prompter, switch) "
        "and the same FactChecker.",
        "- **Same conditions:** the two judges' prompts are cut from the production judge prompt with the same wording. "
        "All agents run in parallel on "
        f"`{settings.LLM_FAST_MODEL}`. Same 39 cases × {max(x['run'] for x in a_raw) + 1} runs, 12 model calls in flight "
        "in both runs. Timeouts are counted apart from wrong answers.",
        "- **Script:** `backend/scripts/eval_agents.py`.",
        "",
        "## Accuracy (correct / answered in time)",
        "| Check | 2 agents | 3 agents |",
        "|---|---|---|",
        *[f"| {k} | {acc(a['tally'][k])} | {acc(b['tally'][k])} |" for k in keys],
        "",
        "## Speed",
        "| | 2 agents | 3 agents |",
        "|---|---|---|",
        f"| Compliance verdict ready (red alert path) | {lat(a['comp_ms'])} | {lat(b['comp_ms'])} |",
        f"| Answer / prompter / switch verdict ready | {lat(a['ctx_ms'])} | {lat(b['ctx_ms'])} |",
        f"| Fact checker | {lat(a['facts_ms'])} | {lat(b['facts_ms'])} |",
        f"| All agents done | {lat(a['all_ms'])} | {lat(b['all_ms'])} |",
        f"| Compliance part timed out | {to(a, 'compliance part')} | {to(b, 'compliance part')} |",
        f"| Answer/prompter/switch part timed out | {to(a, 'context part')} | {to(b, 'context part')} |",
        f"| Fact checker timed out | {to(a, 'fact checker')} | {to(b, 'fact checker')} |",
        "| Model calls per sentence | 2 | 3 |",
        "",
        "## Wrong answers",
    ]
    for label, s in (("2 agents", a), ("3 agents", b)):
        for k in keys:
            if s["misses"][k]:
                md.append(f"- **{label} · {k}:** " + "; ".join(f"{w[:120]} ×{n}" for w, n in s["misses"][k].most_common(5)))
    out.write_text("\n".join(md) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(md[10:]))
    print(f"report: {out}")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--structure", choices=["split2", "split3"], default="split2")
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--concurrency", type=int, default=None, help="cases at a time (default: 12 calls in flight)")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--from-json", type=Path, default=None, help="re-score saved outputs without calling the models")
    ap.add_argument("--compare", nargs=2, type=Path, default=None, metavar=("TWO_AGENTS_JSON", "THREE_AGENTS_JSON"))
    args = ap.parse_args()
    settings = get_settings()
    cases = load_cases("utterance_cases.jsonl")
    if args.compare:
        a, b = (json.loads(p.read_text(encoding="utf-8")) for p in args.compare)
        write_compare(a, b, cases, args.out or EVAL_DIR / "agents-2vs3.md", settings)
        return 0
    name = "agents-baseline" if args.structure == "split2" else "agents-split3"
    out = args.out or EVAL_DIR / f"{name}.md"
    if args.from_json:
        raw = json.loads(args.from_json.read_text(encoding="utf-8"))
    else:
        concurrency = args.concurrency or (6 if args.structure == "split2" else 4)  # 12 calls in flight either way
        raw = await run(args.structure, args.runs, concurrency)
        out.with_suffix(".json").write_text(json.dumps(raw, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    write_report(args.structure, raw, cases, out, settings)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
