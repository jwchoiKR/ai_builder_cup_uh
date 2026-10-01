"""Check both configured Gemini models (DEV_SPEC §15 P0, §16 items 1-2).

Sends one structured-output request per model at its configured thinking level through the real
provider path (LLMClient + VertexBackend), validates the JSON with pydantic, and checks the values
against the catalog. Exit code 0 only if both models pass.

    uv run python scripts/check_models.py            # configured models and levels
    uv run python scripts/check_models.py --levels   # also probe which thinking levels each model accepts
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import BaseModel  # noqa: E402

from app.clock import SystemClock  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.ids import Ids  # noqa: E402
from app.logic.catalog import Catalog, DataPack  # noqa: E402
from app.providers.llm import LLMClient, LLMRequest, VertexBackend  # noqa: E402

FIRST_CALL_DEADLINE_MS = 30_000  # first call may be a cold start
WARM_CALL_DEADLINE_MS = 15_000
LEVELS = ("MINIMAL", "LOW", "MEDIUM", "HIGH")


class ModelCheck(BaseModel):
    kind: Literal["question", "reaction"]
    product_id: Literal["cream_hydra_barrier", "ampoule_deep_hydration"] | None
    live_price: str | None
    reason: str


SYSTEM = (
    "You classify one viewer comment from a live-commerce skincare show. "
    "Use only the PRODUCTS data. Copy prices exactly as written. Return JSON only."
)


def build_user(catalog: Catalog) -> tuple[str, dict]:
    products = [
        {"product_id": p.product_id, "name": p.name, "live_price": catalog.money(p.live_price)}
        for p in catalog.products
    ]
    target = catalog.get_product("ampoule_deep_hydration")
    user = (
        f'<data name="PRODUCTS">{json.dumps(products, separators=(",", ":"))}</data>\n'
        f'<data name="COMMENT">how much is the {target.short_name.removeprefix("the ")} today?</data>\n'
        "Return kind, the product_id the comment is about, that product's live_price copied from PRODUCTS, "
        "and a reason of at most 12 words."
    )
    expected = {"kind": "question", "product_id": target.product_id, "live_price": catalog.money(target.live_price)}
    return user, expected


async def check(client: LLMClient, model: str, level: str, user: str, deadline_ms: int, label: str):
    req = LLMRequest(
        agent="check_models", model=model, thinking_level=level, prompt_version="check_models_v1",
        system_instruction=SYSTEM, user_message=user, output_model=ModelCheck, deadline_ms=deadline_ms,
        preview=label,
    )
    return await client.call(req)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", action="store_true", help="probe every thinking level per model")
    args = ap.parse_args()

    settings = get_settings()
    if settings.LLM_PROVIDER != "vertex":
        print(f"LLM_PROVIDER={settings.LLM_PROVIDER}; this script checks the vertex provider only.")
    catalog = Catalog(DataPack.load(settings.data_path))
    backend = VertexBackend(settings.GCP_PROJECT, settings.LLM_LOCATION)
    clock = SystemClock()
    client = LLMClient(backend, settings, clock, Ids(clock, deterministic=False))
    user, expected = build_user(catalog)

    print(f"project={settings.GCP_PROJECT} location={settings.LLM_LOCATION}")
    ok_all = True
    for role, spec in (("fast", client.fast), ("quality", client.quality)):
        for attempt, deadline in (("first", FIRST_CALL_DEADLINE_MS), ("warm", WARM_CALL_DEADLINE_MS)):
            res = await check(client, spec.model, spec.thinking_level, user, deadline, f"{role}/{attempt}")
            got = res.output.model_dump() if res.output else None
            values_ok = bool(got) and all(got[k] == v for k, v in expected.items())
            passed = res.status == "ok" and values_ok
            ok_all &= passed
            print(
                f"[{'PASS' if passed else 'FAIL'}] {role:7} {spec.model:24} thinking={spec.thinking_level:7} "
                f"{attempt:5} status={res.status:7} latency={res.latency_ms:5} ms "
                f"version={res.meta.get('model_version')} usage={res.meta.get('usage')}"
            )
            print(f"         output={json.dumps(got) if got else res.error}")

    if args.levels:
        print("\nthinking levels accepted per model:")
        for spec in (client.fast, client.quality):
            row = []
            for level in LEVELS:
                res = await check(client, spec.model, level, user, WARM_CALL_DEADLINE_MS, f"levels/{level}")
                row.append(f"{level}={'ok' if res.status == 'ok' else res.status}")
                if res.status != "ok":
                    row[-1] += f" ({(res.error or '')[:80]})"
            print(f"  {spec.model:24} " + "  ".join(row))

    await client.aclose()
    print("\nRESULT:", "PASS" if ok_all else "FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
