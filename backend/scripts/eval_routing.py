"""Route-only experiment; running this script makes paid model calls (never on --help).

    uv run python scripts/eval_routing.py --runs 5 --concurrency 3

The legacy 39 cases use the decision's NEEDS lists, not newly inferred labels.
Additional route_cases.jsonl cases require explicit needs. Regex is facts-only shadow routing.
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import datetime as dt
import json
import math
import re
import statistics
import sys
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import REPO_DIR, get_settings  # noqa: E402

SPECIALISTS = ("compliance", "facts", "context")
THRESHOLDS = (0.02, 0.05, 0.1, 0.2, 0.3, 0.5)
DEADLINE_MS = 500
ROUTERS = ("jev", "gemini_purpose", "llm", "regex")


class RouterOutput(BaseModel):
    model_config = ConfigDict(strict=True)
    compliance: bool
    facts: bool
    context: bool
    reason: str


def load_cases(data_path: Path) -> tuple[list[dict], bool]:
    base_path = data_path / "eval" / "utterance_cases.jsonl"
    cases = [json.loads(s) for s in base_path.read_text(encoding="utf-8").splitlines() if s.strip()]
    needs = {
        "compliance": {f"U{i:02d}" for i in range(1, 13)} | {"U23", "U38"},
        "facts": {"U19", "U21", "U23", "U27", "U39"},
        "context": {"U28", "U29", "U30", "U31", "U34", "U35", "U36", "U37"}
                   | {c["case_id"] for c in cases if "covered_points" in c.get("expected", {})},
    }
    for case in cases:
        case["needs"] = {s: case["case_id"] in needs[s] for s in SPECIALISTS}
        case.setdefault("category", "legacy_utterance")
        case["label_source"] = "decision NEEDS lists (legacy screen-change labels)"
    extra_path = data_path / "eval" / "route_cases.jsonl"
    if extra_path.exists():
        extra = [json.loads(s) for s in extra_path.read_text(encoding="utf-8").splitlines() if s.strip()]
        for case in extra:
            labels = case.get("needs", {})
            if set(labels) != set(SPECIALISTS) or any(type(v) is not bool for v in labels.values()):
                raise ValueError(f"Invalid explicit needs: {case.get('case_id')}")
            if not case.get("category"):
                raise ValueError(f"Missing category: {case.get('case_id')}")
            case["label_source"] = "explicit route_cases label"
        cases.extend(extra)
    ids = [c["case_id"] for c in cases]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate routing case IDs")
    return cases, extra_path.exists()


def fact_pattern(pack) -> re.Pattern:
    """Broad lexical shadow gate; deliberately not a semantic fact classifier."""
    words = set("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
                "fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy "
                "eighty ninety hundred thousand million half quarter percent percentage dollars dollar "
                "cents cent sgd usd ml milliliter milliliters millilitre millilitres liter litre grams "
                "gram mg kg oz ounces ounce drops drop hours hour minutes minute seconds second "
                "days day weeks week months month years year".split())
    for product in pack.products.products:
        words.update([product.name, product.short_name, *product.aliases])
    words.update(s.name for s in pack.products.set_offers)
    names = "|".join(re.escape(w) for w in sorted(words, key=lambda s: (-len(s), s)))
    return re.compile(r"\d|[%$??Ｂβ궔]|(?<!\w)(?:" + names + r")(?!\w)", re.IGNORECASE)


def metrics(rows: list[dict], specialist: str, routes: list[dict] | None = None) -> dict | None:
    routes = routes if routes is not None else [r["route"] for r in rows]
    pairs = [(r, route[specialist]) for r, route in zip(rows, routes) if route.get(specialist) is not None]
    if not pairs:
        return None
    needed = sum(r["needs"][specialist] for r, _ in pairs)
    calls = sum(bool(called) for _, called in pairs)
    hits = sum(r["needs"][specialist] and called for r, called in pairs)
    misses = [r["id"] for r, called in pairs if r["needs"][specialist] and not called]
    return {"samples": len(pairs), "needed": needed, "calls": calls,
            "recall": hits / needed if needed else None, "precision": hits / calls if calls else None,
            "calls_saved": len(pairs) - calls, "calls_saved_fraction": 1 - calls / len(pairs),
            "miss_count": len(misses), "miss_case_ids": sorted(set(misses)),
            "misses_by_case": dict(sorted(collections.Counter(misses).items()))}


def summarize(rows: list[dict]) -> dict:
    from experiments.jev_router import apply_route

    result = {}
    for router in ROUTERS:
        selected = [r for r in rows if r["router"] == router]
        elapsed = sorted(r["router_ms"] for r in selected)
        result[router] = {
            "samples": len(selected), "statuses": dict(collections.Counter(r["router_status"] for r in selected)),
            "latency_ms": {"p50": statistics.median(elapsed) if elapsed else None,
                           "p95": elapsed[max(0, math.ceil(len(elapsed) * .95) - 1)] if elapsed else None,
                           "max": max(elapsed) if elapsed else None},
            "specialists": {s: metrics(selected, s) for s in SPECIALISTS},
        }
    jev = [r for r in rows if r["router"] == "jev"]
    result["jev_sweep"] = []
    for threshold in THRESHOLDS:
        for overrides_on in (True, False):
            routes = [apply_route(r["route_probs"], threshold,
                                  r["forced"] if overrides_on else {s: False for s in SPECIALISTS}) for r in jev]
            result["jev_sweep"].append({"threshold": threshold, "overrides_on": overrides_on,
                                        "specialists": {s: metrics(jev, s, routes) for s in SPECIALISTS}})
    return result


def router_template():
    from app.providers.prompts import _examples_text, _parse_file, _template, _until_rule, _with_examples

    pf = _parse_file(Path(__file__).parent / "experiments" / "prompts" / "router.md")
    return _template(pf, _with_examples(_until_rule(pf.require("SYSTEM INSTRUCTION").lines), _examples_text(pf)))


def prompt_values(case: dict, catalog) -> dict:
    from app.agents.utterance_judge import JudgeInput, build_judge_values
    from app.models.session import Alert, SwitchState
    from eval_common import _group

    ctx = case.get("context") or {}
    on_air = case["current_product_id"]
    alerts = [Alert(alert_id=a["alert_id"], kind="compliance", status="active", transcript_id="tr_prev",
                    product_id=on_air, rule_id=a["rule_id"], severity=catalog.pack.rules_by_id[a["rule_id"]].severity,
                    span=a["span"], say_instead=a.get("say_instead"), created_at=0, shown_at=0)
              for a in ctx.get("active_alerts", []) if a.get("kind", "compliance") == "compliance"]
    questions = [(_group({**q, "intent": "suitability"}, 0), q.get("suggested_answer"))
                 for q in ctx.get("open_questions", [])]
    inp = JudgeInput(utterance=case["utterance"], on_air=on_air, active_alerts=alerts,
                     open_questions=questions, previous=ctx.get("recent_transcript", []), scenario="eval",
                     switch=SwitchState.model_validate(ctx.get("switch_state") or {}),
                     promo=catalog.pack.promos_by_id.get(ctx.get("active_promo_id") or ""))
    return build_judge_values(catalog, inp)


async def run(runs: int, concurrency: int, routers: list[str] | tuple[str, ...] = ROUTERS) -> dict:
    from app.logic.catalog import Catalog, DataPack
    from app.logic.reflex import Reflex
    from app.providers.llm import LLMRequest
    from experiments.gemini_router import GeminiRouter, GEMINI_ROUTER_DEADLINE_MS
    from eval_common import make_client
    from experiments.jev_router import JevRouter, apply_route, build_state, get_threshold, routing_overrides

    if not routers or len(set(routers)) != len(routers) or any(r not in ROUTERS for r in routers):
        raise ValueError("routers must be a nonempty unique subset of available routers")
    settings = get_settings().model_copy(update={"LLM_RETRY_ON_5XX": 0})
    cases, has_extra = load_cases(settings.data_path)
    pack = DataPack.load(settings.data_path)
    catalog, reflex = Catalog(pack), Reflex(pack.rules, pack.lexicon)
    pattern = fact_pattern(pack) if "regex" in routers else None
    template = router_template() if "llm" in routers else None
    threshold = get_threshold() if "jev" in routers else 0.05
    # All validation/preparation precedes client creation or any network operation.
    prepared = [(c, prompt_values(c, catalog) if "llm" in routers else None, routing_overrides(c, reflex),
                 build_state(c, catalog.get_product(c["current_product_id"]).name,
                             [p.text for p in catalog.get_product(c["current_product_id"]).prompter_points]))
                for c in cases]
    client = None
    if "llm" in routers:
        client, _ = make_client(False)
        client._settings = client._settings.model_copy(update={"LLM_RETRY_ON_5XX": 0})
    jev = JevRouter() if "jev" in routers else None
    gemini = GeminiRouter() if "gemini_purpose" in routers else None
    sem = asyncio.Semaphore(concurrency)

    async def one(item: tuple, run_no: int, router: str) -> dict:
        case, values, (forced, overrides), state = item
        base = {"id": case["case_id"], "category": case["category"], "run": run_no,
                "router": router, "needs": case["needs"], "forced": forced, "overrides": overrides}
        async with sem:
            if router == "gemini_purpose":
                probs, elapsed, status = await gemini.route(state)
                return base | {"route_probs": probs, "router_status": status, "router_ms": elapsed,
                               "route": apply_route(probs, 0.5, forced)}
            if router == "jev":
                probs, elapsed, status = await jev.route(state)
                probs = probs if status == "ok" else None
                return base | {"route_probs": probs, "router_status": status, "router_ms": elapsed,
                               "route": apply_route(probs, threshold, forced)}
            if router == "regex":
                start = time.perf_counter()
                decision = bool(pattern.search(case["utterance"]))
                elapsed = (time.perf_counter() - start) * 1000
                return base | {"route_probs": None, "raw_route": {"facts": decision},
                               "router_status": "ok", "router_ms": elapsed,
                               "route": {"compliance": None, "facts": decision or forced["facts"], "context": None}}
            result = await client.call(LLMRequest(
                agent="router", model=client.fast.model, thinking_level=client.fast.thinking_level,
                prompt_version=template.version, system_instruction=template.system_instruction,
                user_message=template.render(values), output_model=RouterOutput, deadline_ms=DEADLINE_MS,
                mock_primary_text=case["utterance"], mock_scenario="eval", preview=case["utterance"]))
            raw = {s: getattr(result.output, s) for s in SPECIALISTS} if result.output else None
            route = {s: raw is None or raw[s] or forced[s] for s in SPECIALISTS}
            return base | {"route_probs": None, "raw_route": raw, "router_status": result.status,
                           "router_ms": result.latency_ms, "route": route,
                           "reason": result.output.reason if result.output else None}

    warmup = {}
    try:
        if client is not None:
            try:
                await asyncio.wait_for(client.backend.warm_up(client.fast.model, 10_000), 10)
                warmup["llm"] = "ok"
            except Exception as exc:
                warmup["llm"] = type(exc).__name__
        if jev is not None:
            warmup["jev"] = await jev.warm_up()
        if gemini is not None:
            warmup["gemini_purpose"] = await gemini.warm_up()
        rows = await asyncio.gather(*(one(item, n, router) for n in range(1, runs + 1)
                                     for item in prepared for router in routers))
    finally:
        await asyncio.gather(*(c.aclose() for c in (client, jev, gemini) if c is not None))
    return {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "runs": runs,
            "concurrency": concurrency, "deadline_ms": DEADLINE_MS, "retries": 0,
            "deadlines_ms": {r: GEMINI_ROUTER_DEADLINE_MS if r == "gemini_purpose" else
                             DEADLINE_MS if r != "regex" else None for r in routers},
            "routers": list(routers), "threshold": threshold,
            "llm_model": settings.LLM_FAST_MODEL, "thinking_level": settings.LLM_FAST_THINKING,
            "route_cases_present": has_extra, "case_count": len(cases), "cases": cases,
            "warmup": warmup, "raw": rows, "summary": summarize(rows)}


def markdown(report: dict) -> str:
    summary = report["summary"]
    deadlines = report.get("deadlines_ms", {"jev": report["deadline_ms"], "llm": report["deadline_ms"]})
    deadline_text = ", ".join(f"{name}: {ms} ms" if ms is not None else f"{name}: no deadline"
                              for name, ms in deadlines.items())
    lines = ["# Routing accuracy", "", f"{report['case_count']} cases 횞 {report['runs']} runs; "
             f"deadlines {deadline_text}; no retries; Jev threshold {report['threshold']}.", "",
             "Legacy utterance labels follow the prescribed NEEDS lists. These label screen changes, "
             "not all semantically checkable facts. Additional cases use explicit labels.", "",
             "Errors and timeouts fail open, including every threshold sweep. High recall can therefore "
             "coexist with a failed router; inspect status counts and calls saved. Warm-up is excluded.", "",
             "Regex measures only facts; compliance and context are N/A. Its latency excludes the shared overrides.", "",
             "Production findings: utterances.py serializes successive final utterances; fact-note publication "
             "depends on the _side path. This route-only experiment does not measure or change either behavior.", ""]
    if not report["route_cases_present"]:
        lines += ["route_cases.jsonl was absent; only the legacy cases were evaluated.", ""]
    lines += ["| Router | Status counts | p50 ms | p95 ms | max ms |", "|---|---|---:|---:|---:|"]
    for name in report.get("routers", [r for r in ROUTERS if summary[r]["samples"]]):
        row = summary[name]
        lat = row["latency_ms"]
        lines.append(f"| {name} | {json.dumps(row['statuses'])} | {lat['p50']:.3f} | {lat['p95']:.3f} | {lat['max']:.3f} |")
    lines += ["", "| Router / sweep | Specialist | Recall | Precision | Calls saved | Misses (runs) | Case IDs |",
              "|---|---|---:|---:|---:|---:|---|"]

    def add(name: str, stats: dict) -> None:
        for specialist, m in stats.items():
            if m is None:
                lines.append(f"| {name} | {specialist} | N/A | N/A | N/A | N/A | |")
                continue
            recall = "N/A" if m["recall"] is None else f"{m['recall']:.1%}"
            precision = "N/A" if m["precision"] is None else f"{m['precision']:.1%}"
            lines.append(f"| {name} | {specialist} | {recall} | {precision} | "
                         f"{m['calls_saved']}/{m['samples']} | {m['miss_count']} | {', '.join(m['miss_case_ids'])} |")

    for name in report.get("routers", [r for r in ROUTERS if summary[r]["samples"]]):
        add(name, summary[name]["specialists"])
    for sweep in summary["jev_sweep"] if summary["jev"]["samples"] else []:
        add(f"Jev {sweep['threshold']} overrides {'on' if sweep['overrides_on'] else 'off'}", sweep["specialists"])
    return "\n".join(lines) + "\n"


def positive_int(value: str) -> int:
    n = int(value)
    if n <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return n


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=positive_int, default=5)
    parser.add_argument("--concurrency", type=positive_int, default=3)
    parser.add_argument("--out", type=Path, default=REPO_DIR / "docs" / "eval" / "routing-accuracy.md")
    parser.add_argument("--routers", nargs="+", choices=ROUTERS, default=list(ROUTERS),
                        help="router subset (default: all)")
    args = parser.parse_args()
    report = asyncio.run(run(args.runs, args.concurrency, args.routers))
    out = args.out.with_suffix(".md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out.write_text(markdown(report), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
