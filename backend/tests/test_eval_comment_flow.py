"""Comment-flow harness: a scenario on the mock runtime with an instant pace, and the scorer."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import eval_comment_flow as cf  # noqa: E402

from .helpers import make_ctx  # noqa: E402


class InstantPace:
    def __init__(self):
        self.t = 0.0

    def now(self) -> float:
        return self.t

    async def sleep(self, seconds: float) -> None:
        self.t += seconds
        await asyncio.sleep(0)


async def test_scenario_cf01_runs_and_scores(monkeypatch):
    monkeypatch.setattr(cf, "PACE", InstantPace())
    case = next(c for c in cf.load_cases("comment_flow_cases.jsonl") if c["scenario_id"] == "CF01")
    ctx = make_ctx()
    try:
        raw = await cf.run_scenario(ctx, case, 0)
        await ctx.scheduler.idle()
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
    assert len(raw["comments"]) == sum(e["type"] == "comment" for e in case["events"])
    s = cf.score([raw], [case])
    reactions = [c for c in raw["comments"] if c["gold"].get("kind") == "reaction"]
    assert reactions and all(c["kind"] == "reaction" for c in reactions)  # deterministic prefilter, no LLM
    assert s["rows"][0]["kind_total"] > 0 and 0 <= s["kind"] <= 1


def test_scorer_flags_a_host_answer_posted_before_the_confirmation():
    case = {"scenario_id": "X", "events": [], "expect": {"clusters": {"c": {}}}}
    gold = {"kind": "question", "cluster": "c", "route": "HOST", "answer_must_include": ["50 mL"]}
    raw = {"id": "X", "run": 0, "event_at": {}, "confirms": {"c": 5000},
           "comments": [{"comment_id": "cm1", "gold": gold, "text": "size?", "kind": "question", "received_at": 0,
                         "triage_ms": 900}],
           "groups": [{"group_id": "g1", "member_comment_ids": ["cm1"], "route": "HOST", "status": "answered"}],
           "answers": [{"answer_id": "a1", "group_id": "g1", "text": "It is 50 mL.", "verified": True, "created_at": 2000,
                        "origin": "ai"}],
           "messages": [{"message_id": "m1", "group_id": "g1", "kind": "host_answer", "state": "published",
                         "text": "It is 50 mL.", "reply_to_comment_ids": ["cm1"], "published_at": 3000}]}
    s = cf.score([raw], [case])
    assert s["host_early"] == 1 and s["stale_or_wrong"] == 0 and not s["passed"]
