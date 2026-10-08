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


# ---- D-406: same_as only on a merged (speech-to-text split) line, only within its chain and product ----------


def _req(llm, text):
    return [r for r in llm.requests if r.agent == "compliance_judge" and r.mock_primary_text == text][-1]


async def test_d406_a_later_line_repeating_a1_raises_a2_and_its_block(tmp_path):
    import json

    from app.logic import pd as pdl

    llm = _Backend()
    first, again = "It cures eczema.", "Really, it cures eczema."
    llm.outputs[("compliance_judge", first)] = _verdict("kelmar_code.pdf#2.1", "q", span="cures eczema")
    out = _verdict("kelmar_code.pdf#2.1", "q", span="cures eczema")
    out["compliance"]["violations"][0]["same_as"] = "A1"  # a same_as on an ordinary line is never applied
    llm.outputs[("compliance_judge", again)] = out
    rt = await _show(tmp_path, llm)
    try:
        await speak(rt, first)
        await advance(rt, 25_000)
        await speak(rt, again)
        alerts = [a for a in await rt.alerts() if a.kind == "compliance"]
        assert [a.status for a in alerts] == ["active", "active"] and len({a.alert_id for a in alerts}) == 2
        assert pdl.alert_blocks(await rt.alerts(), rt.now())  # the repeat is new: it blocks cards for 20 s again
        req = _req(llm, again)  # an ordinary line is not asked for same_as
        assert "same_as" not in json.dumps(req.output_model.model_json_schema()) and "MERGED_LINE" not in req.user_message
    finally:
        await close_env(rt)


async def test_d406_the_merged_line_is_asked_for_same_as(tmp_path):
    import json

    llm = _Backend()
    llm.outputs[("compliance_judge", FRAG)] = _verdict("kelmar_code.pdf#2.1", "must not be presented",
                                                       span="cures eczema")
    llm.outputs[("compliance_judge", MERGED)] = _two("A1")
    rt = await _show(tmp_path, llm)
    try:
        await _merge(rt)
        req = _req(llm, MERGED)
        assert "same_as" in json.dumps(req.output_model.model_json_schema()) and "MERGED_LINE" in req.user_message
    finally:
        await close_env(rt)


async def test_d406_same_as_to_another_product_s_alert_raises_a_new_one(tmp_path):
    llm = _Backend()
    llm.outputs[("compliance_judge", FRAG)] = _verdict("kelmar_code.pdf#2.1", "must not be presented",
                                                       span="cures eczema")
    llm.outputs[("compliance_judge", MERGED)] = _two("A1")
    llm.delays[("compliance_judge", MERGED)] = 0.4
    rt = await _show(tmp_path, llm)
    try:
        await speak(rt, FRAG)
        [frag] = [a for a in await rt.alerts() if a.kind == "compliance"]
        frag.product_id = "another_product"  # the handle names an alert of another product
        await rt.save_alert(frag)
        await advance(rt, 1200)
        await rt.inject_transcript(REST)
        await rt.utterances.drain()
        await asyncio.sleep(0.5)
        await rt.ctx.scheduler.idle()
        alerts = [a for a in await rt.alerts() if a.kind == "compliance"]
        eczema = [a for a in alerts if a.span == "cures eczema"]
        assert len(eczema) == 2 and sorted(a.status for a in eczema) == ["active", "cleared"]
    finally:
        await close_env(rt)


async def test_d406_a_late_correction_of_t2_does_not_close_t3_s_alert(tmp_path):
    llm = _Backend()
    t1, t2, t3 = "It cures eczema.", "Sorry, I take that back.", "Honestly though, it cures eczema."
    llm.outputs[("compliance_judge", t1)] = _verdict("kelmar_code.pdf#2.1", "q", span="cures eczema")
    llm.outputs[("compliance_judge", t2)] = {"alert_checks": [{"handle": "A1", "fixed_by_this_line": True}],
                                             "compliance": {"violations": []}, "reason": "scripted"}
    llm.delays[("compliance_judge", t2)] = 0.4  # T2's verdict lands after T3's
    out = _verdict("kelmar_code.pdf#2.1", "q", span="it cures eczema")
    out["compliance"]["violations"][0]["same_as"] = "A1"
    llm.outputs[("compliance_judge", t3)] = out
    rt = await _show(tmp_path, llm)
    try:
        await speak(rt, t1)
        await advance(rt, 5000)
        await rt.inject_transcript(t2)
        await advance(rt, 5000)
        await rt.inject_transcript(t3)
        await rt.utterances.drain()
        await asyncio.sleep(0.6)
        await rt.ctx.scheduler.idle()
        status = {a.span: a.status for a in await rt.alerts() if a.kind == "compliance"}
        assert status == {"cures eczema": "corrected", "it cures eczema": "active"}
    finally:
        await close_env(rt)
