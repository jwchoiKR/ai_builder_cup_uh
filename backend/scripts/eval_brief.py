"""Release brief eval entry point (D-265): runs the app's BriefAgent on an approved release, as approval does, and
writes the glossary, the STT phrase hints a show from it would get, and the prompter points. Nothing is stored.

    uv run python scripts/eval_brief.py --release rel_x_v1 --out ../docs/eval/brief-x.json [--thinking HIGH]

ONBOARDING_DIR (or ONBOARDING_GCS_BUCKET) selects where the release is read from.
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
from app.logic.catalog import Catalog  # noqa: E402
from app.onboarding.brief import brief_release  # noqa: E402
from app.onboarding.release import load_release, release_pack  # noqa: E402
from app.providers.stt import phrases_from_glossary  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--release", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--thinking", default=None, help="override BRIEF_THINKING (MEDIUM, HIGH)")
    ap.add_argument("--model", default=None, help="override BRIEF_MODEL")
    args = ap.parse_args()
    settings = Settings(LLM_PROVIDER="vertex", STT_PROVIDER="mock", STORE="memory", RETRIEVER="local")
    ctx = build_context(settings)
    try:
        root = settings.onboarding_path
        record = load_release(root, args.release)
        res, seconds = await brief_release(ctx.llm, ctx.prompts["brief_agent"], ctx.reflex, root, args.release, record,
                                           ctx.pack.lang, model=args.model, thinking=args.thinking,
                                           deadline_ms=settings.BRIEF_TIMEOUT_MS, offers=settings.BRIEF_OFFERS)
        out = {"release_id": args.release, "status": res.status, "error": res.error, "seconds": seconds,
               "model": args.model or ctx.llm.brief.model, "thinking": args.thinking or ctx.llm.brief.thinking_level,
               "offers": settings.BRIEF_OFFERS}
        if res.output is not None:
            from app.api.audio_ws import default_glossary

            # the same derivation as a show from this release: brief terms first, then brand, product, ingredients
            cat = Catalog(release_pack(ctx.pack, record, args.release, root, brief=res.output), args.release)
            terms = [t.model_dump() for t in res.output.glossary] + default_glossary(ctx, cat)["terms"]
            out |= {"glossary": [t.model_dump() for t in res.output.glossary],
                    "phrases": phrases_from_glossary({"terms": terms}),
                    "prompter_points": [p.model_dump() for p in cat.products[0].prompter_points]}
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
        await ctx.llm.aclose()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"{args.release} · {out['status']} · {out['thinking']} · {out['seconds']}s · "
          f"{len(out.get('glossary', []))} terms · {len(out.get('prompter_points', []))} points")
    return 0 if res.status == "ok" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
