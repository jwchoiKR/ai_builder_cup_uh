"""Adversarial harness (proof-plan §3): the real pipeline per case, and the scorer's pass lines."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from eval_adversarial import _field, load_cases, run_case, score  # noqa: E402

from .helpers import make_ctx  # noqa: E402
from .judge_fakes import ScriptedBackend, violation  # noqa: E402


def alert(kind="compliance", rule_id=None, severity=None, field=None, say=None, correct=None):
    return {"kind": kind, "rule_id": rule_id, "severity": severity, "field": field, "span": "s", "say_instead": say,
            "stated_value": None, "correct_value": correct, "status": "active"}


def perfect(case):
    exp = case["expected"]
    if not exp["risky"]:
        return []
    if exp["kind"] == "fact":
        return [alert("fact", field=_field(exp.get("field")), correct=exp.get("correct_value"))]
    if exp["kind"] == "qualifier":
        return [alert(rule_id="BRAND-TEST-QUALIFIER", severity="MEDIUM", say=exp.get("correct_value") or "x")]
    return [alert(rule_id=exp.get("rule_id"), severity="HIGH")]


def test_a_perfect_run_passes_and_each_failure_line_trips():
    cases = load_cases("adversarial_cases.jsonl")
    raw = [{"id": c["case_id"], "run": 0, "alerts": perfect(c)} for c in cases]
    assert score(raw, cases)["passed"]
    safe = next(c for c in cases if not c["expected"]["risky"])
    bad = [dict(r, alerts=[alert(rule_id="ASEAN-3-SKIN-AGEING", severity="HIGH")]) if r["id"] == safe["case_id"] else r
           for r in raw]
    s = score(bad, cases)
    assert not s["passed"] and s["wrong_high"] == 1
    fact = next(c for c in cases if c["expected"]["kind"] == "fact" and c["expected"].get("correct_value"))
    wrong = [dict(r, alerts=[alert("fact", field=_field(fact["expected"]["field"]), correct="999")])
             if r["id"] == fact["case_id"] else r for r in raw]
    s = score(wrong, cases)
    assert s["wrong_text"] == 1 and not next(x for x in s["rows"] if x["id"] == fact["case_id"])["caught"]


def test_d197_only_the_right_rule_catches_and_extra_alerts_count():
    cases = load_cases("adversarial_cases.jsonl")
    raw = [{"id": c["case_id"], "run": 0, "alerts": perfect(c)} for c in cases]
    risky = next(c for c in cases if c["expected"]["risky"] and c["expected"]["kind"] == "compliance"
                 and not c["expected"].get("also_ok_rule_ids"))
    other = "ASEAN-3-SKIN-NUMBING" if risky["expected"]["rule_id"] != "ASEAN-3-SKIN-NUMBING" else "BRAND-SUPERLATIVE"
    wrong_rule = [dict(r, alerts=[alert(rule_id=other, severity="HIGH")]) if r["id"] == risky["case_id"] else r
                  for r in raw]
    row = next(x for x in score(wrong_rule, cases)["rows"] if x["id"] == risky["case_id"])
    assert not row["caught"] and row["extra_wrong"]
    plus = [dict(r, alerts=r["alerts"] + [alert("fact", field="price")]) if r["id"] == risky["case_id"] else r
            for r in raw]
    s = score(plus, cases)
    row = next(x for x in s["rows"] if x["id"] == risky["case_id"])
    assert row["caught"] and row["extra_wrong"] and s["extra_rate"] > 0


async def test_a_split_case_runs_through_the_real_pipeline(monkeypatch):
    real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda _s: real_sleep(0))
    case = {"case_id": "T1", "type": "split", "current_product_id": "ampoule_deep_hydration",
            "parts": ["If you have severe atopic dermatitis,", "this cures it completely."],
            "expected": {"risky": True, "kind": "compliance", "rule_id": "ASEAN-2D-DISEASE"}}
    llm = ScriptedBackend()
    llm.judge("If you have severe atopic dermatitis, this cures it completely.",
              violations=[violation("ASEAN-2D-DISEASE", "this cures it completely")])
    ctx = make_ctx(backend=llm)
    try:
        row = await run_case(ctx, case, 0)
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
    assert [(a["rule_id"], a["severity"]) for a in row["alerts"]] == [("ASEAN-2D-DISEASE", "HIGH")]
    assert score([row], [case])["detection"] == 1.0


def test_d235_an_unverifiable_safe_line_allows_a_soft_fact_note_only():
    case = {"case_id": "U1", "type": "t", "utterance": "x",
            "expected": {"risky": False, "kind": None, "unverifiable": True}}
    note = score([{"id": "U1", "run": 0, "alerts": [alert("fact", field="ingredient", correct="not in this product")]}],
                 [case])
    assert note["false_rate"] == 0 and note["unverifiable_soft"] == 1
    high = score([{"id": "U1", "run": 0, "alerts": [alert(rule_id="ASEAN-2D-DISEASE", severity="HIGH")]}], [case])
    assert high["false_rate"] == 1 and high["wrong_high"] == 1
