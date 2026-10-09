"""Prompter coverage and product switch (DEV_SPEC §8.7, §14.1 prompter / segments)."""
from __future__ import annotations

import pytest

from app.logic.prompter import apply_coverage, missing_required, prompter_view
from app.models.session import Segment, Session
from app.pipelines import utterances as utt
from app.pipelines.runtime import ActionError

from .judge_fakes import AMPOULE, CREAM, advance, close_env, events, make_env, speak

@pytest.fixture
async def env():
    rt, llm = await make_env()
    yield rt, llm
    await close_env(rt)


async def segs(rt) -> list[Segment]:
    return await rt.segments()


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
    assert len(await segs(rt)) == 1  # a next-product point alone is not a switch
    new = await utt.operator_switch(rt, AMPOULE)
    assert new.covered_point_ids == ["am-p1"] and (await rt.load_session()).pre_covered == {}


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
    assert s.switch.last_commit is None
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


# ---- D-419: the immediate switch only (D-415) --------------------------------------------------------------------


async def test_d419_no_automatic_switch_after_the_last_product(env):
    rt, llm = env
    await utt.operator_switch(rt, AMPOULE)  # the last product of the run sheet
    back = "Now let me show you the cream again."
    llm.judge(back, utterance_type="transition", transition=True, target=CREAM, confidence="high")
    await speak(rt, back)
    assert [s.product_id for s in await segs(rt)] == [CREAM, AMPOULE]
    assert (await rt.current_segment()).product_id == AMPOULE


async def test_d419_an_old_session_with_a_pending_switch_keeps_undo_and_runs_no_switch():
    """A session document written before D-415 (status, target, commit_at ...) loads; its Undo info stays; nothing
    commits a switch after a read-back."""
    from app.pipelines.runtime import Runtimes
    from app.store.base import SESSIONS

    from .helpers import live_runtime, make_ctx

    ctx = make_ctx()
    rt = await live_runtime(ctx)
    await utt.operator_switch(rt, AMPOULE)
    raw = (await rt.load_session()).model_dump(mode="json")
    undo = raw["switch"]["last_commit"]
    raw["switch"] |= {"status": "pending", "target_product_id": CREAM, "cue_count": 2, "cue_transcript_ids": ["t"],
                      "first_cue_at": rt.now(), "commit_at": rt.now() + 1000}
    ctx.store._data[SESSIONS][rt.sid] = raw  # as an old Firestore document would come back
    rt.shutdown()
    fresh = await Runtimes(ctx).get(rt.sid)
    try:
        s = await fresh.load_session()
        assert s.switch.last_commit == undo
        assert not ctx.scheduler.has(fresh.key("switch-commit"))
        await ctx.scheduler.advance(5000)
        assert (await fresh.current_segment()).product_id == AMPOULE
        await utt.undo_switch(fresh)
        assert (await fresh.current_segment()).product_id == CREAM
    finally:
        await close_env(fresh)


@pytest.mark.legacy_live  # D-434: JUDGE_MODE split and single read the rule JSON (deleted with them, N2)
@pytest.mark.parametrize("mode", ["split", "single"])
async def test_d419_the_mock_only_judge_modes_switch_too(mode):
    rt, llm = await make_env(JUDGE_MODE=mode)
    try:
        line = "Okay, now let me show you our Deep Hydration Ampoule."
        llm.judge(line, utterance_type="transition", transition=True, target=AMPOULE, confidence="high")
        if mode == "single":  # the single judge's own key, with its facts part
            llm.outputs[("judge_single", line)] = llm.outputs[("utterance_judge", line)] | {
                "facts": {"claims": [], "reason": "scripted"}}
        await speak(rt, line)
        assert (await rt.current_segment()).product_id == AMPOULE
    finally:
        await close_env(rt)


@pytest.mark.legacy_live  # D-434: JUDGE_MODE split and single read the rule JSON (deleted with them, N2)
@pytest.mark.parametrize("mode", ["split", "single"])
async def test_d422_a_transition_that_does_not_name_the_next_product_does_not_switch(mode):
    rt, llm = await make_env(JUDGE_MODE=mode)
    try:
        line = "Okay, let's move on."
        llm.judge(line, utterance_type="transition", transition=True, target=AMPOULE, confidence="high")
        llm.named[line] = False  # the model: moving on, but the next product is not named
        if mode == "single":
            llm.outputs[("judge_single", line)] = llm.outputs[("utterance_judge", line)] | {
                "facts": {"claims": [], "reason": "scripted"}}
        await speak(rt, line)
        assert (await rt.current_segment()).product_id == CREAM
    finally:
        await close_env(rt)
