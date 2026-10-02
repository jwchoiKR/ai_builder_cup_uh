"""Utterance agents on the eval cases: accuracy in each agent's own area, leaks into the other
agents' areas, latency and timeouts. Every run is scored (run_eval.py scores run 1 only).

Structures:
  split3 (production, JUDGE_MODE=split3, D-099): ComplianceJudge (compliance, correction) + ContextJudge
         (answer, prompter, switch) + FactChecker, all in parallel. The production agents and prompts.
  split2 (JUDGE_MODE=split, rollback): UtteranceJudge (compliance, correction, answer, prompter,
         switch) + FactChecker.
  router3 (experiment): an LLM router (scripts/experiments/prompts/router.md) first, then only the
         chosen specialists.

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
from app.agents.split_judges import ComplianceJudge, ContextJudge  # noqa: E402
from app.agents.utterance_judge import JudgeInput, UtteranceJudge  # noqa: E402
from app.agents.utterance_judge import post_validate as judge_post_validate  # noqa: E402
from app.clock import SystemClock  # noqa: E402
from app.config import REPO_DIR, get_settings  # noqa: E402
from app.logic.catalog import Catalog, DataPack  # noqa: E402
from app.logic.reflex import Reflex  # noqa: E402
from app.models.agent_io import ComplianceOutput, ContextOutput, UtteranceJudgeOutput  # noqa: E402
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


class RouterOutput(BaseModel):
    compliance: bool
    facts: bool
    context: bool
    reason: str


ROUTER_DEADLINE_MS = 1500  # experiment choice; on timeout or error every specialist runs
NEEDS = {  # cases a specialist must see for the expected result
    "compliance": set(VIOLATION) | {"U38"},
    "facts": set(FACT_WRONG),
}
EMPTY_FACTS = {"claims": [], "reason": "not routed"}


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
    reflex = Reflex(pack.rules)
    judge = UtteranceJudge(client, prompts, catalog, reflex)
    comp_judge, ctx_judge = ComplianceJudge(client, prompts, catalog, reflex), ContextJudge(client, prompts, catalog, reflex)
    facts = FactChecker(client, prompts["fact_checker"], catalog)
    comp_t, ctx_t = prompts["compliance_judge"], prompts["context_judge"]
    router_t = exp_template("router") if structure == "router3" else None
    retriever = LocalRetriever(pack.passages)
    prefetched: dict = {}
    print("warm-up:", await client.warm_up())
    now = SystemClock().now_ms()
    cases = load_cases("utterance_cases.jsonl")
    sem = asyncio.Semaphore(concurrency)

    def call(template, output_model, values: dict, utterance: str, agent: str, deadline_ms: int | None = None):
        return client.call(LLMRequest(
            agent=agent, model=client.fast.model, thinking_level=client.fast.thinking_level,
            prompt_version=template.version, system_instruction=template.system_instruction,
            user_message=template.render(values), output_model=output_model,
            deadline_ms=deadline_ms or settings.JUDGE_TIMEOUT_MS, mock_primary_text=utterance, mock_scenario="eval",
            preview=utterance))

    async def skipped():
        return None

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
                route = {"compliance": True, "facts": True, "context": True}
                router_ms = 0
                if structure == "router3":
                    r = await call(router_t, RouterOutput, values, utt, "router", ROUTER_DEADLINE_MS)
                    router_ms = r.latency_ms
                    row |= {"router_status": r.status, "router_ms": r.latency_ms}
                    if r.output is not None:  # on timeout or error every specialist runs
                        route = {"compliance": r.output.compliance, "facts": r.output.facts, "context": r.output.context}
                    row["route"] = route
                if structure == "split3":  # the production agents
                    comp_call = comp_judge.run(jin, deadline_ms=settings.JUDGE_TIMEOUT_MS, values=values)
                    ctx_call = ctx_judge.run(jin, deadline_ms=settings.JUDGE_TIMEOUT_MS, values=values)
                else:
                    comp_call = call(comp_t, ComplianceOutput, values, utt, "compliance_judge") if route["compliance"] else skipped()
                    ctx_call = call(ctx_t, ContextOutput, values, utt, "context_judge") if route["context"] else skipped()
                c, x, f = await asyncio.gather(
                    comp_call, ctx_call, facts.run(fin, deadline_ms=settings.FACT_TIMEOUT_MS) if route["facts"] else skipped())
                if structure == "router3":
                    # a specialist that was not chosen "answers" nothing as soon as the router has decided
                    row |= {"comp_status": c.status if c else "ok", "comp_ms": router_ms + (c.latency_ms if c else 0),
                            "ctx_status": x.status if x else "ok", "ctx_ms": router_ms + (x.latency_ms if x else 0)}
                    if f is None:
                        row |= {"facts_status": "ok", "facts_ms": router_ms, "facts_raw": EMPTY_FACTS,
                                "facts_validated": EMPTY_FACTS}
                c = c or type("Skipped", (), {"output": None, "status": "ok", "latency_ms": 0})()
                x = x or type("Skipped", (), {"output": None, "status": "ok", "latency_ms": 0})()
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
                if structure == "split3":
                    row |= {"comp_status": c.status, "comp_ms": c.latency_ms, "ctx_status": x.status, "ctx_ms": x.latency_ms}
                row["judge"] = judge_post_validate(merged, catalog, values).model_dump(mode="json")
                if f is None:  # router3: facts not chosen
                    return row
                if structure == "router3":
                    validated = _fact_post_validate(f.output, passages, catalog, promo) if f.output is not None else None
                    return row | {"facts_status": f.status, "facts_ms": row["router_ms"] + f.latency_ms,
                                  "facts_raw": f.output.model_dump(mode="json") if f.output else None,
                                  "facts_validated": validated.model_dump(mode="json") if validated else None}
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
    # routing (router3 only): calls per sentence, routes a needed specialist did not get
    routing = None
    if any("route" in x for x in raw):
        context_needed = set(ANSWER_YES) | {"U35", "U36", "U37"} | {c["case_id"] for c in cases if "covered_points" in c["expected"]}
        needs = NEEDS | {"context": context_needed}
        missed = collections.Counter()
        chosen = collections.Counter()
        router_ms = [x["router_ms"] for x in raw if x.get("router_status") == "ok"]
        for x in raw:
            route = x.get("route") or {}
            for spec, ids in needs.items():
                if route.get(spec):
                    chosen[spec] += 1
                elif x["id"] in ids:
                    missed[f"{spec}: {x['id']}"] += 1
        calls = [1 + sum(bool(v) for v in (x.get("route") or {}).values()) for x in raw]
        routing = {"router_ms": router_ms, "router_timeouts": sum(x.get("router_status") != "ok" for x in raw),
                   "calls": sum(calls) / len(calls), "missed": missed, "chosen": chosen}
    return {"tally": tally, "misses": misses, "comp_ms": comp_ms, "ctx_ms": ctx_ms, "facts_ms": facts_ms,
            "all_ms": all_ms, "timeouts": timeouts, "n": len(raw), "routing": routing}


def acc(c: collections.Counter) -> str:
    answered = c["ok"] + c["wrong"]
    return f"{c['ok']}/{answered} ({100 * c['ok'] / answered:.1f}%)" if answered else "n/a"


def lat(v: list[int]) -> str:
    return f"p50 {pct(v, 0.5):.0f} · p95 {pct(v, 0.95):.0f} · max {max(v)} ms" if v else "n/a"


def ordered(keys) -> list[str]:
    return sorted(keys, key=lambda k: (not k.startswith("judge"), k not in COMP_KEYS, "leak" in k, k))


AGENTS = {
    "split2": "UtteranceJudge + FactChecker in parallel (JUDGE_MODE=split, rollback)",
    "split3": "ComplianceJudge + ContextJudge + FactChecker in parallel (production, D-099)",
    "router3": "LLM router first, then only the chosen of ComplianceJudge / ContextJudge / FactChecker in parallel (experiment)",
}


def routing_lines(s: dict) -> list[str]:
    r = s["routing"]
    if not r:
        return []
    missed = "; ".join(f"{k} ×{n}" for k, n in r["missed"].most_common()) or "none"
    return [
        f"- **Router:** {lat(r['router_ms'])}; timed out {r['router_timeouts']}/{s['n']} (then every specialist runs)",
        f"- **Model calls per sentence:** {r['calls']:.2f} (router included)",
        f"- **Specialist chosen:** " + ", ".join(f"{k} {r['chosen'][k]}/{s['n']}" for k in ("compliance", "context", "facts")),
        f"- **Needed specialist not chosen (case × runs):** {missed}",
    ]


def write_report(structure: str, raw: list[dict], cases: list[dict], out: Path, settings) -> None:
    s = score(raw, cases)
    runs = max(x["run"] for x in raw) + 1
    md = [
        f"# Utterance agents · {structure} · {dt.date.today().isoformat()}",
        "",
        f"- **Agents:** {AGENTS[structure]}, on `{settings.LLM_FAST_MODEL}` (thinking {settings.LLM_FAST_THINKING}).",
        f"- **Runs:** 39 eval cases × {runs} runs = {s['n']} case runs; every run scored. Timeouts are counted apart from wrong answers.",
        "- **Script:** `backend/scripts/eval_agents.py`; production prompts in `prompts/`, the router prompt in "
        "`backend/scripts/experiments/prompts/`. Judge outputs get the production `post_validate`.",
        "",
        "| Check | Correct / answered | Wrong | Timeout |",
        "|---|---|---|---|",
        *[f"| {k} | {acc(s['tally'][k])} | {s['tally'][k]['wrong']} | {s['tally'][k]['timeout']} |" for k in ordered(s["tally"])],
        "",
        f"- **Compliance verdict ready (red alert path):** {lat(s['comp_ms'])}",
        f"- **Answer / prompter / switch verdict ready:** {lat(s['ctx_ms'])}",
        f"- **Fact verdict ready:** {lat(s['facts_ms'])}",
        f"- **All done:** {lat(s['all_ms'])}",
        f"- **Timeouts:** {dict(s['timeouts']) or 'none'} of {s['n']} each",
        *routing_lines(s),
        "",
        "## Wrong answers (case: what came back × runs)",
    ]
    for k in ordered(s["tally"]):
        if s["misses"][k]:
            md.append(f"- **{k}:** " + "; ".join(f"{w[:150]} ×{n}" for w, n in s["misses"][k].most_common(6)))
    out.write_text("\n".join(md) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(md[6:]))
    print(f"report: {out}")


def write_compare(runs: list[tuple[str, list[dict]]], cases: list[dict], out: Path, settings) -> None:
    labels = [label for label, _ in runs]
    scores = [score(raw, cases) for _, raw in runs]
    keys = ordered(set().union(*(sc["tally"] for sc in scores)))

    def to(sc: dict, name: str) -> str:
        return f"{sc['timeouts'].get(name, 0)}/{sc['n']} ({100 * sc['timeouts'].get(name, 0) / sc['n']:.1f}%)"

    def calls(sc: dict, label: str) -> str:
        if sc["routing"]:
            return f"{sc['routing']['calls']:.2f}"
        return "2" if "2" in label.split()[0] else "3"

    head = "| | " + " | ".join(labels) + " |"
    sep = "|---|" + "---|" * len(labels)
    md = [
        f"# Utterance agent structures compared · {dt.date.today().isoformat()}",
        "",
        "**Structures:**",
        *[f"- **{label}:** {AGENTS[raw[0].get('structure', 'router3' if 'route' in raw[0] else ('split3' if 'comp_ms' in raw[0] and raw[0].get('comp_ms') != raw[0].get('ctx_ms') else 'split2'))]}"
          for label, raw in runs],
        "",
        "**Same conditions:**",
        f"- 39 eval cases × 20 runs on `{settings.LLM_FAST_MODEL}` (thinking {settings.LLM_FAST_THINKING}).",
        "- The same specialist prompts (compliance_judge and context_judge are cut from utterance_judge with the same wording).",
        "- At most 12 specialist calls in flight. Timeouts are counted apart from wrong answers.",
        "",
        "## Accuracy (correct / answered in time)",
        "| Check | " + " | ".join(labels) + " |",
        sep,
        *[f"| {k} | " + " | ".join(acc(sc["tally"][k]) for sc in scores) + " |" for k in keys],
        "",
        "## Speed and cost",
        head,
        sep,
        "| Compliance verdict ready (red alert path) | " + " | ".join(lat(sc["comp_ms"]) for sc in scores) + " |",
        "| Answer / prompter / switch verdict ready | " + " | ".join(lat(sc["ctx_ms"]) for sc in scores) + " |",
        "| Fact verdict ready | " + " | ".join(lat(sc["facts_ms"]) for sc in scores) + " |",
        "| All done | " + " | ".join(lat(sc["all_ms"]) for sc in scores) + " |",
        "| Compliance part timed out | " + " | ".join(to(sc, "compliance part") for sc in scores) + " |",
        "| Answer/prompter/switch part timed out | " + " | ".join(to(sc, "context part") for sc in scores) + " |",
        "| Fact checker timed out | " + " | ".join(to(sc, "fact checker") for sc in scores) + " |",
        "| Model calls per sentence | " + " | ".join(calls(sc, label) for sc, label in zip(scores, labels)) + " |",
        "",
    ]
    for label, sc in zip(labels, scores):
        if sc["routing"]:
            md += [f"## Routing ({label})", *routing_lines(sc), ""]
    md.append("## Wrong answers")
    for label, sc in zip(labels, scores):
        for k in keys:
            if sc["misses"][k]:
                md.append(f"- **{label} · {k}:** " + "; ".join(f"{w[:120]} ×{n}" for w, n in sc["misses"][k].most_common(5)))
    out.write_text("\n".join(md) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(md[10:]))
    print(f"report: {out}")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--structure", choices=["split2", "split3", "router3"], default="split2")
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--concurrency", type=int, default=None, help="cases at a time (default: 12 specialist calls in flight)")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--from-json", type=Path, default=None, help="re-score saved outputs without calling the models")
    ap.add_argument("--compare", nargs="+", default=None, metavar="LABEL=JSON",
                    help="compare saved runs, e.g. '2 agents=docs/eval/agents-baseline.json'")
    args = ap.parse_args()
    settings = get_settings()
    cases = load_cases("utterance_cases.jsonl")
    if args.compare:
        runs = []
        for item in args.compare:
            label, path = item.split("=", 1)
            runs.append((label, json.loads(Path(path).read_text(encoding="utf-8"))))
        write_compare(runs, cases, args.out or EVAL_DIR / "agents-compare.md", settings)
        return 0
    name = {"split2": "agents-baseline", "split3": "agents-split3", "router3": "agents-router3"}[args.structure]
    out = args.out or EVAL_DIR / f"{name}.md"
    if args.from_json:
        raw = json.loads(args.from_json.read_text(encoding="utf-8"))
    else:
        concurrency = args.concurrency or (6 if args.structure == "split2" else 4)  # 12 specialist calls in flight
        raw = await run(args.structure, args.runs, concurrency)
        for x in raw:
            x["structure"] = args.structure
        out.with_suffix(".json").write_text(json.dumps(raw, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    write_report(args.structure, raw, cases, out, settings)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
