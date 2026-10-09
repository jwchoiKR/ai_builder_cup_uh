"""D-142 (JAPAC B): each session holds its own (market, language) pack; the runtime takes it from there."""
from __future__ import annotations

import json
import shutil

import pytest

from app.pipelines.runtime import ActionError, create_session

from .helpers import make_ctx


async def test_a_language_the_market_does_not_offer_is_refused():
    ctx = make_ctx()
    with pytest.raises(ActionError, match="unknown_market_language|does not offer|en|ko"):
        await create_session(ctx, "daon_skincare_demo", lang="ko")


def tmp_copy(data, products, tmp_path):
    """The data folder with another products.json."""
    import shutil

    out = tmp_path / "data"
    shutil.copytree(data, out)
    (out / "products" / "products.json").write_text(json.dumps(products), encoding="utf-8")
    return out
