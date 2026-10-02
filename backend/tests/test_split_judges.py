"""JUDGE_MODE=split3 (D-099): the compliance and context judges run in parallel and each verdict is
applied as soon as it arrives; the publish decision needs both."""
from __future__ import annotations

import asyncio

import pytest

from .judge_fakes import AMPOULE, close_env, events, make_env, speak, violation
from .test_publish import ANSWER, messages, oily_on_host

BACTERIA = "It kills the bacteria on your skin."
SWITCH_AND_CLAIM = "Next up, the ampoule, and it kills the bacteria on your skin."


@pytest.fixture
async def env():
    rt, llm = await make_env()
    yield rt, llm
    await close_env(rt)


async def until(check, tries: int = 150) -> None:
    for _ in range(tries):
        if await check():
            return
        await asyncio.sleep(0.01)


async def test_compliance_is_applied_before_a_slow_context_judge(env):
    rt, llm = env
    llm.judge(BACTERIA, violations=[violation("ASEAN-3-SKIN-ANTIMICROBIAL")], covered=["cr-p1"])
    llm.delays[("context_judge", BACTERIA)] = 0.4

    async def alert_shown():
        return any(a.kind == "compliance" and a.status == "active" for a in await rt.alerts())

    await speak(rt, BACTERIA, wait=False)
    await until(alert_shown)
    assert await alert_shown()
    assert (await rt.current_segment()).covered_point_ids == []  # the context judge is still running
    await rt.ctx.scheduler.idle()
    assert (await rt.current_segment()).covered_point_ids == ["cr-p1"]


async def test_late_high_alert_resets_a_switch_the_context_judge_started(env):
    rt, llm = env
    llm.judge(SWITCH_AND_CLAIM, violations=[violation("ASEAN-3-SKIN-ANTIMICROBIAL")], transition=True,
              target=AMPOULE, confidence="high")
    llm.delays[("compliance_judge", SWITCH_AND_CLAIM)] = 0.2
    await speak(rt, SWITCH_AND_CLAIM)
    assert [e.payload["cue_count"] for e in await events(rt, "segment.switch_counting")] == [1]
    assert [a.status for a in await rt.alerts()] == ["active"]
    assert (await rt.load_session()).switch.status == "idle"  # §8.4.7, same result as one judge


async def test_context_failure_keeps_alerts_and_skips_publish(env):
    rt, llm = env
    g = await oily_on_host(rt)
    llm.judge(ANSWER, utterance_type="answer", matched=g.group_id, is_answer=True, consistent=True)
    llm.fail("context_judge", ANSWER)
    llm.judge(BACTERIA, violations=[violation("ASEAN-3-SKIN-ANTIMICROBIAL")])
    llm.fail("context_judge", BACTERIA)
    await speak(rt, ANSWER)
    await speak(rt, BACTERIA)
    assert await messages(rt, "host_answer") == []
    assert [a.rule_id for a in await rt.alerts() if a.status == "active"] == ["ASEAN-3-SKIN-ANTIMICROBIAL"]
    assert await events(rt, "judge.failed") == []  # only a compliance failure is shown to the operator


async def test_compliance_failure_fails_toward_warning_and_skips_publish(env):
    rt, llm = env
    g = await oily_on_host(rt)
    llm.judge(ANSWER, utterance_type="answer", matched=g.group_id, is_answer=True, consistent=True, covered=["cr-p1"])
    llm.fail("compliance_judge", ANSWER)
    await speak(rt, ANSWER)
    [ev] = await events(rt, "judge.failed")
    assert ev.payload["status"] == "error"
    assert await messages(rt, "host_answer") == []  # no compliance verdict: never post
    assert (await rt.current_segment()).covered_point_ids == ["cr-p1"]  # context still applied


async def test_both_verdicts_publish_the_host_answer(env):
    rt, llm = env
    g = await oily_on_host(rt)
    llm.judge(ANSWER, utterance_type="answer", matched=g.group_id, is_answer=True, consistent=True)
    llm.delays[("compliance_judge", ANSWER)] = 0.1
    await speak(rt, ANSWER)
    [m] = await messages(rt, "host_answer")
    assert m.state == "pending"


async def test_split_mode_is_kept_for_rollback():
    rt, llm = await make_env(JUDGE_MODE="split")
    try:
        llm.judge(BACTERIA, violations=[violation("ASEAN-3-SKIN-ANTIMICROBIAL")], covered=["cr-p1"])
        await speak(rt, BACTERIA)
        agents = {agent for agent, _ in llm.calls}
        assert "utterance_judge" in agents and not agents & {"compliance_judge", "context_judge"}
        assert [a.status for a in await rt.alerts()] == ["active"]
        assert (await rt.current_segment()).covered_point_ids == ["cr-p1"]
    finally:
        await close_env(rt)
