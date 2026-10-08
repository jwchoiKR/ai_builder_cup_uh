"""D-403 (codex on D-401; user: option A): the model says which listed alert a violation repeats (`same_as`, by
handle); code no longer decides sameness by rule id. Fictional law pack; scripted verdicts; the production path."""
from __future__ import annotations

import asyncio

import pytest

from app.pipelines.utterances import dismiss_alert

from .judge_fakes import advance, close_env, events, speak
from .test_d358 import _Backend, _show, _verdict

pytestmark = pytest.mark.originals

FRAG, REST = "Honestly, this cures eczema", "and psoriasis too."
MERGED = f"{FRAG} {REST}"


def _two(eczema_same_as: str | None) -> dict:
    out = _verdict("kelmar_code.pdf#2.1", "must not be presented", span="cures eczema")
    v = out["compliance"]["violations"][0]
    out["compliance"]["violations"] = [{**v, "same_as": eczema_same_as}, {**v, "span": "psoriasis too", "same_as": None}]
    return out


async def _merge(rt, dismiss: bool = False) -> None:
    await speak(rt, FRAG)
    [frag] = [a for a in await rt.alerts() if a.kind == "compliance"]
    await advance(rt, 1200)
    await rt.inject_transcript(REST)
    await asyncio.sleep(0.1)
    if dismiss:
        await dismiss_alert(rt, frag.alert_id)  # the operator dismisses it while the merged check runs
    await rt.utterances.drain()
    await asyncio.sleep(0.5)
    await rt.ctx.scheduler.idle()


async def test_d403_eczema_dismissed_during_the_merge_stays_closed_and_psoriasis_shows(tmp_path):
    llm = _Backend()
    llm.outputs[("compliance_judge", FRAG)] = _verdict("kelmar_code.pdf#2.1", "must not be presented",
                                                       span="cures eczema")
    llm.outputs[("compliance_judge", MERGED)] = _two("A1")
    llm.delays[("compliance_judge", MERGED)] = 0.4
    rt = await _show(tmp_path, llm)
    try:
        await _merge(rt, dismiss=True)
        status = {a.span: a.status for a in await rt.alerts() if a.kind == "compliance"}
        assert status == {"cures eczema": "dismissed", "psoriasis too": "active"}  # same rule, a different claim
        req = [r for r in llm.requests if r.agent == "compliance_judge" and r.mock_primary_text == MERGED][-1]
        assert '"raised_s_ago"' in req.user_message  # each listed alert's age goes to the model
    finally:
        await close_env(rt)


async def test_d403_a_merged_line_repeating_a1_keeps_a1_s_id(tmp_path):
    llm = _Backend()
    llm.outputs[("compliance_judge", FRAG)] = _verdict("kelmar_code.pdf#2.1", "must not be presented",
                                                       span="cures eczema")
    llm.outputs[("compliance_judge", MERGED)] = _two("A1")
    rt = await _show(tmp_path, llm)
    try:
        await _merge(rt)
        [frag] = [a for a in await rt.alerts() if a.kind == "compliance" and a.span == "cures eczema"]
        assert frag.status == "active"
        assert len([e for e in await events(rt, "alert.created") if e.payload["kind"] == "compliance"]) == 2  # + psoriasis
        assert {a.span for a in await rt.alerts() if a.kind == "compliance" and a.status == "active"} == {
            "cures eczema", "psoriasis too"}
    finally:
        await close_env(rt)


async def test_d403_without_same_as_the_merged_verdict_replaces_the_fragment_s_alert(tmp_path):
    llm = _Backend()
    llm.outputs[("compliance_judge", FRAG)] = _verdict("kelmar_code.pdf#2.1", "must not be presented",
                                                       span="cures eczema")
    llm.outputs[("compliance_judge", MERGED)] = _two(None)
    rt = await _show(tmp_path, llm)
    try:
        await _merge(rt)
        alerts = [a for a in await rt.alerts() if a.kind == "compliance"]
        assert sorted((a.span, a.status) for a in alerts) == [("cures eczema", "active"), ("cures eczema", "cleared"),
                                                               ("psoriasis too", "active")]
    finally:
        await close_env(rt)
