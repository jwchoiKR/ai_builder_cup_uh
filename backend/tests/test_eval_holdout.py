"""Offline evaluation contracts; no credentials or model calls."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from eval_expectations import expectation_checks
from eval_holdout_sequences import alert_latencies, feed_turns, runtime_effects


def checks(expected, judge=None, facts=None, **kwargs):
    return expectation_checks(expected, judge or {}, facts or {}, lambda a, b: a == b, **kwargs)


def test_ids_do_not_determine_compliance_and_fact_scores():
    judge = {"compliance": {"violations": [{"rule_id": "rule", "severity": "HIGH"}]}}
    facts = {"claims": [{"verdict": "contradicted", "field": "price", "correct_value": "36"}]}
    result = checks({"compliance": True, "rule_id": "rule", "severity": "HIGH",
                     "fact": "contradicted", "field": "price", "correct_value": "36"}, judge, facts)
    assert all(c[2] for c in result)
    assert not checks({"compliance": True, "rule_id": "different"}, judge)[0][2]


def test_negated_and_quoted_violations_do_not_create_alerts():
    for flag in ("is_negated", "is_quoted"):
        judge = {"compliance": {"violations": [{"rule_id": "rule", flag: True}]}}
        assert checks({"compliance": False}, judge)[0][2]


def test_facts_supported_and_none_require_no_contradicted_notes():
    for verdict in ("supported", "none"):
        assert checks({"fact": verdict})[-1][2]
        assert not checks({"fact": verdict}, facts={"claims": [{"verdict": "contradicted"}]})[-1][2]


def test_answer_readout_group_and_symbolic_correction_are_checked():
    judge = {"answer": {"is_answer": False, "matched_group_id": "real_group"},
             "correction": {"corrects_alert_ids": ["real_alert"]}}
    result = checks({"answer": False, "matched_group": "group_alias", "corrects_alert_ids": ["alert_alias"]},
                    judge, ids={"group_alias": "real_group", "alert_alias": "real_alert"})
    assert all(c[2] for c in result)
    judge["answer"]["matched_group_id"] = None
    assert any(not c[2] for c in checks({"answer": False, "matched_group": "real_group"}, judge))


def test_continuation_and_coverage_have_independent_checks():
    assert all(c[2] for c in checks({"switch": "continuation"}))
    assert not all(c[2] for c in checks({"switch": "continuation"}, continuation=False))
    result = checks({"switch": True, "target": "ampoule", "covered_points": ["p1"]},
                    {"prompter": {"covered_point_ids": ["p1"], "switch": {
                        "is_transition": True, "is_quote": False, "target_product_id": "ampoule"}}})
    assert all(c[2] for c in result)


@pytest.mark.parametrize("expected", [{"typo": True}, {"fact": "unknown"}, {"switch": "unknown"}])
def test_unknown_expectations_fail_loudly(expected):
    with pytest.raises(ValueError):
        checks(expected)


def test_agent_timeouts_never_earn_true_negative_scores():
    from eval_agents import score

    row = {"id": "new-holdout-id", "run": 0, "judge": None,
           "comp_status": "timeout", "ctx_status": "timeout", "facts_status": "timeout",
           "comp_ms": 10, "ctx_ms": 10, "facts_ms": 10, "facts_raw": None, "facts_validated": None}
    result = score([row], [{"case_id": row["id"], "expected": {"compliance": False, "fact": "none"}}])
    assert all(t["ok"] == 0 and t["timeout"] == 1 for t in result["tally"].values())
    assert result["all_ms"] == []


def test_latency_uses_first_active_event_even_after_correction():
    payload = {"alert_id": "a", "transcript_id": "t", "kind": "compliance"}
    events = [{"type": "alert.created", "at": 101, "payload": {**payload, "status": "provisional"}},
              {"type": "alert.updated", "at": 130, "payload": {**payload, "status": "active", "shown_at": 125}},
              {"type": "alert.updated", "at": 140, "payload": {**payload, "status": "active", "shown_at": 125}},
              {"type": "alert.updated", "at": 160, "payload": {**payload, "status": "corrected"}}]
    assert alert_latencies(events, "t", 100)[0]["speech_end_to_alert_ms"] == 25
    assert len(alert_latencies(events, "t", 100)) == 1
    assert alert_latencies(events, "another", 100) == []


def test_runtime_effects_override_rejected_model_results_and_credit_late_correction():
    judge = {"compliance": {"violations": [{"rule_id": "rejected"}]},
             "correction": {"corrects_alert_ids": ["rejected"]},
             "answer": {"is_answer": True, "matched_group_id": "g"},
             "prompter": {"covered_point_ids": ["rejected"], "switch": {
                 "is_transition": True, "target_product_id": "ampoule"}}}
    event = {"type": "alert.updated", "at": 150, "payload": {
        "alert_id": "late", "status": "corrected", "corrected_by_transcript_id": "t"}}
    state = {"segments": [{"product_id": "cream", "covered_point_ids": ["committed"]}],
             "switch_before": {"status": "idle"}, "switch": {"status": "idle"}}
    effective, facts = runtime_effects([event], "t", [], judge, state, None)
    assert effective["compliance"]["violations"] == []
    assert effective["correction"]["corrects_alert_ids"] == ["late"]
    assert effective["answer"]["is_answer"] is False
    assert effective["prompter"]["covered_point_ids"] == []
    assert effective["prompter"]["switch"]["is_transition"] is False
    assert facts == {"claims": []}


def test_runtime_effects_include_active_fact_and_committed_answer_and_switch():
    payload = {"alert_id": "f", "transcript_id": "t", "kind": "fact", "status": "active", "field": "price", "correct_value": "36"}
    state = {"segments": [], "pre_covered": {"ampoule": ["p"]},
             "switch_before": {"cue_count": 0}, "switch": {"target_product_id": "ampoule", "cue_count": 1}}
    judge = {"prompter": {"covered_point_ids": ["p"], "switch": {"is_transition": True, "target_product_id": "ampoule"}}}
    effective, facts = runtime_effects([{"type": "alert.created", "payload": payload}], "t",
                                     [{"alert_id": "f"}], judge, state, ("g", "verbal_not_posted"))
    assert facts["claims"][0]["field"] == "price"
    assert effective["answer"]["is_answer"] is True
    assert effective["answer"]["matched_group_id"] == "g"
    assert effective["prompter"]["switch"]["is_transition"] is True
    assert effective["prompter"]["covered_point_ids"] == ["p"]


@pytest.mark.asyncio
async def test_gaps_follow_finals_without_draining_inference(monkeypatch):
    calls = []
    running = []

    class Pipeline:
        async def submit(self, text, **kwargs):
            running.append(text)
            calls.append(("submit", text, len(running)))
            return text

        async def drain(self):
            calls.append(("drain", tuple(running)))

    async def sleep(seconds):
        calls.append(("gap", seconds))

    monkeypatch.setattr(asyncio, "sleep", sleep)
    rt = SimpleNamespace(utterances=Pipeline(), now=lambda: 100)
    result = await feed_turns(rt, [{"utterance": "first", "gap_ms": 450},
                                  {"utterance": "second", "gap_ms": 550}])
    assert result == ["first", "second"]
    assert calls == [("submit", "first", 1), ("gap", .45), ("submit", "second", 2),
                     ("gap", .55), ("drain", ("first", "second"))]


@pytest.mark.asyncio
async def test_negative_gap_is_rejected_before_submission():
    with pytest.raises(ValueError):
        await feed_turns(None, [{"utterance": "test", "gap_ms": -1}])


@pytest.mark.asyncio
async def test_sequence_with_open_questions_runs_on_the_mock_runtime(monkeypatch):
    """S05 seeds open questions; the seeded groups must use a known id prefix (grp_)."""
    import json

    from eval_holdout_sequences import run_sequence

    from .helpers import make_ctx

    real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda _s: real_sleep(0))
    lines = (SCRIPTS.parents[1] / "data" / "eval" / "holdout_sequences.jsonl").read_text(encoding="utf-8").splitlines()
    s05 = next(json.loads(ln) for ln in lines if ln.strip() and json.loads(ln)["seq_id"] == "S05")
    ctx = make_ctx()
    try:
        result = await run_sequence(ctx, s05, 1)
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
    assert result["symbols"]["g_makeup"].startswith("grp_")
    assert len(result["turns"]) == len(s05["turns"])


def test_qualifier_ok_allows_only_a_lone_qualifier_medium():
    """H090: a BRAND-TEST-QUALIFIER MEDIUM is allowed there, not required; any other alert is still a leak."""
    q = {"rule_id": "BRAND-TEST-QUALIFIER", "severity": "MEDIUM"}
    other = {"rule_id": "ASEAN-3-SKIN-AGEING", "severity": "HIGH"}
    judge = lambda *vs: {"compliance": {"violations": list(vs)}}  # noqa: E731
    exp = {"compliance": False, "qualifier_ok": True}
    assert checks(exp)[0][2] and checks(exp, judge(q))[0][2]
    assert not checks(exp, judge(other))[0][2] and not checks(exp, judge(q, other))[0][2]
    assert not checks(exp, judge({**q, "severity": "HIGH"}))[0][2]
    assert not checks({"compliance": False}, judge(q))[0][2]  # without the label it is a leak
