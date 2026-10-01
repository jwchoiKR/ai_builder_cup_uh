"""Prompter coverage and product switch (DEV_SPEC §8.7, §14.1 prompter / segments)."""
from __future__ import annotations

import pytest

from app.logic.prompter import apply_coverage, missing_required, prompter_view
from app.logic.segments import classify_switch, step_switch
from app.models.agent_io import UtteranceJudgeOutput
from app.models.session import Segment, Session, SwitchState
from app.pipelines import utterances as utt
from app.pipelines.runtime import ActionError

from .judge_fakes import AMPOULE, CREAM, advance, close_env, events, judge_output, make_env, speak, violation

INTRO = "Okay, now let me show you our Deep Hydration Ampoule. It has four percent niacinamide."
INTRO2 = "So next up is the Deep Hydration Ampoule."
CONT = "It's a watery gel, just two to three drops after toner."
BACK = "Going back to the cream for a second, it's fragrance free."


@pytest.fixture
async def env():
    rt, llm = await make_env()
    yield rt, llm
    await close_env(rt)


def script_switch(llm) -> None:
    llm.judge(INTRO, utterance_type="transition", transition=True, target=AMPOULE, confidence="high", covered=["am-p1"])
    llm.judge(INTRO2, utterance_type="transition", transition=True, target=AMPOULE, confidence="high")
    llm.judge(CONT, covered=["am-p2"])
    llm.judge(BACK, transition=True, target=CREAM, confidence="high", covered=["cr-p5"])


async def segs(rt) -> list[Segment]:
    return await rt.segments()


async def to_pending(rt, llm) -> None:
    script_switch(llm)
    await speak(rt, INTRO)
    await speak(rt, CONT)
    assert (await rt.load_session()).switch.status == "pending"


# ---- coverage (§8.7.1) ---------------------------------------------------------------------------


async def test_coverage_is_monotonic(env):
    rt, llm = env
    llm.judge("It's a lightweight gel-cream.", covered=["cr-p1"])
    llm.judge("One percent ceramide NP, five percent panthenol and three percent squalane.", covered=["cr-p2"])
    llm.judge("Hello again everyone.")
    llm.judge("Again: a lightweight gel-cream.", covered=["cr-p1"])
    await speak(rt, "It's a lightweight gel-cream.")
    await speak(rt, "One percent ceramide NP, five percent panthenol and three percent squalane.")
    before = len(await events(rt, "prompter.updated"))
    await speak(rt, "Hello again everyone.")
    await speak(rt, "Again: a lightweight gel-cream.")
    [seg] = await segs(rt)
    assert seg.covered_point_ids == ["cr-p1", "cr-p2"]
    assert len(await events(rt, "prompter.updated")) == before  # nothing new covered: no event
    last = (await events(rt, "prompter.updated"))[-1].payload
    assert (last["required_covered"], last["required_total"]) == (1, 3)


async def test_next_product_points_are_pre_covered_and_applied_on_commit(env):
    rt, llm = env
    llm.judge("The ampoule has four percent niacinamide, more on that later.", covered=["am-p1"])
    await speak(rt, "The ampoule has four percent niacinamide, more on that later.")
    s = await rt.load_session()
    assert s.pre_covered == {AMPOULE: ["am-p1"]} and (await segs(rt))[0].covered_point_ids == []
    assert s.switch.status == "idle"  # a next-product point alone is not a switch cue
    new = await utt.operator_switch(rt, AMPOULE)
    assert new.covered_point_ids == ["am-p1"] and (await rt.load_session()).pre_covered == {}


# ---- automatic switch ----------------------------------------------------------------------------


async def test_two_cues_pending_then_commit(env):
    rt, llm = env
    script_switch(llm)
    t1 = await speak(rt, INTRO)
    s = await rt.load_session()
    assert (s.switch.status, s.switch.cue_count, s.switch.target_product_id) == ("counting", 1, AMPOULE)
    assert s.switch.cue_transcript_ids == [t1.transcript_id] and s.pre_covered == {AMPOULE: ["am-p1"]}
    counting = await events(rt, "segment.switch_counting")
    assert counting[-1].payload == {"target_product_id": AMPOULE, "cue_count": 1, "transcript_id": t1.transcript_id}
    await advance(rt, 2000)
    await speak(rt, CONT)
    s = await rt.load_session()
    assert s.switch.status == "pending" and s.switch.cue_count == 2
    [pending] = await events(rt, "segment.switch_pending")
    commit_at = pending.payload["commit_at"]
    assert commit_at == rt.now() + 5000
    await advance(rt, 4999)
    assert len(await segs(rt)) == 1
    await advance(rt, 1)
    old, new = await segs(rt)
    assert old.product_id == CREAM and old.ended_at == commit_at
    assert (new.product_id, new.start_reason, new.started_at) == (AMPOULE, "auto_speech", commit_at)
    assert new.covered_point_ids == ["am-p1", "am-p2"]
    s = await rt.load_session()
    assert s.pre_covered == {} and s.current_segment_id == new.segment_id and s.switch.status == "idle"
    assert s.switch.last_commit == {"closed_segment_id": old.segment_id, "opened_segment_id": new.segment_id, "at": commit_at}
    [missing] = await events(rt, "segment.missing_points")
    assert missing.payload["missing_point_ids"] == ["cr-p2", "cr-p3", "cr-p4"] and len(missing.payload["missing_texts"]) == 3
    assert (await events(rt, "prompter.updated"))[-1].payload["product_id"] == AMPOULE
    assert (await events(rt, "segment.started"))[-1].payload["segment_id"] == new.segment_id


async def test_window_expiry_restarts_counting(env):
    rt, llm = env
    script_switch(llm)
    await speak(rt, INTRO)
    await advance(rt, 31_000)
    t2 = await speak(rt, INTRO2)
    s = await rt.load_session()
    assert (s.switch.status, s.switch.cue_count, s.switch.cue_transcript_ids) == ("counting", 1, [t2.transcript_id])
    assert await events(rt, "segment.switch_pending") == []


async def test_counting_reset_by_going_back(env):
    rt, llm = env
    script_switch(llm)
    await speak(rt, INTRO)
    await speak(rt, BACK)
    s = await rt.load_session()
    assert s.switch.status == "idle" and await events(rt, "segment.switch_cancelled") == []


@pytest.mark.parametrize("cancel_text, script", [
    (BACK, None),
    ("It has no added fragrance.", {"covered": ["cr-p5"]}),  # only on-air points
    ("It kills the bacteria on your skin.", {"violations": [violation("ASEAN-3-SKIN-ANTIMICROBIAL")]}),
])
async def test_pending_cancelled_by_speech(env, cancel_text, script):
    rt, llm = env
    await to_pending(rt, llm)
    if script is not None:
        llm.judge(cancel_text, **script)
    await speak(rt, cancel_text)
    assert (await rt.load_session()).switch.status == "idle"
    assert len(await events(rt, "segment.switch_cancelled")) == 1
    await advance(rt, 6000)
    assert len(await segs(rt)) == 1


@pytest.mark.parametrize("by", ["operator", "host"])
async def test_pending_cancelled_by_operator_or_host_esc(env, by):
    rt, llm = env
    await to_pending(rt, llm)
    await utt.cancel_switch(rt, by)
    [ev] = await events(rt, "segment.switch_cancelled")
    assert ev.payload["reason"] == by
    await advance(rt, 6000)
    assert len(await segs(rt)) == 1
    with pytest.raises(ActionError) as e:
        await utt.cancel_switch(rt, by)
    assert e.value.status == 409


async def test_high_alert_active_blocks_counting(env):
    rt, llm = env
    bad = "It kills the bacteria on your skin."
    llm.judge(bad, violations=[violation("ASEAN-3-SKIN-ANTIMICROBIAL")])
    await speak(rt, bad)
    script_switch(llm)
    await speak(rt, INTRO)
    assert (await rt.load_session()).switch.status == "idle"


@pytest.mark.parametrize("kw", [
    dict(utterance_type="answer", transition=True, target=AMPOULE, confidence="high"),
    dict(utterance_type="question_readout", transition=True, quote=True, target=AMPOULE, confidence="high"),
    dict(utterance_type="transition", transition=True, target=AMPOULE, confidence="low"),
    dict(covered=["am-p2"]),  # continuation without a first cue
])
async def test_not_a_cue(env, kw):
    rt, llm = env
    llm.judge("Something about the ampoule.", **kw)
    await speak(rt, "Something about the ampoule.")
    assert (await rt.load_session()).switch.status == "idle"


async def test_no_automatic_switch_after_last_product(env):
    rt, llm = env
    await utt.operator_switch(rt, AMPOULE)
    llm.judge("Now let me show you the cream again.", utterance_type="transition", transition=True, target=CREAM,
              confidence="high")
    await speak(rt, "Now let me show you the cream again.")
    await speak(rt, "Now let me show you the cream again.")
    assert (await rt.load_session()).switch.status == "idle" and len(await segs(rt)) == 2


# ---- operator switch and undo --------------------------------------------------------------------


async def test_operator_switch_and_undo(env):
    rt, llm = env
    llm.judge("Teaser: four percent niacinamide in the ampoule.", covered=["am-p1"])
    await speak(rt, "Teaser: four percent niacinamide in the ampoule.")
    new = await utt.operator_switch(rt, AMPOULE)
    assert new.start_reason == "operator" and new.covered_point_ids == ["am-p1"]
    llm.judge("Instant hydration plus forty-five percent.", covered=["am-p3"])
    await speak(rt, "Instant hydration plus forty-five percent.")
    await advance(rt, 30_000)
    reopened = await utt.undo_switch(rt)
    cream = await rt.get_segment(reopened.segment_id)
    assert cream.product_id == CREAM and cream.ended_at is None
    assert await rt.get_segment(new.segment_id) is None and [x.product_id for x in await segs(rt)] == [CREAM]
    s = await rt.load_session()
    assert s.pre_covered == {AMPOULE: ["am-p1", "am-p3"]} and s.current_segment_id == cream.segment_id
    assert s.switch.status == "idle" and s.switch.last_commit is None
    types = [e.type for e in await events(rt) if e.type in ("segment.undone", "segment.started")]
    assert types[-2:] == ["segment.undone", "segment.started"]
    assert (await events(rt, "segment.undone"))[-1].payload["segment_id"] == new.segment_id
    with pytest.raises(ActionError):
        await utt.undo_switch(rt)  # nothing left to undo


async def test_undo_after_window_is_rejected(env):
    rt, _ = env
    await utt.operator_switch(rt, AMPOULE)
    await advance(rt, 61_000)
    with pytest.raises(ActionError) as e:
        await utt.undo_switch(rt)
    assert e.value.status == 409


async def test_operator_switch_validation(env):
    rt, _ = env
    with pytest.raises(ActionError):
        await utt.operator_switch(rt, CREAM)  # already on air
    with pytest.raises(ActionError):
        await utt.operator_switch(rt, "nope")


# ---- cues ----------------------------------------------------------------------------------------


async def test_cue_covered_becomes_done(env):
    rt, llm = env
    cue = await utt.send_cue(rt, "Mention the patch test results.", None)
    assert (await rt.load_session()).cue.status == "active"
    text = "We patch tested it on thirty-two people and nobody reported a reaction."
    llm.judge(text, covered=["cr-p4"], cues=[cue.cue_id])
    t = await speak(rt, text)
    s = await rt.load_session()
    assert s.cue.status == "done" and s.cue.done_by_transcript_id == t.transcript_id
    assert (await events(rt, "cue.updated"))[-1].payload["status"] == "done"


async def test_new_cue_replaces_old_and_preset_fills_missing_points(env):
    rt, _ = env
    first = await utt.send_cue(rt, "Wrap up please.", None)
    second = await utt.send_cue(rt, None, "preset_missing_points")
    assert second.text.startswith("Please cover: Ceramide NP 1%, panthenol 5%, squalane 3%.")
    assert "Patch tested" in second.text and (await rt.load_session()).cue.cue_id == second.cue_id
    updates = [e.payload for e in await events(rt, "cue.updated")]
    assert {"cue_id": first.cue_id, "status": "cleared"}.items() <= updates[1].items()
    await utt.clear_cue(rt, second.cue_id)
    assert (await rt.load_session()).cue.status == "cleared"


# ---- pure functions --------------------------------------------------------------------------------


def _judge(**kw) -> UtteranceJudgeOutput:
    return UtteranceJudgeOutput.model_validate(judge_output(**kw))


CR_POINTS = {f"cr-p{i}" for i in range(1, 7)}
AM_POINTS = {f"am-p{i}" for i in range(1, 7)}


def classify(j, state=None, high=False, next_product=AMPOULE):
    return classify_switch(j, state or SwitchState(), on_air=CREAM, next_product=next_product,
                           on_air_points=CR_POINTS, next_points=AM_POINTS if next_product else set(),
                           high_alert_became_active=high)


def test_classify_switch():
    intro = _judge(utterance_type="transition", transition=True, target=AMPOULE, confidence="medium")
    assert classify(intro) == "cue"
    assert classify(intro, high=True) == "cancel"
    assert classify(intro, next_product=None) == "neutral"
    assert classify(_judge(covered=["am-p2"])) == "neutral"
    assert classify(_judge(covered=["am-p2"]), SwitchState(status="counting")) == "cue"
    assert classify(_judge(covered=["am-p2"], quote=True), SwitchState(status="counting")) == "neutral"
    assert classify(_judge(covered=["cr-p1", "am-p2"])) == "neutral"
    assert classify(_judge(covered=["cr-p1"])) == "cancel"
    assert classify(_judge(transition=True, target=CREAM, confidence="high")) == "cancel"
    assert classify(_judge()) == "neutral"


def test_step_switch():
    kw = dict(next_product=AMPOULE, cues_needed=2, window_sec=30, cancel_window_sec=5)
    s, ev = step_switch(SwitchState(), "cue", transcript_id="t1", now=1000, **kw)
    assert (s.status, s.cue_count, s.first_cue_at, ev) == ("counting", 1, 1000, "counting")
    s2, ev = step_switch(s, "neutral", transcript_id="t2", now=2000, **kw)
    assert s2 == s and ev is None
    s3, ev = step_switch(s, "cue", transcript_id="t3", now=31_000, **kw)
    assert (s3.status, s3.commit_at, s3.cue_transcript_ids, ev) == ("pending", 36_000, ["t1", "t3"], "pending")
    late, ev = step_switch(s, "cue", transcript_id="t4", now=31_001, **kw)
    assert (late.status, late.cue_count, late.first_cue_at) == ("counting", 1, 31_001)
    assert step_switch(s3, "cancel", transcript_id="t5", now=32_000, **kw)[1] == "cancelled"
    assert step_switch(s, "cancel", transcript_id="t5", now=2000, **kw) == (SwitchState(), "reset")
    assert step_switch(s3, "cue", transcript_id="t6", now=32_000, **kw) == (s3, None)


def test_apply_coverage_and_view(catalog):
    seg = Segment(segment_id="seg_1", product_id=CREAM, order=1, started_at=0, start_reason="session_start",
                  planned_duration_sec=900)
    s = Session(session_id="s", runsheet_id="daon_skincare_demo", title="t", status="live", created_at=0)
    added, pre = apply_coverage(["cr-p2", "am-p1", "xx", "cr-p2"], seg, s, catalog)
    assert added == ["cr-p2"] and pre == {AMPOULE: ["am-p1"]} and s.pre_covered == {AMPOULE: ["am-p1"]}
    assert apply_coverage(["cr-p2"], seg, s, catalog) == ([], {})
    assert missing_required(catalog, seg) == ["cr-p3", "cr-p4"]
    view = prompter_view(catalog, seg)
    assert (view["required_covered"], view["required_total"], view["next_product_id"]) == (1, 3, AMPOULE)
    assert [p["covered"] for p in view["points"]] == [False, True, False, False, False, False]
    assert [p["required"] for p in view["points"]] == [False, True, True, True, False, False]
