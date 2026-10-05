"""Onboarding eval entry point (P0, docs/research/onboarding-spec.md section 3): runs the app's onboarding path on a
folder of one product's files and writes the record. Code and prompts are frozen during a run; nobody intervenes.

    uv run python scripts/eval_onboarding.py ../data/onboarding_dev/p1_lumen_serum --out ../docs/eval/onb-p1.json
    uv run python scripts/eval_onboarding.py <files dir> --out <record.json> [--hints "market SG"]

Steps run: 1 store (immutable, content-addressed), 2 read (gemini_whole), 3 normalise. The output is an
`OnboardingResult` (record, files, method, models, seconds, notes).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.context import build_context  # noqa: E402
from app.onboarding.pipeline import onboard_files  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", type=Path, help="folder with one product's files")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--hints", default="", help="optional brand or market hints")
    ap.add_argument("--thinking", default=None, help="override the read step's thinking level")
    args = ap.parse_args()
    files = sorted(p for p in args.files.iterdir() if p.is_file())
    settings = Settings(LLM_PROVIDER="vertex", STT_PROVIDER="mock", STORE="memory", RETRIEVER="local")
    ctx = build_context(settings)
    try:
        result = await onboard_files(ctx.llm, settings.data_path / "onboarding", args.files.name,
                                     [(p.name, p.read_bytes()) for p in files], hints=args.hints,
                                     **({"thinking": args.thinking} if args.thinking else {}))
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
        await ctx.llm.aclose()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8", newline="\n")
    r = result.record
    print(f"{r.brand} · {r.product_name} · {r.category} · {len(r.variants)} variants · {len(r.offers)} offers · "
          f"{len(r.cautions)} cautions · {len(r.not_approved_claims)} not-approved · {len(r.conflicts)} conflicts · "
          f"{result.seconds}s · notes {len(result.notes)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
