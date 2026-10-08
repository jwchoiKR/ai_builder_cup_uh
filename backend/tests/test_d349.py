"""D-349 SWITCH_MODE=immediate: the context judge's transition verdict alone switches the prompter at once (no name
match, no confirming line, no pending countdown); for SWITCH_DUAL_SCOPE_SEC after a switch or an undo the fact
checker and the compliance judge get both products, labelled, and the compliance judge says which product each claim
is about. The default (two_step) is unchanged. Made-up lines on the demo show's two products."""
from __future__ import annotations

import pytest

from .judge_fakes import AMPOULE, CREAM, ScriptedBackend, close_env, events, speak, violation

MOVE_ON = "Okay, let me show you the next one now."  # names no product


class _Recording(ScriptedBackend):
    def __init__(self) -> None:
        super().__init__()
        self.requests = []

    async def generate(self, req, timeout_ms):
        self.requests.append(req)
        return await super().generate(req, timeout_ms)

    def last(self, agent: str, text: str):
        return [r for r in self.requests if r.agent == agent and r.mock_primary_text == text][-1]


async def _env(**settings):
    from .helpers import live_runtime, make_ctx

    llm = _Recording()
    rt = await live_runtime(make_ctx(backend=llm, **settings))
    return rt, llm


async def _on_air(rt) -> str:
    return (await rt.current_segment()).product_id


async def test_d349_a_transition_verdict_switches_at_once():
    rt, llm = await _env(SWITCH_MODE="immediate")
    try:
        llm.judge(MOVE_ON, utterance_type="transition", transition=True, target=AMPOULE, confidence="medium",
                  reason="the host moves on to the next product")
        await speak(rt, MOVE_ON)
        assert await _on_air(rt) == AMPOULE  # no confirming line, no 5 s countdown, no name heard
        assert not await events(rt, "segment.switch_counting") and not await events(rt, "segment.switch_pending")
        [d] = await events(rt, "segment.switch_decided")
        assert d.payload["switch"] is True and d.payload["confidence"] == "medium"
        assert d.payload["reason"] == "the host moves on to the next product"
        [seg] = [e for e in await events(rt, "segment.started") if e.payload["product_id"] == AMPOULE]
        assert seg.payload["start_reason"] == "auto_speech"
        s = await rt.load_session()
        assert s.switch.last_commit["immediate"] is True and s.switch.previous_product_id == CREAM
    finally:
        await close_env(rt)


@pytest.mark.parametrize("kw", [
    {"quote": True},  # a viewer's words read out
    {"target": CREAM},  # back to the on-air product
])  # D-351: an answer line and a low confidence no longer block a switch (tests/test_d351.py)
async def test_d349_no_switch_on_a_quote_or_another_target(kw):
    rt, llm = await _env(SWITCH_MODE="immediate")
    try:
        llm.judge(MOVE_ON, **({"utterance_type": "transition", "transition": True, "target": AMPOULE,
                               "confidence": "high"} | kw))
        await speak(rt, MOVE_ON)
        assert await _on_air(rt) == CREAM
        assert [e.payload["switch"] for e in await events(rt, "segment.switch_decided")] == [False]
    finally:
        await close_env(rt)


async def test_d349_the_default_two_step_mode_is_unchanged():
    rt, llm = await _env(SWITCH_ARM_NAME=False)
    try:
        llm.judge(MOVE_ON, utterance_type="transition", transition=True, target=AMPOULE, confidence="high")
        await speak(rt, MOVE_ON)
        assert await _on_air(rt) == CREAM and len(await events(rt, "segment.switch_counting")) == 1
        assert not await events(rt, "segment.switch_decided")
        s = await rt.load_session()
        assert s.switch.previous_product_id is None
    finally:
        await close_env(rt)


async def test_d349_both_products_reach_the_judges_for_the_window_only():
    from .judge_fakes import advance

    rt, llm = await _env(SWITCH_MODE="immediate", SWITCH_DUAL_SCOPE_SEC=10)
    try:
        llm.judge(MOVE_ON, utterance_type="transition", transition=True, target=AMPOULE, confidence="high")
        await speak(rt, MOVE_ON)
        inside, outside = "This one feels so light on the skin.", "You can layer it under any cream."
        await speak(rt, inside)
        comp = llm.last("compliance_judge", inside)
        assert '<data name="PREVIOUS_PRODUCT">' in comp.user_message and CREAM in comp.user_message
        assert "product_id" in comp.output_model.model_json_schema()["$defs"][
            next(k for k in comp.output_model.model_json_schema()["$defs"] if k.startswith("Violation"))]["properties"]
        facts = llm.last("fact_checker", inside)
        assert '"previous_product"' in facts.user_message and CREAM in facts.user_message
        await advance(rt, 10_001)
        await speak(rt, outside)
        comp = llm.last("compliance_judge", outside)
        assert "PREVIOUS_PRODUCT" not in comp.user_message and '"previous_product"' not in llm.last(
            "fact_checker", outside).user_message
    finally:
        await close_env(rt)


@pytest.mark.parametrize("picked, product", [(CREAM, CREAM), (AMPOULE, AMPOULE), ("someone_else", AMPOULE)])
async def test_d349_the_alert_and_its_wording_follow_the_product_the_model_picked(picked, product):
    from app.models.agent_io import ComplianceOutput

    rt, llm = await _env(SWITCH_MODE="immediate")
    try:
        llm.judge(MOVE_ON, utterance_type="transition", transition=True, target=AMPOULE, confidence="high")
        await speak(rt, MOVE_ON)
        line = "And honestly, it heals eczema overnight."
        v = violation("ASEAN-2D-DISEASE", "heals eczema overnight") | {"product_id": picked}
        out = ComplianceOutput.model_validate({"compliance": {"violations": []}, "correction": {"corrects_alert_ids": []},
                                               "reason": "scripted"}).model_dump(mode="json")
        out["compliance"]["violations"] = [v]
        llm.outputs[("compliance_judge", line)] = out
        await speak(rt, line)
        [a] = [a for a in await rt.alerts() if a.kind == "compliance" and a.status == "active"]
        assert a.product_id == product
        own = [c.lower() for c in rt.catalog.approved_claims(product)]
        assert any(c[:20] in a.say_instead.lower() for c in own) or any(
            x.say.lower() in a.say_instead.lower() for x in rt.catalog.get_product(product).avoid_saying)
    finally:
        await close_env(rt)


async def test_d349_an_undo_opens_the_window_for_the_undone_product():
    from app.pipelines.utterances import undo_switch

    rt, llm = await _env(SWITCH_MODE="immediate")
    try:
        llm.judge(MOVE_ON, utterance_type="transition", transition=True, target=AMPOULE, confidence="high")
        await speak(rt, MOVE_ON)
        await undo_switch(rt)
        s = await rt.load_session()
        assert await _on_air(rt) == CREAM and s.switch.previous_product_id == AMPOULE
        line = "So that is the cream again."
        await speak(rt, line)
        assert AMPOULE in llm.last("compliance_judge", line).user_message.split('<data name="PREVIOUS_PRODUCT">')[1]
    finally:
        await close_env(rt)


async def test_d349_eval_show_replays_a_show_and_scores_its_switches(tmp_path):
    """scripts/eval_show.py on a made-up two-release show: one caught switch, its events tied to the lines."""
    import sys
    from pathlib import Path

    from app.onboarding.release import product_key, save_release

    from .helpers import make_ctx
    from .test_clean_base import clean_data, kettle
    from .test_multi_release import cream

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import eval_show

    onb = tmp_path / "onb"
    ids = [save_release(onb, cream(), "job_c"), save_release(onb, kettle(), "job_k")]
    llm = _Recording()
    ctx = make_ctx(backend=llm, DATA_DIR=str(clean_data(tmp_path)), ONBOARDING_DIR=str(onb), SWITCH_MODE="immediate")
    risky = "Honestly, it heals eczema overnight."
    llm.judge(risky, violations=[violation("ASEAN-2D-DISEASE", "heals eczema overnight")])
    move = "Alright, that's it for the cream, let's look at something else."
    llm.judge(move, utterance_type="transition", transition=True, target=product_key(kettle()), confidence="high")
    show = {"show_id": "S1", "release_ids": ids, "lines": [
        {"id": "L1", "text": "This cream feels so soft at night.", "gap_ms": 0, "expect": "stay"},
        {"id": "L1b", "text": risky, "gap_ms": 0, "labels": {"risky": True}},
        {"id": "L2", "text": move, "gap_ms": 0, "expect": "switch_to:2"},
        {"id": "L3", "text": "It boils water really fast.", "gap_ms": 0, "expect": "stay"}]}
    try:
        raw = await eval_show.run_show(ctx, show, settle_ms=0)
    finally:
        await close_env_ctx(ctx)
    decided = [e for e in raw["switch_events"] if e["event"] == "decided"]
    assert [(e["line"], e["switch"]) for e in decided] == [("L2", True)]
    assert [e["release"] for e in raw["switch_events"] if e["event"] == "committed"] == [ids[1]]
    s = raw["switch_score"]
    assert [r["caught"] for r in s["expected"]] == [True] and s["false_switches"] == []
    assert [x["context"]["switch"]["is_transition"] for x in raw["lines"]] == [False, False, True, False]
    [a] = [a for a in raw["alerts"] if a["ms_to_shown"] is not None]
    assert (a["line"], a["kind"], a["checked_against"]) == ("L1b", "compliance", ids[0])
    assert raw["lines"][1]["labels"] == {"risky": True}
    # the effective settings are written with each show
    assert raw["settings"]["STORE"] == "memory" and raw["settings"]["SWITCH_MODE"] == "immediate"
    assert {"FIRESTORE_DATABASE", "COMPLIANCE_RESAY", "CORRECTION_CHECK", "REFLEX_SCAN", "JUDGE_PRODUCTS",
            "FACT_PROMPT"} <= set(raw["settings"])
    assert all(c["usage"] is None or isinstance(c["usage"], dict) for c in raw["calls"])
    assert {"lines", "switch_events", "alerts", "prompter", "chips", "judge", "calls", "timeline"} <= set(raw)


async def close_env_ctx(ctx) -> None:
    ctx.runtimes.shutdown()
    ctx.scheduler.shutdown()
