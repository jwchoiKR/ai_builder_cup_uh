"""Law pack eval entry point (D-229): regulator documents in, rule records with evidence out, by the app path.

    uv run python scripts/eval_lawpack.py ../data/onboarding_dev/law_supplements --market SG --category food_supplement \
        --out ../docs/eval/lawpack-dev.json
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
from app.onboarding.files import model_part  # noqa: E402
from app.onboarding.lawpack import read_lawpack  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", type=Path)
    ap.add_argument("--market", required=True)
    ap.add_argument("--category", required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    settings = Settings(LLM_PROVIDER="vertex", STT_PROVIDER="mock", STORE="memory", RETRIEVER="local")
    ctx = build_context(settings)
    try:
        parts = [model_part(p.name, p.read_bytes()) for p in sorted(args.files.iterdir()) if p.is_file()]
        rec, notes, secs = await read_lawpack(ctx.llm, parts, market=args.market.upper(), category=args.category)
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
        await ctx.llm.aclose()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"record": rec.model_dump(mode="json"), "notes": notes, "seconds": secs},
                                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"{rec.name} · covers {rec.covers} · {len(rec.rules)} rules · {secs}s · notes {len(notes)}")
    for r in rec.rules:
        print(f"  {r.rule_id} {r.severity} {r.title} | {r.evidence[0].locator}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
