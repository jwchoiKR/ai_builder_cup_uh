"""D-299: pool 5's failure classes, each next to the line that must keep its old outcome (made-up lines)."""
from __future__ import annotations

from .conftest import ALL_FIXES


def _fixes() -> tuple:
    return tuple(ALL_FIXES.split(","))  # D-353: the opt-in code checks, named (no longer the default)


def test_d299_the_relation_prompt_has_the_bound_hint():
    from pathlib import Path

    text = (Path(__file__).parents[2] / "prompts" / "fact_relation_v5.md").read_text(encoding="utf-8")
    assert "excludes 25 itself" in text
