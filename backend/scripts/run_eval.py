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
    backend = VertexBackend(settings.GCP_PROJECT, settings.LLM_LOCATION)
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


async def eval_comments(record: bool) -> tuple[str, bool]:
    settings = get_settings()
    pack = DataPack.load(settings.data_path)
    catalog = Catalog(pack)
    prompts = load_prompts(settings.prompts_path, BUILDERS)
    client, backend = make_client(record)
    triage = CommentTriage(client, prompts["comment_triage"], catalog, settings)
    await client.warm_up()
    now = SystemClock().now_ms()

    rows, latencies = [], []
    totals = {"kind": 0, "intent": 0, "route": 0, "hide": [0, 0], "group": [0, 0], "product": [0, 0], "slots": [0, 0]}
    c22_followed = None

    async def one(case: dict) -> tuple[dict, object]:
        ctx = case.get("context") or {}
        groups = [_group(g, now) for g in ctx.get("open_groups", [])]
        res = await triage.run(TriageInput(text=case["comment"], context_product_id=case["current_product_id"],
                                           open_groups=groups, scenario=case["case_id"]),
                               deadline_ms=settings.TRIAGE_TIMEOUT_MS)
        return case, res

    results = []
    for i in range(0, len(cases := load_cases("comment_cases.jsonl")), 6):  # modest concurrency
        results += await asyncio.gather(*(one(c) for c in cases[i:i + 6]))

    for case, res in results:
        exp = case["expected"]
        out = res.output
        latencies.append(res.latency_ms)
        if out is None:
            rows.append(f"| {case['case_id']} | {case['comment']} | **{res.status}** {res.error or ''} | | | | ✗ |")
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
    await client.aclose()
    return "\n".join(lines) + "\n", passed


def write_report(mode: str, text: str) -> Path:
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    path = EVAL_DIR / f"{dt.date.today().isoformat()}-{mode}.md"
    path.write_text(text, encoding="utf-8")
    return path


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("suite", choices=["comments", "utterances"])
    ap.add_argument("--mode", choices=["split", "single"], default="split")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--runs", type=int, default=1)
    args = ap.parse_args()
    if args.suite == "comments":
        text, passed = await eval_comments(args.record)
        path = write_report("comments", text)
    else:
        from eval_utterances import eval_utterances  # noqa: PLC0415 - phase P2

        text, passed = await eval_utterances(args.mode, args.record, args.runs)
        path = write_report(args.mode, text)
    print(text)
    print(f"report: {path}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
