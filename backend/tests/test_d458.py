"""D-458 INCOMPLETE_HOLD: a final the context judge says stops mid-thought keeps its alerts until the next final, which
is judged with it as one line; with no next final in time, its alerts are shown alone. Made-up lines only."""
from __future__ import annotations

import pytest

from .helpers import make_ctx, product_show, text_pdf
from .judge_fakes import ScriptedBackend, advance, close_env, events, speak

CODE = text_pdf("Vellum Code\n2.1 A cosmetic must not be presented as treating disease.\n")
TONER = {"brand": "Vellum", "product_name": "Calm Toner", "category": "toner", "currency": "SGD",
         "variants": [{"label": "", "list_price": "30.00", "live_price": "25.00"}],
         "points": [{"text": "Alcohol-free.", "required": True}]}
A = "Our new toner calms any rash in one."  # speech-to-text closed the line mid-sentence
B = "Week, that is what a viewer asked, and no, it does not."
AB = f"{A} {B}"


def verdict(span: str) -> dict:
    return {"alert_checks": [], "compliance": {"violations": [{
        "citation": "vellum_code.pdf#2.1", "quote": "must not be presented as treating disease", "span": span,
        "severity": "HIGH", "is_negated": False, "is_quoted": False, "say_instead": "It feels soothing."}]},
        "reason": "scripted"}


async def show(llm, **settings):
    from app.pipelines.runtime import create_session

    ctx = make_ctx(backend=llm, **settings)
    s = await create_session(ctx, "", release_id=product_show(ctx, TONER, [("vellum_code.pdf", CODE)]))
    rt = await ctx.runtimes.get(s.session_id)
    await rt.start()
    await ctx.scheduler.advance(5000)
    return rt


@pytest.fixture
async def env():
    llm = ScriptedBackend()
    llm.outputs[("compliance_judge", A)] = verdict("calms any rash")
    llm.incomplete[A] = True
    rt = await show(llm, INCOMPLETE_HOLD=True, INCOMPLETE_HOLD_MS=2500)
    yield rt, llm
    await close_env(rt)


async def created(rt) -> list:
    return [e.payload for e in await events(rt, "alert.created")]


async def test_next_final_in_time_judges_the_pair_once_and_never_shows_the_piece(env):
    rt, llm = env
    a = await speak(rt, A)
    assert await created(rt) == []  # held: its verdict is in, but it waits for the next final
    assert [e.payload["transcript_id"] for e in await events(rt, "hold.started")] == [a.transcript_id]
    await advance(rt, 1000)
    llm.outputs[("compliance_judge", AB)] = verdict("calms any rash in one week")
    llm.incomplete[AB] = True  # a merged line is never held again
    b = await speak(rt, B)
    assert ("compliance_judge", B) not in llm.calls and ("fact_checker", B) not in llm.calls
    assert ("compliance_judge", AB) in llm.calls
    shown = await created(rt)
    assert [x["transcript_id"] for x in shown] == [b.transcript_id]  # the merged verdict, at once
    assert rt.utterances.hold_counts == {"holds": 1, "superseded": 1, "released_alone": 0}
    assert [e.payload["transcript_id"] for e in await events(rt, "hold.ended")] == [a.transcript_id]
    await advance(rt, 5000)  # the piece's timer is gone: nothing more is shown
    assert len(await created(rt)) == 1
    assert rt.utterances.incomplete == {a.transcript_id: True, b.transcript_id: True}


async def test_no_next_final_in_time_shows_the_held_alerts_from_the_piece_end(env):
    rt, _ = env
    a = await speak(rt, A)
    await advance(rt, 2499)
    assert await created(rt) == []
    await advance(rt, 1)
    [shown] = await created(rt)
    assert shown["transcript_id"] == a.transcript_id and shown["created_at"] == a.received_at + 2500
    assert rt.utterances.hold_counts == {"holds": 1, "superseded": 0, "released_alone": 1}


async def test_a_next_final_after_the_window_is_judged_alone(env):
    rt, llm = env
    await speak(rt, A)
    await advance(rt, 3000)
    await speak(rt, B)
    assert ("compliance_judge", B) in llm.calls and ("compliance_judge", AB) not in llm.calls
    assert rt.utterances.hold_counts["released_alone"] == 1


async def test_the_second_piece_waits_for_a_slow_context_verdict_and_is_not_judged_alone(env):
    rt, llm = env
    llm.delays[("context_judge", A)] = 0.05
    await speak(rt, A, wait=False)
    rt.ctx.clock.advance(800)
    await speak(rt, B)
    assert ("compliance_judge", B) not in llm.calls and ("compliance_judge", AB) in llm.calls
    assert rt.utterances.hold_counts["superseded"] == 1
    assert await created(rt) == []


async def test_a_failed_context_check_shows_the_alerts_at_once(env):
    rt, llm = env
    llm.fail("context_judge", A)
    a = await speak(rt, A)
    assert [x["transcript_id"] for x in await created(rt)] == [a.transcript_id]
    assert rt.utterances.hold_counts["holds"] == 0 and rt.utterances.incomplete[a.transcript_id] is None


async def test_a_whole_line_shows_its_alerts_once_its_context_verdict_is_in(env):
    rt, llm = env
    llm.incomplete[A] = False
    a = await speak(rt, A)
    assert [x["transcript_id"] for x in await created(rt)] == [a.transcript_id]
    assert await events(rt, "hold.started") == []


async def test_on_by_default_an_incomplete_final_is_held():
    llm = ScriptedBackend()
    llm.outputs[("compliance_judge", A)] = verdict("calms any rash")
    llm.incomplete[A] = True
    rt = await show(llm)  # D-459: code defaults
    try:
        a = await speak(rt, A)
        assert await created(rt) == []
        assert "incomplete" in rt.utterances.context.output_model.model_fields
        assert rt.utterances.incomplete == {a.transcript_id: True}
    finally:
        await close_env(rt)


async def test_switched_off_the_context_output_has_no_incomplete_field():
    llm = ScriptedBackend()
    llm.outputs[("compliance_judge", A)] = verdict("calms any rash")
    llm.incomplete[A] = True
    rt = await show(llm, INCOMPLETE_HOLD=False)
    try:
        a = await speak(rt, A)
        assert [x["transcript_id"] for x in await created(rt)] == [a.transcript_id]
        assert "incomplete" not in rt.utterances.context.output_model.model_fields
        assert rt.utterances.incomplete == {}
    finally:
        await close_env(rt)
