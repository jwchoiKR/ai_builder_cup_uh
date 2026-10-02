"""Utterance pipeline end to end (DEV_SPEC §8.2) with a scripted LLM backend."""
from __future__ import annotations

import asyncio
import re

import pytest

from app.pipelines.runtime import ActionError

from .helpers import say
from .judge_fakes import (
    ScriptedBackend,
    close_env,
    events,
    make_env,
    price_contradiction,
    speak,
    violation,
)

WRINKLES = "Use it every night and your wrinkles will disappear overnight."
BACTERIA = "It kills the bacteria on your skin."
WRONG = "And today the live price is only thirty-two dollars."


class RecordingScripted(ScriptedBackend):
    """Also keeps the rendered user message of every call (to check agent inputs)."""

    def __init__(self) -> None:
        super().__init__()
        self.messages: dict[tuple[str, str], str] = {}

    async def generate(self, req, timeout_ms):
        self.messages[(req.agent, req.mock_primary_text)] = req.user_message
        return await super().generate(req, timeout_ms)


@pytest.fixture
async def env():
    rt, llm = await make_env()
    yield rt, llm
    await close_env(rt)


def data_block(message: str, name: str) -> str:
    return re.search(rf'<data name="{name}">(.*?)</data>', message, re.S).group(1)


async def test_transcript_stored_and_emitted(env):
    rt, _ = env
    seg = await rt.current_segment()
    t = await speak(rt, "Hi everyone, welcome to DAON LAB live!")
    [ev] = await events(rt, "transcript.final")
    assert ev.payload["transcript_id"] == t.transcript_id and ev.payload["source"] == "injected"
    assert ev.payload["segment_id"] == seg.segment_id and ev.payload["is_final"]
    assert ev.payload["speech_end_at"] == ev.payload["received_at"] == rt.now()


async def test_transcripts_are_processed_in_order(env):
    rt, llm = env
    texts = [f"Line number {i}." for i in range(5)]
    for i, text in enumerate(texts):
        llm.judge(text, covered=[f"cr-p{i + 1}"])
        llm.delays[("utterance_judge", text)] = 0.05 * (5 - i)  # earlier lines are slower
    for text in texts:
        await speak(rt, text, wait=False)
    await rt.ctx.scheduler.idle()
    assert [e.payload["text"] for e in await events(rt, "transcript.final")] == texts
    covered = [e.payload["covered_point_ids"][-1] for e in await events(rt, "prompter.updated")
               if e.payload["covered_point_ids"]]
    assert covered == ["cr-p1", "cr-p2", "cr-p3", "cr-p4", "cr-p5"]
    assert (await rt.current_segment()).covered_point_ids == ["cr-p1", "cr-p2", "cr-p3", "cr-p4", "cr-p5"]


async def test_steps_1_to_4_wait_for_the_previous_judge(env):
    rt, llm = env
    llm.judge(BACTERIA, violations=[violation("ASEAN-3-SKIN-ANTIMICROBIAL")])
    llm.delays[("utterance_judge", BACTERIA)] = 0.3
    llm.judge(WRINKLES, violations=[violation("ASEAN-3-SKIN-AGEING")])
    await speak(rt, BACTERIA, wait=False)
    await speak(rt, WRINKLES, wait=False)
    await rt.ctx.scheduler.idle()
    created = [e.payload["rule_id"] for e in await events(rt, "alert.created")]
    assert created == ["ASEAN-3-SKIN-ANTIMICROBIAL", "ASEAN-3-SKIN-AGEING"]  # N1's reflex step ran after N's judge


async def test_slow_fact_check_does_not_block_next_compliance(env):
    rt, llm = env
    llm.facts(WRONG, price_contradiction(), delay=0.4)
    llm.judge(BACTERIA, violations=[violation("ASEAN-3-SKIN-ANTIMICROBIAL")])
    await speak(rt, WRONG, wait=False)
    await speak(rt, BACTERIA, wait=False)
    for _ in range(150):
        if any(a.kind == "compliance" and a.status == "active" for a in await rt.alerts()):
            break
        await asyncio.sleep(0.01)
    alerts = await rt.alerts()
    assert any(a.kind == "compliance" and a.status == "active" for a in alerts)
    assert not any(a.kind == "fact" for a in alerts)  # N's fact check still running
    await rt.ctx.scheduler.idle()
    created = [(e.payload["kind"], e.seq) for e in await events(rt, "alert.created")]
    assert [k for k, _ in created] == ["compliance", "fact"]  # compliance of N+1 applied before facts of N


async def test_judge_input_lists(tmp_path):
    from .helpers import live_runtime, make_ctx

    llm = RecordingScripted()
    ctx = make_ctx(backend=llm)
    rt = await live_runtime(ctx)
    try:
        await say(rt, "Raj", "Is it OK for oily skin?")
        [g] = await rt.groups()
        llm.judge(WRINKLES, violations=[violation("ASEAN-3-SKIN-AGEING")])
        await speak(rt, WRINKLES)
        first, first_ctx = llm.messages[("compliance_judge", WRINKLES)], llm.messages[("context_judge", WRINKLES)]
        assert data_block(first, "ACTIVE_ALERTS") == "[]"  # its own provisional alert is not listed
        assert f'"group_id":"{g.group_id}"' in data_block(first_ctx, "OPEN_QUESTIONS")
        assert '"suggested_answer":"' in data_block(first_ctx, "OPEN_QUESTIONS")
        assert "OPEN_QUESTIONS" not in first and "ACTIVE_ALERTS" not in first_ctx  # D-099: each judge its own data
        assert data_block(first, "RECENT_TRANSCRIPT") == data_block(first_ctx, "RECENT_TRANSCRIPT") == "[]"
        await speak(rt, "Next sentence.")
        second = llm.messages[("compliance_judge", "Next sentence.")]
        second_ctx = llm.messages[("context_judge", "Next sentence.")]
        [a] = await rt.alerts()
        assert f'"alert_id":"{a.alert_id}"' in data_block(second, "ACTIVE_ALERTS")
        assert data_block(second, "RECENT_TRANSCRIPT") == f'["{WRINKLES}"]'
        points = data_block(second_ctx, "PROMPTER_POINTS")
        assert '"point_id":"cr-p1"' in points and '"point_id":"am-p1"' in points
        facts_msg = llm.messages[("fact_checker", "Next sentence.")]
        assert '"in_progress":false' in data_block(facts_msg, "SWITCH_CONTEXT")
        assert "DL-CR-01#key-facts#live-broadcast-price" in data_block(facts_msg, "SOURCE")
    finally:
        await close_env(rt)


async def test_single_mode_applies_compliance_and_facts_from_one_call():
    rt, llm = await make_env(JUDGE_MODE="single")
    try:
        text = "It kills bacteria and it's only thirty-two dollars."
        llm.single(text, violations=[violation("ASEAN-3-SKIN-ANTIMICROBIAL")], claims=[price_contradiction()])
        await speak(rt, text)
        kinds = sorted((a.kind, a.status) for a in await rt.alerts())
        assert kinds == [("compliance", "active"), ("fact", "active")]
        agents = {agent for agent, _ in llm.calls}
        assert "judge_single" in agents and "fact_checker" not in agents
    finally:
        await close_env(rt)


async def test_validation_and_state(env):
    rt, _ = env
    with pytest.raises(ActionError) as e:
        await rt.inject_transcript("   ")
    assert e.value.status == 400
    await rt.end()
    with pytest.raises(ActionError) as e:
        await rt.inject_transcript("Hello?")
    assert e.value.status == 409


async def test_snapshot_blocks(env):
    rt, llm = env
    llm.judge(BACTERIA, violations=[violation("ASEAN-3-SKIN-ANTIMICROBIAL")], covered=["cr-p1"])
    await speak(rt, BACTERIA)
    op = await rt.snapshot("operator")
    host = await rt.snapshot("host")
    assert [a["rule_id"] for a in op["alerts"]] == ["ASEAN-3-SKIN-ANTIMICROBIAL"] and host["alerts"] == op["alerts"]
    assert op["prompter"]["covered_point_ids"] == ["cr-p1"] and op["prompter"]["required_total"] == 3
    assert [t["text"] for t in op["transcripts"]] == [BACTERIA] and "transcripts" not in host
    assert {"compliance_judge", "context_judge"} <= {c["agent"] for c in op["agent_calls"]} and "agent_calls" not in host
    assert op["metrics"]["alert"]["count"] == 1
