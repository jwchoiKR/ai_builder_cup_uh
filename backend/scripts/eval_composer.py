"""AnswerComposer thinking level: LOW vs MEDIUM on Vertex AI (D-067 follow-up).

Question set:
  (a) every product question in bursts B1-B4 (comment_script.json, scenes S03, S04, S09, S11);
  (b) every comment eval case whose recorded triage is a composable question.
Triage results come from the RECORDED fixtures (deterministic), products from attribute_product,
composability from is_composable; B4 runs with promo_time_sale_10 active. Identical composer inputs
are deduplicated.

Each question runs 3 times per mode, modes interleaved, concurrency 4, deadline 30 s (latency is
measured, not cut). Passages and verify_answer exactly as in pipelines/comments.py::_run_composer.

    uv run python scripts/eval_composer.py [--runs 3] [--modes LOW MEDIUM] [--out ../docs/eval/composer-thinking.md]
                                           [--calls ../docs/eval/composer-calls.json]

--calls writes every call (question, mode, status, answer, citations, verify errors, passage ids) as JSON.
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import datetime as dt
import json
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.answer_composer import AnswerComposer, ComposeInput, gather_passages  # noqa: E402
from app.agents.comment_triage import GROUP_REF, post_validate  # noqa: E402
from app.agents.inputs import BUILDERS  # noqa: E402
from app.clock import SystemClock  # noqa: E402
from app.config import REPO_DIR, get_settings  # noqa: E402
from app.ids import Ids  # noqa: E402
from app.logic.catalog import Catalog, DataPack  # noqa: E402
from app.logic.grouping import normalise_question  # noqa: E402
from app.logic.prefilter import prefilter  # noqa: E402
from app.logic.product_mapping import attribute_product  # noqa: E402
from app.logic.promos import promo_state  # noqa: E402
from app.logic.reflex import Reflex  # noqa: E402
from app.logic.routing import is_composable  # noqa: E402
from app.logic.verify import verify_answer  # noqa: E402
from app.models.agent_io import CommentTriageOutput  # noqa: E402
from app.providers.llm import AgentResult, LLMClient, MockBackend, VertexBackend  # noqa: E402
from app.providers.prompts import load_prompts  # noqa: E402
from app.providers.retriever import LocalRetriever  # noqa: E402

MODES = ("LOW", "MEDIUM")
BURST_SCENES = ("S03", "S04", "S09", "S11")
PROMO_SCENES = {"S11": "promo_time_sale_10"}
CONTEXT_PRODUCT = "cream_hydra_barrier"
DEADLINE_MS = 30_000
CONCURRENCY = 4


@dataclass
class Question:
    product_id: str | None  # None for product_scope=multi
    intent: str
    slots: dict
    canonical: str
    promo_id: str | None
    sources: list[str] = field(default_factory=list)  # "S03 Lee: How much is the cream?" / "C03: ..."

    @property
    def key(self) -> tuple:
        return (self.product_id, self.intent, tuple(sorted((k, v) for k, v in self.slots.items() if v)),
                normalise_question(self.canonical), self.promo_id or "none")


@dataclass
class Run:
    question: Question
    mode: str
    result: AgentResult | None = None
    verified: bool = False
    errors: list[str] = field(default_factory=list)


def load_triage(mock: MockBackend, text: str, scenario: str) -> dict | None:
    for sc in dict.fromkeys((scenario, "default")):
        p = mock.fixture_path("comment_triage", text, sc)
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
            ref = data.get("group_candidate_id")
            if isinstance(ref, str) and ref.startswith(GROUP_REF):
                data["group_candidate_id"] = None
            return data
    return None


def build_questions(pack: DataPack, catalog: Catalog, data_dir: Path) -> tuple[list[Question], list[str]]:
    mock = MockBackend()
    found: dict[tuple, Question] = {}
    skipped: list[str] = []

    def consider(text: str, scenario: str, context_pid: str, label: str) -> None:
        if prefilter(text, pack.lexicon).kind is not None:
            return  # reaction or hidden by the prefilter: never reaches triage or the composer
        raw = load_triage(mock, text, scenario)
        if raw is None:
            skipped.append(f"{label}: no recorded triage fixture")
            return
        out = post_validate(CommentTriageOutput.model_validate(raw), catalog, text, set())
        if out.kind != "question":
            return
        intent = pack.intents_by_name.get(out.intent or "other", pack.intents_by_name["other"])
        pid, _ = attribute_product(text, out, context_pid, catalog, intent)
        if not is_composable(intent, pid):
            return
        q = Question(product_id=pid if intent.product_scope == "single" else None, intent=intent.intent,
                     slots=out.condition_slots.model_dump(), canonical=out.canonical_question,
                     promo_id=PROMO_SCENES.get(scenario))
        found.setdefault(q.key, q).sources.append(label)

    script = json.loads((data_dir / "demo" / "comment_script.json").read_text(encoding="utf-8"))
    for burst_id, burst in script["bursts"].items():
        scene = burst.get("scene")
        if scene not in BURST_SCENES:
            continue
        for c in burst["comments"]:
            consider(c["text"], scene, CONTEXT_PRODUCT, f"{burst_id.split('_')[0]}/{scene} {c['author_name']}: {c['text']}")
    for line in (data_dir / "eval" / "comment_cases.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        consider(case["comment"], case["case_id"], case["current_product_id"], f"{case['case_id']}: {case['comment']}")
    return list(found.values()), skipped


def pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, max(0, round(q * (len(s) - 1))))]


def fmt_ms(v: float | None) -> str:
    return "n/a" if v is None else f"{v / 1000:.1f} s"


def fmt_pct(n: int, d: int) -> str:
    return "n/a" if d == 0 else f"{n}/{d} ({100 * n / d:.0f}%)"


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    ap.add_argument("--out", type=Path, default=REPO_DIR / "docs" / "eval" / "composer-thinking.md")
    ap.add_argument("--calls", type=Path, default=None)
    args = ap.parse_args()
    modes = tuple(args.modes)

    settings = get_settings()
    pack = DataPack.load(settings.data_path)
    catalog = Catalog(pack)
    prompts = load_prompts(settings.prompts_path, BUILDERS)
    retriever = LocalRetriever(pack.passages)
    reflex = Reflex(pack.rules, pack.lexicon)
    prefetched = {p.product_id: await retriever.prefetch(p.product_id) for p in catalog.products}

    questions, skipped = build_questions(pack, catalog, settings.data_path)
    print(f"{len(questions)} distinct composer inputs; {len(skipped)} comments without a fixture")

    backend = VertexBackend(settings.GCP_PROJECT, settings.LLM_LOCATION)
    clock = SystemClock()
    composers = {}
    for mode in modes:
        client = LLMClient(backend, settings.model_copy(update={"COMPOSER_THINKING": mode}), clock,
                           Ids(clock, deterministic=False))
        composers[mode] = AnswerComposer(client, prompts["answer_composer"], catalog)
    warm = await next(iter(composers.values())).llm.warm_up()
    print("warm-up:", warm)

    passages_of: dict[tuple, list] = {}
    for q in questions:
        passages_of[q.key] = await gather_passages(
            retriever, catalog, prefetched, product_id=q.product_id, intent=q.intent,
            canonical_question=q.canonical, promo=pack.promos_by_id.get(q.promo_id or ""),
            top_k=settings.COMPOSER_TOP_K)

    # Interleave modes: run r, question i -> LOW/MEDIUM order flips with (r + i).
    jobs: list[Run] = []
    for r in range(args.runs):
        for i, q in enumerate(questions):
            order = modes if (r + i) % 2 == 0 else tuple(reversed(modes))
            jobs.extend(Run(q, m) for m in order)

    queue: asyncio.Queue[Run] = asyncio.Queue()
    for j in jobs:
        queue.put_nowait(j)
    done = 0

    async def worker() -> None:
        nonlocal done
        while not queue.empty():
            job = queue.get_nowait()
            q = job.question
            promo = pack.promos_by_id.get(q.promo_id or "")
            intent = pack.intents_by_name[q.intent]
            passages = passages_of[q.key]
            res = await composers[job.mode].run(
                ComposeInput(product_id=q.product_id, intent=q.intent, slots=q.slots, canonical_question=q.canonical,
                             promo=promo, passages=passages, scenario="eval-composer", sensitive=intent.sensitive),
                deadline_ms=DEADLINE_MS,
            )
            job.result = res
            if res.status == "ok" and res.output is not None:
                not_approved = (catalog.not_approved_claims(q.product_id) if q.product_id
                                else [c for p in catalog.products for c in p.not_approved_claims])
                job.verified, job.errors = verify_answer(res.output, passages, q.product_id,
                                                         multi=q.product_id is None, reflex=reflex,
                                                         not_approved_claims=not_approved)
            else:
                job.errors = [f"{res.status}: {res.error or ''}".strip()]
            done += 1
            if done % 20 == 0:
                print(f"  {done}/{len(jobs)} calls")

    await asyncio.gather(*(worker() for _ in range(CONCURRENCY)))
    await backend.aclose()

    if args.calls:
        index = {id(q): n for n, q in enumerate(questions, 1)}
        calls = []
        for j in jobs:
            q, res = j.question, j.result
            out = res.output if res else None
            calls.append({
                "q": index[id(q)], "canonical": q.canonical, "product_id": q.product_id, "intent": q.intent,
                "promo_id": q.promo_id, "sources": q.sources, "mode": j.mode,
                "status": res.status if res else "none", "latency_ms": res.latency_ms if res else None,
                "answer": out.model_dump(mode="json") if out is not None else None,
                "verified": j.verified, "errors": j.errors,
                "passages": [p.passage_id for p in passages_of[q.key]],
            })
        args.calls.parent.mkdir(parents=True, exist_ok=True)
        args.calls.write_text(json.dumps(calls, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"calls: {args.calls}")
    if len(modes) < len(MODES):
        return 0  # the report compares both modes

    # ---- aggregate -------------------------------------------------------------------------------
    agg_rows = []
    summary = {}
    for mode in MODES:
        runs = [j for j in jobs if j.mode == mode]
        n = len(runs)
        ok = [j for j in runs if j.result and j.result.status == "ok" and j.result.output]
        lat = [j.result.latency_ms for j in ok]
        statuses = collections.Counter(j.result.status if j.result else "none" for j in runs)
        thoughts = [((j.result.meta.get("usage") or {}).get("thoughts") or 0) for j in ok]
        within = sum(1 for j in ok if j.result.latency_ms <= settings.COMPOSER_TIMEOUT_MS)
        summary[mode] = {
            "n": n, "verified": sum(j.verified for j in runs), "grounded": sum(bool(j.result.output.grounded) for j in ok),
            "needs_human": sum(bool(j.result.output.needs_human) for j in ok), "statuses": dict(statuses),
            "p50": pct(lat, 0.5), "p95": pct(lat, 0.95), "max": max(lat) if lat else None, "within": within,
            "within15": sum(1 for j in ok if j.result.latency_ms <= 15_000),
            "thoughts": statistics.mean(thoughts) if thoughts else 0.0,
        }
        s = summary[mode]
        agg_rows.append(
            f"| {mode} | {fmt_pct(s['verified'], n)} | {fmt_pct(s['grounded'], n)} | {fmt_pct(s['needs_human'], n)} | "
            f"{', '.join(f'{k} {v}' for k, v in sorted(s['statuses'].items()))} | {fmt_ms(s['p50'])} | {fmt_ms(s['p95'])} | "
            f"{fmt_ms(s['max'])} | {fmt_pct(s['within'], n)} | {fmt_pct(s['within15'], n)} | {s['thoughts']:.0f} |"
        )

    q_rows = []
    for i, q in enumerate(questions, 1):
        cells = []
        errs: collections.Counter[str] = collections.Counter()
        for mode in MODES:
            runs = [j for j in jobs if j.question is q and j.mode == mode]
            lat = [j.result.latency_ms for j in runs if j.result and j.result.status == "ok"]
            cells.append((sum(j.verified for j in runs), len(runs), pct(lat, 0.5)))
            for j in runs:
                for e in j.errors:
                    errs[f"{mode}: {e[:70]}"] += 1
        product = q.product_id or "multi (both)"
        covers = "; ".join(q.sources[:3]) + (f"; +{len(q.sources) - 3} more" if len(q.sources) > 3 else "")
        typical = "; ".join(f"{e} ×{c}" for e, c in errs.most_common(2)) or "—"
        q_rows.append(
            f"| {i} | {q.canonical} | {product} | {q.intent} | {q.promo_id or '—'} | "
            f"{cells[0][0]}/{cells[0][1]} | {cells[1][0]}/{cells[1][1]} | {fmt_ms(cells[0][2])} | {fmt_ms(cells[1][2])} | "
            f"{typical} | {covers} |"
        )

    low, med = summary["LOW"], summary["MEDIUM"]
    deadline_s = settings.COMPOSER_TIMEOUT_MS / 1000

    def rate(s: dict, key: str) -> float:
        return s[key] / s["n"] if s["n"] else 0.0

    conclusion = [
        f"- Deadline ({deadline_s:.0f} s, `COMPOSER_TIMEOUT_MS`): LOW finished {fmt_pct(low['within'], low['n'])} of calls "
        f"in time, MEDIUM {fmt_pct(med['within'], med['n'])}. Latency p50/p95: LOW {fmt_ms(low['p50'])} / {fmt_ms(low['p95'])}, "
        f"MEDIUM {fmt_ms(med['p50'])} / {fmt_ms(med['p95'])}.",
        f"- First-answer target (≤ 15 s, §3.7): LOW {fmt_pct(low['within15'], low['n'])}, "
        f"MEDIUM {fmt_pct(med['within15'], med['n'])} of calls.",
        f"- Quality: verify_answer pass rate LOW {rate(low, 'verified'):.0%} vs MEDIUM {rate(med, 'verified'):.0%}; "
        f"grounded LOW {rate(low, 'grounded'):.0%} vs MEDIUM {rate(med, 'grounded'):.0%}; "
        f"needs_human LOW {rate(low, 'needs_human'):.0%} vs MEDIUM {rate(med, 'needs_human'):.0%}. "
        f"Mean thinking tokens LOW {low['thoughts']:.0f}, MEDIUM {med['thoughts']:.0f}.",
    ]

    lines = [
        f"# Composer thinking level: LOW vs MEDIUM · {dt.date.today().isoformat()}",
        "",
        f"Model `{settings.LLM_QUALITY_MODEL}` on Vertex AI (`{settings.LLM_LOCATION}`), prompt "
        f"`{prompts['answer_composer'].version}`, `COMPOSER_THINKING` = LOW vs MEDIUM (D-067). "
        f"Script: `backend/scripts/eval_composer.py`.",
        "",
        "## Setup",
        f"- **Questions:** {len(questions)} distinct composer inputs (product, intent, slots, canonical question, promo), "
        f"covering {sum(len(q.sources) for q in questions)} comments:",
        "  - every product question of bursts B1–B4 (scenes S03, S04, S09, S11);",
        "  - every comment eval case whose recorded triage is a composable question.",
        "- **How each question was built:**",
        "  - triage output from the recorded fixtures (`tests/fixtures/llm/comment_triage/`, scenario = scene or case id);",
        "  - product from `attribute_product`: context product = cream for B1–B4, the case's `current_product_id` for eval cases;",
        "  - only `is_composable` questions kept; B4 questions run with `promo_time_sale_10` active.",
        f"- **Runs:** {args.runs} per question and mode, modes interleaved, concurrency {CONCURRENCY}.",
        f"- **Deadline:** {DEADLINE_MS // 1000} s, so latency is measured in full. "
        f"The production deadline (`COMPOSER_TIMEOUT_MS` = {settings.COMPOSER_TIMEOUT_MS} ms) is reported separately.",
        "- **Passages and checks:** same as the pipeline: `gather_passages` with BM25 and prefetch, plus the promo passage; "
        "`verify_answer` (§8.9.4).",
        "- **Rates:** over all runs, so a non-ok call counts as not verified and not grounded. "
        "Latency is over ok calls.",
        *([f"- Comments skipped (no recorded triage fixture): {len(skipped)}."] if skipped else []),
        "",
        "## Aggregate",
        "| Mode | verify_answer pass | grounded | needs_human | statuses | p50 | p95 | max | ≤ 12 s | ≤ 15 s | thinking tokens (mean) |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
        *agg_rows,
        "",
        "## Conclusion",
        *conclusion,
        "",
        "## Per question",
        "| # | Canonical question | Product | Intent | Promo | LOW pass | MEDIUM pass | LOW p50 | MEDIUM p50 | Typical verify errors | Covers |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
        *q_rows,
    ]
    if skipped:
        lines += ["", "## Skipped", *[f"- {s}" for s in skipped]]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(lines[:40]))
    print(f"report: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
