"""Utterance agents on the eval cases: accuracy in each agent's own area, leaks into the other
agents' areas, latency and timeouts. Every run is scored (run_eval.py scores run 1 only).

Structures:
  split3 (production, JUDGE_MODE=split3, D-099): ComplianceJudge (compliance, correction) + ContextJudge
         (answer, prompter, switch) + FactChecker, all in parallel. The production agents and prompts.
  split2 (JUDGE_MODE=split, rollback): UtteranceJudge (compliance, correction, answer, prompter,
         switch) + FactChecker.
  router3 (experiment): an LLM router (scripts/experiments/prompts/router.md) first, then only the
         chosen specialists.
  jev_selective: Jev routes all three specialists, with deterministic overrides and fail-open.
  jev_tiered: compliance and facts start immediately; Jev gates context only.
  gemini_selective: purpose-based Gemini routes all three specialists with the same overrides.
  gemini_tiered: compliance and facts start immediately; Gemini gates context only.

Inputs are the 39 utterance eval cases (data/eval/utterance_cases.jsonl) built as run_eval.py does:
text in as the final transcript, real models on Vertex AI. No orchestrator code runs. Judge outputs
get the production post_validate (unknown ids dropped, severity from the rule). The fact checker is
scored twice: raw, and after its own quote check (post_validate).

    uv run python scripts/eval_agents.py --structure split2 --runs 20      # docs/eval/agents-baseline.md
    uv run python scripts/eval_agents.py --structure split3 --runs 20      # docs/eval/agents-split3.md
    uv run python scripts/eval_agents.py --compare A.json B.json           # docs/eval/agents-2vs3.md
    uv run python scripts/eval_agents.py --from-json A.json                # re-score saved outputs
    uv run python scripts/eval_agents.py --from-json A.json --revalidate --out B.md
        # apply the current fact quote check to the saved raw fact outputs (same model answers)
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import datetime as dt
import json
import sys
import uuid
from pathlib import Path

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import app.agents.fact_checker as fc_module  # noqa: E402
from app.agents.fact_checker import FactChecker, FactInput, gather_fact_passages  # noqa: E402
from app.agents.inputs import BUILDERS  # noqa: E402
from app.agents.split_judges import ComplianceJudge, ContextJudge  # noqa: E402
from app.agents.utterance_judge import STATIC_JUDGE_KEYS, JudgeInput, UtteranceJudge  # noqa: E402
from app.agents.utterance_judge import post_validate as judge_post_validate  # noqa: E402
from app.clock import SystemClock  # noqa: E402
from app.config import REPO_DIR, get_settings  # noqa: E402
from app.logic.catalog import Catalog, DataPack  # noqa: E402
from app.logic.reflex import Reflex  # noqa: E402
from app.models.agent_io import ComplianceOutput, ContextOutput, FactCheckOutput, UtteranceJudgeOutput  # noqa: E402
from app.models.session import Alert, SwitchState  # noqa: E402
from app.providers.llm import LLMRequest  # noqa: E402
from app.providers.prompts import (  # noqa: E402
    _examples_text, _parse_file, _template, _until_rule, _with_examples, load_prompts,
)
from app.providers.retriever import LocalRetriever  # noqa: E402
from eval_expectations import expectation_checks
from run_eval import _group, _same_value, load_cases, make_client, pct  # noqa: E402
from experiments.gemini_router import GeminiRouter, GEMINI_ROUTER_DEADLINE_MS  # noqa: E402
from experiments.jev_router import (  # noqa: E402
    JevRouter, apply_route, build_state, get_threshold, routing_overrides,
)

EXP_PROMPTS = Path(__file__).resolve().parent / "experiments" / "prompts"
EVAL_DIR = REPO_DIR / "docs" / "eval"

# Keep the fact checker's raw model answer: run() normally applies post_validate before returning.
_fact_post_validate = fc_module.post_validate


class RouterOutput(BaseModel):
    compliance: bool
    facts: bool
    context: bool
    reason: str


ROUTER_DEADLINE_MS = 1500  # experiment choice; on timeout or error every specialist runs
EMPTY_FACTS = {"claims": [], "reason": "not routed"}


def needed_specialists(cases: list[dict]) -> dict[str, set[str]]:
    """Dispatch requirements come from labels, independently of case IDs."""
    return {
        "compliance": {c["case_id"] for c in cases if c.get("expected", {}).get("compliance") is True
                       or "corrects_alert_ids" in c.get("expected", {})},
        "facts": {c["case_id"] for c in cases if c.get("expected", {}).get("fact") == "contradicted"
                  or c.get("context", {}).get("active_fact_alerts")},
        "context": {c["case_id"] for c in cases if set(c.get("expected", {})) &
                    {"answer", "matched_group", "consistent_with_suggested", "covered_points", "switch"}},
    }


def exp_template(name: str):
    pf = _parse_file(EXP_PROMPTS / f"{name}.md")
    return _template(pf, _with_examples(_until_rule(pf.require("SYSTEM INSTRUCTION").lines), _examples_text(pf)))


def make_router(structure: str):
    if structure in ("jev_selective", "jev_tiered"):
        return JevRouter()
    if structure in ("gemini_selective", "gemini_tiered"):
        return GeminiRouter()
    return None


# ---- running ---------------------------------------------------------------------------------------


def case_switch_promo(case: dict, pack: DataPack) -> tuple[SwitchState, object]:
    ctx = case.get("context") or {}
    sw = ctx.get("switch_state") or {}
    switch = SwitchState(status=sw.get("status", "idle"), target_product_id=sw.get("target_product_id"),
                         cue_count=sw.get("cue_count", 0))
    return switch, pack.promos_by_id.get(ctx.get("active_promo_id") or "")


async def revalidate(raw: list[dict], cases: list[dict]) -> list[dict]:
    """Re-apply the current fact quote check to saved raw fact outputs (no model calls)."""
    settings = get_settings()
    pack = DataPack.load(settings.data_path)
    catalog = Catalog(pack)
    retriever = LocalRetriever(pack.passages)
    prefetched: dict = {}
    by_id = {c["case_id"]: c for c in cases}
    env: dict[str, tuple] = {}
    for x in raw:
        if x.get("facts_raw") is None or x.get("route", {}).get("facts") is False:
            continue
        case = by_id[x["id"]]
        if x["id"] not in env:
            switch, promo = case_switch_promo(case, pack)
            passages = await gather_fact_passages(retriever, catalog, prefetched, utterance=case["utterance"],
                                                  on_air=case["current_product_id"], switch=switch,
                                                  search_timeout_ms=settings.FACT_SEARCH_TIMEOUT_MS)
            env[x["id"]] = (passages, promo)
        passages, promo = env[x["id"]]
        out = _fact_post_validate(FactCheckOutput.model_validate(x["facts_raw"]), passages, catalog, promo,
                                  case["utterance"])
        x["facts_validated"] = out.model_dump(mode="json")
    return raw


async def run(structure: str, runs: int, concurrency: int, cases: list[dict] | None = None) -> list[dict]:
    settings = get_settings()
    pack = DataPack.load(settings.data_path)
    catalog = Catalog(pack)
    prompts = load_prompts(settings.prompts_path, BUILDERS)
    client, _ = make_client(False)
    reflex = Reflex(pack.rules, pack.lexicon)
    judge = UtteranceJudge(client, prompts, catalog, reflex)
    comp_judge, ctx_judge = ComplianceJudge(client, prompts, catalog, reflex), ContextJudge(client, prompts, catalog, reflex)
    facts = FactChecker(client, prompts["fact_checker"], catalog)
    comp_t, ctx_t = prompts["compliance_judge"], prompts["context_judge"]
    router_t = exp_template("router") if structure == "router3" else None
    router = make_router(structure)
    threshold = get_threshold() if structure.startswith("jev_") else 0.5 if router else None
    retriever = LocalRetriever(pack.passages)
    prefetched: dict = {}
    print("warm-up:", await client.warm_up())
    if router:
        await router.warm_up()
    now = SystemClock().now_ms()
    cases = cases if cases is not None else load_cases("utterance_cases.jsonl")
    sem = asyncio.Semaphore(concurrency)
    eval_session = "eval_" + uuid.uuid4().hex

    def call(template, output_model, values: dict, utterance: str, agent: str, deadline_ms: int | None = None):
        user, prefix = template.render_cached(values, STATIC_JUDGE_KEYS)
        return client.call(LLMRequest(
            agent=agent, model=client.fast.model, thinking_level=client.fast.thinking_level,
            prompt_version=template.version, system_instruction=template.system_instruction,
            user_message=user, output_model=output_model, session_id=eval_session,
            cache_prefix=prefix, cache_ttl_sec=sum(i.planned_duration_sec for i in catalog.runsheet.items),
            deadline_ms=deadline_ms or settings.JUDGE_TIMEOUT_MS, mock_primary_text=utterance, mock_scenario="eval",
            preview=utterance))

    async def skipped():
        return None

    async def one(case: dict, run_no: int) -> dict:
        ctx = case.get("context") or {}
        on_air = case["current_product_id"]
        switch, promo = case_switch_promo(case, pack)
        alerts = [Alert(alert_id=a["alert_id"], kind="compliance", status="active", transcript_id="tr_prev",
                        product_id=on_air, rule_id=a["rule_id"], severity=pack.rules_by_id[a["rule_id"]].severity,
                        span=a["span"], say_instead=a.get("say_instead"), created_at=now, shown_at=now)
                  for a in ctx.get("active_alerts", [])]
        questions = [(_group({**q, "intent": "suitability"}, now), q.get("suggested_answer"))
                     for q in ctx.get("open_questions", [])]
        previous = ctx.get("recent_transcript", [])
        utt = case["utterance"]
        async with sem:
            passages = await gather_fact_passages(retriever, catalog, prefetched, utterance=utt, on_air=on_air,
                                                  switch=switch, search_timeout_ms=settings.FACT_SEARCH_TIMEOUT_MS)
            jin = JudgeInput(utterance=utt, on_air=on_air, active_alerts=alerts, open_questions=questions,
                             previous=previous, scenario="eval", switch=switch, promo=promo, passages=passages,
                             session_id=eval_session, on_screen_group_id=case.get("shown_group_id"))
            fin = FactInput(utterance=utt, on_air=on_air, switch=switch, promo=promo, passages=passages,
                            previous=previous, scenario="eval", session_id=eval_session)
            row: dict = {"id": case["case_id"], "run": run_no}
            if structure == "split2":
                j, f = await asyncio.gather(judge.run(jin, deadline_ms=settings.JUDGE_TIMEOUT_MS),
                                            facts.run(fin, deadline_ms=settings.FACT_TIMEOUT_MS))
                row |= {"comp_status": j.status, "comp_ms": j.latency_ms, "ctx_status": j.status, "ctx_ms": j.latency_ms,
                        "judge_usage": getattr(j, "meta", {}).get("usage"),
                        "judge": j.output.model_dump(mode="json") if j.output else None}
            else:
                values = judge.build_values(jin)
                route = {"compliance": True, "facts": True, "context": True}
                router_ms = 0
                comp_task = fact_task = None
                if router:
                    forced, overrides = routing_overrides(case, reflex)
                    # These tasks start before waiting for the router in the tiered experiment.
                    if structure.endswith("_tiered"):
                        comp_task = asyncio.create_task(comp_judge.run(
                            jin, deadline_ms=settings.JUDGE_TIMEOUT_MS, values=values))
                        fact_task = asyncio.create_task(facts.run(fin, deadline_ms=settings.FACT_TIMEOUT_MS))
                    product = catalog.get_product(on_air)
                    points = [p.text for p in product.prompter_points]
                    probs, router_ms, status = await router.route(build_state(case, product.name, points))
                    route = apply_route(probs, threshold, forced)
                    if structure.endswith("_tiered"):
                        route |= {"compliance": True, "facts": True}
                    row |= {"router_status": status, "router_ms": router_ms, "route_probs": probs,
                            "route": route, "overrides": overrides, "route_threshold": threshold}
                    if structure.startswith("jev_"):
                        row["jev_threshold"] = threshold
                if structure == "router3":
                    r = await call(router_t, RouterOutput, values, utt, "router", ROUTER_DEADLINE_MS)
                    router_ms = r.latency_ms
                    row |= {"router_status": r.status, "router_ms": r.latency_ms}
                    if r.output is not None:  # on timeout or error every specialist runs
                        route = {"compliance": r.output.compliance, "facts": r.output.facts, "context": r.output.context}
                    row["route"] = route
                if structure == "split3" or router:  # the production agents
                    comp_call = comp_task if comp_task is not None else (
                        comp_judge.run(jin, deadline_ms=settings.JUDGE_TIMEOUT_MS, values=values)
                        if route["compliance"] else skipped())
                    ctx_call = (ctx_judge.run(jin, deadline_ms=settings.JUDGE_TIMEOUT_MS, values=values)
                                if route["context"] else skipped())
                else:
                    comp_call = call(comp_t, ComplianceOutput, values, utt, "compliance_judge") if route["compliance"] else skipped()
                    ctx_call = call(ctx_t, ContextOutput, values, utt, "context_judge") if route["context"] else skipped()
                c, x, f = await asyncio.gather(
                    comp_call, ctx_call, fact_task if fact_task is not None else (
                        facts.run(fin, deadline_ms=settings.FACT_TIMEOUT_MS) if route["facts"] else skipped()))
                if structure == "router3" or router:
                    # a specialist that was not chosen "answers" nothing as soon as the router has decided
                    comp_delay = 0 if structure.endswith("_tiered") else router_ms
                    row |= {"comp_status": c.status if c else "ok", "comp_ms": comp_delay + (c.latency_ms if c else 0),
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
                if structure == "split3" and row["judge"]["answer"]["matched_group_id"] is None:  # a timeout too
                    # D-175: as the runtime does, ask once more about the one draft the line seems to answer
                    from dataclasses import replace as _replace

                    from app.logic.publish import relink_candidate
                    cand = relink_candidate(utt, {g.group_id: a for g, a in questions if a}, pack.lexicon)
                    if cand is not None:
                        one = [(g, a) for g, a in questions if g.group_id == cand]
                        jin2 = _replace(jin, open_questions=one, on_screen_group_id=cand)
                        x2 = await ctx_judge.run(jin2, deadline_ms=settings.JUDGE_TIMEOUT_MS,
                                                 values=judge.build_values(jin2))
                        row["ctx_relink"] = {"group_id": cand, "status": x2.status, "ms": x2.latency_ms,
                                             "answer": x2.output.answer.model_dump(mode="json") if x2.output else None}
                row["compliance_usage"] = getattr(c, "meta", {}).get("usage")
                row["context_usage"] = getattr(x, "meta", {}).get("usage")
                if f is None:  # router3: facts not chosen
                    return row
                if structure == "router3" or router:
                    validated = _fact_post_validate(f.output, passages, catalog, promo, utt) if f.output is not None else None
                    fact_delay = 0 if structure.endswith("_tiered") else router_ms
                    return row | {"facts_status": f.status, "facts_ms": fact_delay + f.latency_ms,
                                  "facts_usage": getattr(f, "meta", {}).get("usage"),
                                  "facts_raw": f.output.model_dump(mode="json") if f.output else None,
                                  "facts_validated": validated.model_dump(mode="json") if validated else None}
        validated = _fact_post_validate(f.output, passages, catalog, promo, utt) if f.output is not None else None
        return row | {"facts_status": f.status, "facts_ms": f.latency_ms,
                      "facts_usage": getattr(f, "meta", {}).get("usage"),
                      "facts_raw": f.output.model_dump(mode="json") if f.output else None,
                      "facts_validated": validated.model_dump(mode="json") if validated else None}

    results = []
    fc_module.post_validate = lambda out, *a, **k: out
    try:
        for r in range(runs):
            results += await asyncio.gather(*(one(c, r) for c in cases))
            print(f"run {r + 1}/{runs} done")
    finally:
        fc_module.post_validate = _fact_post_validate
        await client.aclose()
        if router:
            await router.aclose()
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
        cid = x["id"]
        for label, fact_key in (("raw", "facts_raw"), ("after quote check", "facts_validated")):
            checks = expectation_checks(by_id[cid]["expected"], x.get("judge") or {},
                                        x.get(fact_key) or {}, _same_value)
            for area, name, ok, detail in checks:
                if area != "facts" and label != "raw":
                    continue
                key = f"facts ({label}) · {name}" if area == "facts" else f"judge · {name}"
                status = x.get("facts_status") if area == "facts" else _st(x, f"{area}_status")
                if status == "ok" and ((area == "facts" and x.get(fact_key) is None)
                                       or (area != "facts" and x.get("judge") is None)):
                    status = "invalid"
                mark(key, cid, status, ok, detail)
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
        needs = needed_specialists(cases)
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
    "gemini_selective": "Gemini first, then selected specialists in parallel (experiment)",
    "gemini_tiered": "ComplianceJudge and FactChecker immediately; Gemini gates ContextJudge (experiment)",
    "jev_selective": "Jev first, then selected specialists in parallel (experiment)",
    "jev_tiered": "ComplianceJudge and FactChecker immediately; Jev gates ContextJudge (experiment)",
}


def routing_lines(s: dict) -> list[str]:
    r = s["routing"]
    if not r:
        return []
    missed_by_specialist = {spec: sum(n for key, n in r["missed"].items() if key.startswith(spec + ":"))
                           for spec in ("compliance", "facts", "context")}
    missed = "; ".join(f"{k} ×{n}" for k, n in r["missed"].most_common()) or "none"
    return [
        f"- **Router:** {lat(r['router_ms'])}; timed out {r['router_timeouts']}/{s['n']} (then every specialist runs)",
        f"- **Model calls per sentence:** {r['calls']:.2f} (router included)",
        f"- **Needed specialist not dispatched (must be zero):** {missed_by_specialist}",
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
        f"- **Runs:** {len(cases)} eval cases × {runs} runs = {s['n']} case runs; every run scored. Timeouts are counted apart from wrong answers.",
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
    if structure.startswith("gemini_"):
        md[6:6] = [f"- **Gemini router:** fast model and thinking above; threshold 0.5; "
                   f"{GEMINI_ROUTER_DEADLINE_MS} ms deadline; fail-open."]
    if structure.startswith("jev_"):
        md[6:6] = [
            f"- **Jev:** `typesafe/jev-1.13`; threshold {raw[0].get('jev_threshold', 0.05)}; 500 ms deadline; fail-open.",
            "- **Timing scope:** router plus specialist calls only; excludes STT, retrieval, queueing and browser paint.",
            "- **Production findings (unchanged):** successive finals wait for previous judges in "
            "`utterances.py:143-145`; fact-note publication waits in `_side` (`utterances.py:473`).",
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
        f"- {len(cases)} eval cases × 20 runs on `{settings.LLM_FAST_MODEL}` (thinking {settings.LLM_FAST_THINKING}).",
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
    ap.add_argument("--cases", choices=["utterance", "holdout"], default="utterance")
    ap.add_argument("--structure", choices=list(AGENTS), default="split2")
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--concurrency", type=int, default=None, help="cases at a time (default: 12 specialist calls in flight)")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--from-json", type=Path, default=None, help="re-score saved outputs without calling the models")
    ap.add_argument("--revalidate", action="store_true",
                    help="with --from-json: apply the current fact quote check to the saved raw fact outputs")
    ap.add_argument("--compare", nargs="+", default=None, metavar="LABEL=JSON",
                    help="compare saved runs, e.g. '2 agents=docs/eval/agents-baseline.json'")
    args = ap.parse_args()
    if args.runs < 1 or (args.concurrency is not None and args.concurrency < 1):
        ap.error("--runs and --concurrency must be positive")
    settings = get_settings()
    cases = load_cases(f"{args.cases}_cases.jsonl")
    if args.compare:
        runs = []
        for item in args.compare:
            label, path = item.split("=", 1)
            runs.append((label, json.loads(Path(path).read_text(encoding="utf-8"))))
        write_compare(runs, cases, args.out or EVAL_DIR / "agents-compare.md", settings)
        return 0
    name = {"split2": "agents-baseline", "split3": "agents-split3", "router3": "agents-router3",
            "jev_selective": "agents-jev-selective", "jev_tiered": "agents-jev-tiered",
            "gemini_selective": "agents-gemini-selective", "gemini_tiered": "agents-gemini-tiered"}[args.structure]
    if args.cases == "holdout":
        name = f"holdout-{args.structure}"
    out = args.out or EVAL_DIR / f"{name}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.from_json:
        raw = json.loads(args.from_json.read_text(encoding="utf-8"))
        if args.revalidate:
            raw = await revalidate(raw, cases)
            out.with_suffix(".json").write_text(json.dumps(raw, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    else:
        concurrency = args.concurrency or (6 if args.structure == "split2" else 4)  # 12 specialist calls in flight
        raw = await run(args.structure, args.runs, concurrency, cases)
        for x in raw:
            x["structure"] = args.structure
        out.with_suffix(".json").write_text(json.dumps(raw, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    write_report(args.structure, raw, cases, out, settings)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
