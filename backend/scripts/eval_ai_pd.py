"""AI PD model arms: decision latency and agreement, through the ADK runner (production) and as a direct call.

Cases: data/eval/pd_cases.jsonl, each a show state, its candidates in the runtime's rule order, and the gold
choice from the ai_pd prompt's own priorities ("none" where the prompt says so). Paid model calls.

    uv run python scripts/eval_ai_pd.py [--runs 3] [--out ../docs/eval/ai-pd-arms.md]

Per arm and path: p50 / p95 latency, the share over PD_DEADLINE_MS, agreement with the gold, agreement with the
rule pick (the first candidate) where the gold is a card, and invalid or failed answers. Latency is measured
without a deadline; the first call of each arm and path is a warm-up and not counted.
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.ai_pd import AiPd, PdChoice  # noqa: E402
from app.config import REPO_DIR, get_settings  # noqa: E402
from app.pipelines.pd import PD_DEADLINE_MS  # noqa: E402

ARMS = [("gemini-3.8-flash", "MEDIUM"), ("gemini-3.8-flash", "LOW"), ("gemini-3.8-flash", "MINIMAL"),
        ("gemini-3.5-flash-lite", "LOW"), ("gemini-3.5-flash-lite", "MINIMAL")]
NO_DEADLINE_MS = 60_000


class Direct:
    """The same system instruction, user message and output schema, sent with google-genai directly."""

    def __init__(self, project: str, location: str, model: str, thinking: str, template) -> None:
        from google import genai
        from google.genai import types

        self.client = genai.Client(vertexai=True, project=project, location=location)
        self.template, self.model, self.types = template, model, types
        self.config = types.GenerateContentConfig(
            system_instruction=template.system_instruction, response_mime_type="application/json",
            response_schema=PdChoice, temperature=0.0,
            thinking_config=types.ThinkingConfig(thinking_level=thinking))

    async def choose(self, state: dict, candidates: list[dict], deadline_ms: int):
        started = time.perf_counter()
        text = self.template.render({"pd_state_json": state, "pd_candidates_json": candidates})
        try:
            resp = await asyncio.wait_for(self.client.aio.models.generate_content(
                model=self.model, contents=text, config=self.config), deadline_ms / 1000)
            choice = PdChoice.model_validate_json(resp.text or "")
            status = "ok" if choice.choice == "none" or choice.choice in {c["id"] for c in candidates} else "invalid"
        except Exception as e:  # noqa: BLE001
            choice, status = None, f"error:{type(e).__name__}"
        return (choice if status == "ok" else None), round((time.perf_counter() - started) * 1000), status


def pct(values: list[int], q: float) -> int | None:
    v = sorted(values)
    return v[min(len(v) - 1, round(q * (len(v) - 1)))] if v else None


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--out", type=Path, default=REPO_DIR / "docs" / "eval" / "ai-pd-arms.md")
    ap.add_argument("--cases", type=Path, default=None, help="a case file of the same format (default pd_cases.jsonl)")
    ap.add_argument("--arms", nargs="+", default=None, help="model:THINKING pairs, e.g. gemini-3.8-flash:LOW")
    ap.add_argument("--paths", nargs="+", choices=["adk", "direct"], default=["adk", "direct"])
    args = ap.parse_args()
    st = get_settings()
    cases_path = args.cases or st.data_path / "eval" / "pd_cases.jsonl"
    cases = [json.loads(x) for x in cases_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    arms = [tuple(a.split(":")) for a in args.arms] if args.arms else ARMS
    rows = []
    for model, thinking in arms:
        adk = AiPd(project=st.GCP_PROJECT, location=st.LLM_LOCATION, model=model, thinking_level=thinking,
                   prompts_dir=st.prompts_path)
        paths = {"adk": adk, "direct": Direct(st.GCP_PROJECT, st.LLM_LOCATION, model, thinking, adk.template)}
        for path, agent in paths.items():
            if path not in args.paths:
                continue
            await agent.choose(cases[0]["state"], cases[0]["candidates"], NO_DEADLINE_MS)  # warm-up
            for run in range(args.runs):
                for c in cases:
                    choice, ms, status = await agent.choose(c["state"], c["candidates"], NO_DEADLINE_MS)
                    rows.append({"model": model, "thinking": thinking, "path": path, "run": run, "case": c["case_id"],
                                 "ms": ms, "status": status, "choice": choice.choice if choice else None,
                                 "gold": c["gold"], "rule": c["candidates"][0]["id"]})
            print(f"{model} {thinking} {path}: done")
    args.out.with_suffix(".json").write_text(json.dumps(rows, indent=1), encoding="utf-8")

    lines = ["# AI PD arms: latency and agreement", "",
             f"{len(cases)} cases (`{cases_path.name}`) × {args.runs} runs per arm and path; no deadline while "
             f"measuring; deadline in production {PD_DEADLINE_MS} ms.", "",
             "| model | thinking | path | p50 | p95 | over deadline | gold | rule (gold is a card) | invalid/failed |",
             "|---|---|---|---|---|---|---|---|---|"]
    groups = collections.defaultdict(list)
    for r in rows:
        groups[(r["model"], r["thinking"], r["path"])].append(r)
    for (model, thinking, path), rs in groups.items():
        ms = [r["ms"] for r in rs]
        cards = [r for r in rs if r["gold"] != "none"]
        lines.append(
            f"| {model} | {thinking} | {path} | {pct(ms, .5)} ms | {pct(ms, .95)} ms | "
            f"{sum(m > PD_DEADLINE_MS for m in ms)}/{len(ms)} | {sum(r['choice'] == r['gold'] for r in rs)}/{len(rs)} | "
            f"{sum(r['choice'] == r['rule'] for r in cards)}/{len(cards)} | "
            f"{sum(r['status'] != 'ok' for r in rs)} |")
    lines += ["", "Misses against the gold (case: answers over the runs):", ""]
    for (model, thinking, path), rs in groups.items():
        miss = collections.defaultdict(list)
        for r in rs:
            if r["choice"] != r["gold"]:
                miss[r["case"]].append(r["choice"] or r["status"])
        if miss:
            lines.append(f"- {model} {thinking} {path}: " + "; ".join(f"{k} → {', '.join(v)}" for k, v in sorted(miss.items())))
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("report:", args.out)


if __name__ == "__main__":
    asyncio.run(main())
