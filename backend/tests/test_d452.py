"""D-452: the speech hints come only from the product read's stt_terms. A product without them gives no hints: none
are built from the brand, the product name or key facts. Made-up products."""
from __future__ import annotations

from app.api.audio_ws import phrases_for_release

from .helpers import make_ctx, product_show, text_pdf

INFO = {"brand": "Lunelle", "product_name": "Hydra Calm Cream", "category": "face cream", "currency": "SGD",
        "variants": [{"label": "", "list_price": "42.00", "live_price": "36.00"}], "points": [{"text": "5% panthenol.", "required": True}]}
REG = [("lunelle_code.pdf", text_pdf("Lunelle Code\n2.1 No disease claims.\n"))]


def test_d452_only_the_products_stt_terms_are_hints():
    ctx = make_ctx()
    try:
        with_terms = product_show(ctx, {**INFO, "stt_terms": ["Lunelle", "panthenol", "Hydra Calm"]}, REG,
                                  "prd_000000000201", "reg_000000000201")
        assert phrases_for_release(ctx, with_terms) == ["Lunelle", "panthenol", "Hydra Calm"]
        without = product_show(ctx, INFO, REG, "prd_000000000202", "reg_000000000202")
        assert phrases_for_release(ctx, without) == []  # no brand or product name as a fallback
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
