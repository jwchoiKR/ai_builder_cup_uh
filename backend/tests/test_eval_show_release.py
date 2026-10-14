"""eval_show: a committed switch in a rebuilt-onboarding show names the release it moved to (pack.releases is empty for
"<product_id>:<regulation_id>" keys, so switch_score caught nothing). Made-up products only."""
from __future__ import annotations

import sys
from pathlib import Path

from .helpers import make_ctx, product_show, text_pdf
from .judge_fakes import ScriptedBackend

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

REG = text_pdf("Lunelle Code\n2.1 A cosmetic must not be presented as treating disease.\n")
CREAM = {"brand": "Lunelle", "product_name": "Hydra Calm Cream", "category": "face cream", "currency": "SGD",
         "variants": [{"label": "", "list_price": "42.00", "live_price": "36.00"}],
         "points": [{"text": "Fragrance-free.", "required": True}]}
AMPOULE = {"brand": "Lunelle", "product_name": "Deep Glow", "category": "serum ampoule", "currency": "SGD",
           "variants": [{"label": "", "list_price": "48.00", "live_price": "39.00"}],
           "points": [{"text": "10% niacinamide.", "required": True}]}
MOVE = "Okay, next up, the Deep Glow ampoule."


async def test_a_committed_switch_names_its_release_and_is_caught():
    from eval_show import run_show

    llm = ScriptedBackend()
    llm.judge(MOVE, named=True, transition=True, target="prd_000000000102", confidence="high")
    ctx = make_ctx(backend=llm)
    keys = [product_show(ctx, CREAM, [("lunelle_code.pdf", REG)], "prd_000000000101", "reg_000000000101"),
            product_show(ctx, AMPOULE, [("lunelle_code.pdf", REG)], "prd_000000000102", "reg_000000000102")]
    show = {"show_id": "s1", "release_ids": keys,
            "lines": [{"id": "l1", "text": "It is fragrance-free."}, {"id": "l2", "text": MOVE, "expect": "switch_to:2"}]}
    raw = await run_show(ctx, show, settle_ms=0)
    [commit] = [e for e in raw["switch_events"] if e["event"] == "committed"]
    assert commit["release"] == keys[1]
    assert [r["caught"] for r in raw["switch_score"]["expected"]] == [True]
    assert raw["lines"][0]["on_air_release"] == keys[0]
