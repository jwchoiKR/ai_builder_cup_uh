"""BroadcastSummary post-validation (DEV_SPEC §7.8): only numbers from the statistics survive."""
from __future__ import annotations

from app.agents.broadcast_summary import (
    NEUTRAL_HEADLINE,
    BroadcastSummary,
    SummaryInput,
    post_validate,
    rule_based_summary,
    stats_numbers,
)
from app.models.agent_io import SummaryOutput
from app.providers.llm import MockBackend

from .helpers import make_ctx

STATS = {
    "title": "DAON LAB · Skincare session",
    "duration_sec": 312,
    "totals": {"comments": 48, "questions": 21},
    "products": [{"name": "Hydra Barrier Cream", "unanswered_groups": [{"canonical_question": "q", "unique_askers": 3}]}],
    "compliance_alerts": [{"rule_id": "ASEAN-3-SKIN-AGEING", "shown_to_corrected_ms": 4200}],
    "agent_latency": {"utterance_judge": {"p50_ms": 1380.0}},
    "general_unanswered_groups": [],
}


def test_stats_numbers_normalised():
    nums = stats_numbers(STATS)
    assert {"312", "48", "21", "3", "4200", "1380"} <= nums  # 1380.0 -> 1380


def test_sentences_with_unknown_numbers_are_dropped():
    out = SummaryOutput(
        headline="48 comments in 312 seconds.",
        highlights=["Viewers posted 48 comments. The host answered 99 questions.", "All 21 questions were grouped."],
        watch_outs=["One alert took 4200 ms to correct.", "Judge p50 was 1.4 s."],
        follow_ups=["Reply to the 3 unanswered askers.", "Call 7 customers."],
    )
    v = post_validate(out, STATS)
    assert v.headline == "48 comments in 312 seconds."
    assert v.highlights == ["Viewers posted 48 comments.", "All 21 questions were grouped."]
    assert v.watch_outs == ["One alert took 4200 ms to correct."]  # 1.4 is not in the stats
    assert v.follow_ups == ["Reply to the 3 unanswered askers."]


def test_headline_falls_back_to_neutral_text():
    out = SummaryOutput(headline="A record 500 viewers joined.", highlights=[], watch_outs=[], follow_ups=["No number here."])
    v = post_validate(out, STATS)
    assert v.headline == NEUTRAL_HEADLINE
    assert v.follow_ups == ["No number here."]


def test_number_free_text_and_ids_untouched():
    out = SummaryOutput(headline="Calm broadcast.", highlights=["Rule ASEAN-3-SKIN-AGEING was corrected."],
                        watch_outs=[], follow_ups=[])
    # "3" in the rule id is a number that appears in the stats JSON, so the sentence stays.
    assert post_validate(out, STATS).highlights == ["Rule ASEAN-3-SKIN-AGEING was corrected."]


def test_rule_based_fallback_is_valid():
    SummaryOutput.model_validate(rule_based_summary(STATS))


async def test_agent_runs_with_mock_fallback(tmp_path):
    ctx = make_ctx(tmp_path)
    agent = BroadcastSummary(ctx.llm, ctx.prompts["broadcast_summary"])
    res = await agent.run(SummaryInput(stats=STATS), deadline_ms=5000)
    assert res.status == "ok" and res.output is not None
    allowed = stats_numbers(STATS)
    import re

    for text in [res.output.headline, *res.output.highlights, *res.output.watch_outs, *res.output.follow_ups]:
        assert all(m.group(0) in allowed for m in re.finditer(r"\d+(\.\d+)?", text))
    assert isinstance(ctx.llm.backend, MockBackend)
