"""Draft-verifier gate (proof-plan item 3): which seeded bad drafts pass the deterministic
`verify_answer`, and which still pass the LLM draft verifier after it (D-126)?

    uv run python scripts/eval_draft_verifier.py --cases draft_verifier_cases.jsonl --out ../docs/eval/draft-verifier.md
    uv run python scripts/eval_draft_verifier.py --llm --runs 3 --cases ... --out ../docs/eval/draft-verifier-llm.md

Pass lines (fixed before results): bad drafts passing every layer 0, good drafts blocked <= 3%,
LLM check adds <= 700 ms at p95.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.draft_verifier import DraftCheckInput, DraftVerifier, cited_passages  # noqa: E402
from app.config import REPO_DIR, Settings, get_settings  # noqa: E402
from app.context import build_context  # noqa: E402
from app.logic.catalog import Catalog, DataPack  # noqa: E402
from app.logic.metrics import percentile  # noqa: E402
from app.logic.reflex import Reflex  # noqa: E402
from app.logic.verify import verify_answer  # noqa: E402
from app.models.agent_io import ComposerOutput  # noqa: E402

PASS = {"good_blocked": 0.03, "p95_ms": 700}


def load_cases(name: str) -> list[dict]:
    path = get_settings().data_path / "eval" / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def check_all(cases: list[dict]) -> list[dict]:
    pack = DataPack.load(get_settings().data_path)
    catalog, reflex = Catalog(pack), Reflex(pack.rules)
    rows = []
    for c in cases:
        out = ComposerOutput.model_validate(c["composer_output"])
        pid = c.get("product_id")
        multi = pid is None
        ok, errors = verify_answer(out, pack.passages, pid, multi=multi, reflex=reflex,
                                   not_approved_claims=catalog.not_approved_claims(pid) if pid else [])
        rows.append({"draft_id": c["draft_id"], "label": c["label"], "flaw": c.get("flaw"), "passed": ok,
                     "errors": errors, "answer": out.answer})
    return rows


async def llm_check_all(cases: list[dict], runs: int, concurrency: int) -> list[dict]:
    """The LLM check on every draft (not only those verify_answer lets through), so each layer is measured."""
    settings = Settings(LLM_PROVIDER="vertex", STT_PROVIDER="mock", STORE="memory", RETRIEVER="local")
    ctx = build_context(settings)
    pack = ctx.pack
    verifier = DraftVerifier(ctx.llm, ctx.prompts["draft_verifier"], Catalog(pack))
    sem = asyncio.Semaphore(concurrency)

    async def one(c: dict, run_no: int) -> dict:
        out = ComposerOutput.model_validate(c["composer_output"])
        async with sem:
            res = await verifier.run(DraftCheckInput(
                product_id=c.get("product_id"), question=c["question"], answer=out.answer.strip(), promo=None,
                passages=cited_passages([x.passage_id for x in out.citations], pack.passages), scenario="eval",
            ), deadline_ms=settings.DRAFT_VERIFY_TIMEOUT_MS)
        o = res.output
        return {"draft_id": c["draft_id"], "run": run_no, "status": res.status, "latency_ms": res.latency_ms,
                "passed": res.status == "ok" and o is not None and o.verdict == "pass",
                "problems": (o.problems or [o.reason]) if o is not None and o.verdict == "fail" else []}

    try:
        await ctx.llm.warm_up()
        raw = []
        for run_no in range(runs):
            raw += await asyncio.gather(*(one(c, run_no) for c in cases))
            print(f"run {run_no + 1}/{runs} done")
        return raw
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
        await ctx.llm.aclose()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="draft_verifier_cases.jsonl")
    ap.add_argument("--out", type=Path, default=REPO_DIR / "docs/eval/draft-verifier.md")
    ap.add_argument("--llm", action="store_true", help="also run the LLM draft verifier (Vertex)")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--concurrency", type=int, default=6)
    args = ap.parse_args()
    cases = load_cases(args.cases)
    rows = check_all(cases)
    bad = [r for r in rows if r["label"] == "bad"]
    good = [r for r in rows if r["label"] == "good"]
    bad_pass = [r for r in bad if r["passed"]]
    good_block = [r for r in good if not r["passed"]]
    if not args.llm:
        lines = [
            "# Draft verifier gate: verify_answer alone", "",
            f"{dt.date.today().isoformat()} · `{args.cases}` · {len(bad)} bad and {len(good)} good drafts.", "",
            f"- Bad drafts that pass verify_answer: **{len(bad_pass)} / {len(bad)}**",
            f"- Good drafts that verify_answer blocks: **{len(good_block)} / {len(good)}**", "",
            "## Bad drafts that pass", "",
            *[f"- {r['draft_id']}: {r['flaw']} — \"{r['answer']}\"" for r in bad_pass], "",
            "## Good drafts that are blocked", "",
            *([f"- {r['draft_id']}: {'; '.join(r['errors'])} — \"{r['answer']}\"" for r in good_block] or ["- none"]),
        ]
        args.out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        print(f"bad passing verify_answer {len(bad_pass)}/{len(bad)}; good blocked {len(good_block)}/{len(good)}")
        return 0

    raw = asyncio.run(llm_check_all(cases, args.runs, args.concurrency))
    args.out.with_suffix(".json").write_text(json.dumps(raw, ensure_ascii=False) + "\n", encoding="utf-8",
                                             newline="\n")
    code = {r["draft_id"]: r for r in rows}
    # a draft is posted only when both layers pass it
    final = [{**x, "label": code[x["draft_id"]]["label"], "flaw": code[x["draft_id"]]["flaw"],
              "answer": code[x["draft_id"]]["answer"], "code_passed": code[x["draft_id"]]["passed"],
              "posted": code[x["draft_id"]]["passed"] and x["passed"]} for x in raw]
    bad_posted = [x for x in final if x["label"] == "bad" and x["posted"]]
    good_runs = [x for x in final if x["label"] == "good"]
    good_blocked = [x for x in good_runs if not x["posted"]]
    llm_only_bad = [x for x in final if x["label"] == "bad" and x["passed"]]
    lat = [x["latency_ms"] for x in raw]
    p50, p95 = percentile(lat, 0.5), percentile(lat, 0.95)
    errors = [x for x in raw if x["status"] != "ok"]
    gb_rate = len(good_blocked) / len(good_runs) if good_runs else 0.0
    passed = not bad_posted and gb_rate <= PASS["good_blocked"] and (p95 or 0) <= PASS["p95_ms"]
    lines = [
        "# Draft verifier gate: verify_answer + LLM draft verifier", "",
        f"{dt.date.today().isoformat()} · `{args.cases}` · {len(bad)} bad and {len(good)} good drafts × {args.runs} runs"
        f" · `{get_settings().LLM_FAST_MODEL}` ({get_settings().LLM_FAST_THINKING}).", "",
        f"**{'PASS' if passed else 'FAIL'}** · bad drafts posted {len(bad_posted)} (0) · good drafts blocked "
        f"{len(good_blocked)}/{len(good_runs)} ({gb_rate:.1%}, ≤ 3%) · LLM check p50 {p50} ms, p95 {p95} ms (≤ 700 ms)"
        f" · timeouts or errors {len(errors)}", "",
        f"- Bad drafts the LLM check alone lets through (all runs): {len(llm_only_bad)}/{len(bad) * args.runs}",
        f"- Good drafts verify_answer blocks: {len(good_block)}/{len(good)}", "",
        "## Bad drafts posted (passed both layers)", "",
        *([f"- {x['draft_id']} run {x['run']}: {x['flaw']} — \"{x['answer']}\"" for x in bad_posted] or ["- none"]), "",
        "## Bad drafts the LLM check passes (verify_answer may still block them)", "",
        *([f"- {x['draft_id']} run {x['run']} (code {'pass' if x['code_passed'] else 'block'}): {x['flaw']}"
           for x in llm_only_bad] or ["- none"]), "",
        "## Good drafts blocked", "",
        *([f"- {x['draft_id']} run {x['run']}: {'; '.join(x['problems']) or x['status']} — \"{x['answer']}\""
           for x in good_blocked] or ["- none"]),
    ]
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"{'PASS' if passed else 'FAIL'} bad posted {len(bad_posted)}; good blocked {len(good_blocked)}/"
          f"{len(good_runs)}; p50 {p50} ms p95 {p95} ms; errors {len(errors)}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
