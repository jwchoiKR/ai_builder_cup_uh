"""D-409 (user, audit 12): the production fact prompt (v5) no longer points at ACTIVE_PROMO, ACTIVE_OFFERS or SET_OFFERS;
in prompter mode the time-sale price and the set offer reach the model in the snapshot (SOURCE)."""
from __future__ import annotations

from pathlib import Path

from app.logic.prompter import prompter_passages

from .helpers import live_runtime, make_ctx
from .judge_fakes import CREAM, close_env

PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "fact_relation_v5.md"


def test_d409_the_v5_prompt_has_no_promo_offer_or_set_blocks():
    text = PROMPT.read_text(encoding="utf-8")
    assert not [w for w in ("ACTIVE_PROMO", "ACTIVE_OFFERS", "SET_OFFERS") if w in text]
