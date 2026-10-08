"""D-347: FACT_PROMPT=v8 is v5 plus one rule: lists of rejected claim wordings are never a fact source; real usage
cautions stay facts. The default stays v5. (The model's behaviour is measured with scripts/probe_banned_lists.py
against the real model; a scripted backend cannot show it.)"""
from __future__ import annotations

from pathlib import Path


def test_d347_the_v8_rule_and_examples():
    text = (Path(__file__).parents[2] / "prompts" / "fact_relation_v8.md").read_text(encoding="utf-8")
    assert "is never a fact source" in text and '"Do not say …"' in text and "TIDAK DILULUSKAN" in text
    assert '"Not approved for children under 4 months"' in text  # a real caution stays a fact
    assert "Example S" in text and '"relation":"contradicts"' in text.split("Example S", 1)[1]


async def test_d347_v8_is_wired_with_the_v5_schema():
    from app.models.agent_io import FactRelationOutputV5

    from .helpers import live_runtime, make_ctx
    from .judge_fakes import close_env

    rt = await live_runtime(make_ctx(FACT_RELATION=True, FACT_PROMPT="v8", JUDGE_ARM="single"))
    try:
        assert rt.utterances.facts.relation_model is FactRelationOutputV5
        assert "is never a fact source" in rt.utterances.facts.system_instruction
    finally:
        await close_env(rt)
