"""D-462 ALERT_GRACE: a new alert reaches the host ALERT_GRACE_MS after its line's end; when the next final came within
that time, also after that final's verdicts, which may clear it first (then the host never sees it); at the latest 5 s
after its line's end. The operator sees every alert at once. Made-up lines only."""
from __future__ import annotations

import pytest

from app.bus import for_role

from .helpers import make_ctx, product_show, text_pdf
from .judge_fakes import ScriptedBackend, advance, close_env, events, speak

CODE = text_pdf("Vellum Code\n2.1 A cosmetic must not be presented as treating disease.\n")
TONER = {"brand": "Vellum", "product_name": "Calm Toner", "category": "toner", "currency": "SGD",
         "variants": [{"label": "", "list_price": "30.00", "live_price": "25.00"}],
         "points": [{"text": "Alcohol-free.", "required": True}]}
A = "Our toner heals rashes overnight."
B = "Sorry, I take that back, it simply feels soothing."
C = "It comes in a glass bottle."
Q = "Is it sold in a bigger size?"


def violation() -> dict:
    return {"alert_checks": [], "compliance": {"violations": [{
        "citation": "vellum_code.pdf#2.1", "quote": "must not be presented as treating disease", "span": "heals rashes",
        "severity": "HIGH", "is_negated": False, "is_quoted": False, "say_instead": "It feels soothing."}]},
        "reason": "scripted"}


def fixes_first_alert() -> dict:
    return {"alert_checks": [{"handle": "A1", "fixed_by_this_line": True}], "compliance": {"violations": []},
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
    llm.outputs[("compliance_judge", A)] = violation()
    rt = await show(llm, ALERT_GRACE=True, ALERT_GRACE_MS=2000)
    yield rt, llm
    await close_env(rt)


async def host_alerts(rt) -> list[dict]:
    """The alert events the host's stream carries."""
    return [out.payload for e in await events(rt) if e.type.startswith("alert.")
            and (out := for_role(e, "host")) is not None]


async def test_alone_the_operator_sees_it_at_once_and_the_host_after_the_grace_time(env):
    rt, _ = env
    a = await speak(rt, A)
    [created] = [e.payload for e in await events(rt, "alert.created")]
    assert created["shown_at"] is None and created["created_at"] == a.received_at  # the operator's stream has it
    assert await host_alerts(rt) == []
    assert (await rt.snapshot("host"))["alerts"] == [] and len((await rt.snapshot("operator"))["alerts"]) == 1
    await advance(rt, 1999)
    assert await host_alerts(rt) == []
    await advance(rt, 1)
    [shown] = await host_alerts(rt)
    assert shown["shown_at"] == a.speech_end_at + 2000 and shown["status"] == "active"
    assert len((await rt.snapshot("host"))["alerts"]) == 1
    g = rt.utterances.grace[shown["alert_id"]]
    assert g["outcome"] == "published" and g["next_in_window"] is False


async def test_a_next_final_in_time_that_corrects_it_keeps_it_off_the_host_screen(env, caplog):
    rt, llm = env
    caplog.set_level("INFO", logger="app.pipelines.utterances")
    await speak(rt, A)
    [aid] = [a.alert_id for a in await rt.alerts()]
    llm.outputs[("compliance_judge", B)] = fixes_first_alert()
    await advance(rt, 1000)
    b = await speak(rt, B)
    await advance(rt, 5000)
    [a] = await rt.alerts()
    assert a.status == "corrected" and a.shown_at is None
    assert await host_alerts(rt) == [] and (await rt.snapshot("host"))["alerts"] == []
    g = rt.utterances.grace[aid]
    assert (g["outcome"], g["next_final"], g["next_in_window"], g["cleared_by"]) == (
        "cleared before display", b.transcript_id, True, b.transcript_id)
    assert "provisional alert cleared before display" in caplog.text


async def test_a_next_final_in_time_that_does_not_clear_it_shows_it_at_the_grace_time(env):
    rt, _ = env
    a = await speak(rt, A)
    await advance(rt, 1000)
    c = await speak(rt, C)
    await advance(rt, 999)
    assert await host_alerts(rt) == []
    await advance(rt, 1)
    [shown] = await host_alerts(rt)
    assert shown["shown_at"] == a.speech_end_at + 2000
    g = rt.utterances.grace[shown["alert_id"]]
    assert (g["next_final"], g["next_in_window"]) == (c.transcript_id, True)


async def test_a_next_final_after_the_window_does_not_delay_it(env):
    rt, _ = env
    a = await speak(rt, A)
    await advance(rt, 2500)
    await speak(rt, C)
    [shown] = await host_alerts(rt)
    assert shown["shown_at"] == a.speech_end_at + 2000
    assert rt.utterances.grace[shown["alert_id"]]["next_in_window"] is False


async def test_it_waits_for_the_next_finals_verdicts(env):
    rt, _ = env  # a question is held for its answer (QUESTION_HOLD_MS 2500), so its verdicts come after the grace time
    a = await speak(rt, A)
    await advance(rt, 1000)
    await speak(rt, Q)
    await advance(rt, 1500)  # the grace time is over; the question's verdicts are not in yet
    assert await host_alerts(rt) == []
    await advance(rt, 1000)  # the question is judged alone at 1000 + 2500
    [shown] = await host_alerts(rt)
    assert shown["shown_at"] == a.speech_end_at + 3500


async def test_the_cap_shows_it_five_seconds_after_its_line_whatever_the_next_final_does():
    llm = ScriptedBackend()
    llm.outputs[("compliance_judge", A)] = violation()
    rt = await show(llm, ALERT_GRACE=True, ALERT_GRACE_MS=2000, QUESTION_HOLD_MS=4000)
    try:
        a = await speak(rt, A)
        await advance(rt, 1500)
        await speak(rt, Q)  # held until 1500 + 4000, past the cap
        await advance(rt, 3499)
        assert await host_alerts(rt) == []
        await advance(rt, 1)
        [shown] = await host_alerts(rt)
        assert shown["shown_at"] == a.speech_end_at + 5000
    finally:
        await close_env(rt)


async def test_a_verdict_after_the_grace_time_is_shown_at_once(env):
    rt, llm = env
    llm.delays[("compliance_judge", A)] = 0.05
    await speak(rt, A, wait=False)
    rt.ctx.clock.advance(2600)  # the verdict comes 2.6 s after the line's end
    await rt.ctx.scheduler.idle()
    [a] = await rt.alerts()
    assert a.shown_at == a.created_at
    assert len(await host_alerts(rt)) == 1


async def test_a_high_alert_escalates_from_when_the_host_saw_it(env):
    rt, _ = env
    a = await speak(rt, A)
    await advance(rt, 2000 + rt.settings.COMPLIANCE_ESCALATE_SEC * 1000 - 1)
    assert await events(rt, "alert.escalated") == []
    await advance(rt, 1)
    [esc] = await events(rt, "alert.escalated")
    assert esc.payload["escalated_at"] == a.speech_end_at + 2000 + rt.settings.COMPLIANCE_ESCALATE_SEC * 1000


async def test_off_by_default_the_host_sees_it_when_it_is_created():
    llm = ScriptedBackend()
    llm.outputs[("compliance_judge", A)] = violation()
    rt = await show(llm)
    try:
        await speak(rt, A)
        [shown] = await host_alerts(rt)
        assert shown["shown_at"] == shown["created_at"]
        assert rt.utterances.grace == {}
    finally:
        await close_env(rt)


async def test_a_fact_note_the_next_final_fixes_in_time_never_reaches_the_host(env):
    from .judge_fakes import claim

    rt, llm = env
    wrong, fix = "The toner is S$20 today.", "Sorry, it is S$25 today."
    llm.facts(wrong, claim("price", "contradicted", product_id="prd_000000000001", stated="S$20", correct="S$25.00",
                           span="S$20"))
    llm.facts(fix, fixed=["F1"])
    await speak(rt, wrong)
    [note] = [a for a in await rt.alerts() if a.kind == "fact"]
    assert note.shown_at is None
    await advance(rt, 800)
    await speak(rt, fix)
    await advance(rt, 5000)
    note = await rt.get_alert(note.alert_id)
    assert note.status != "active" and note.shown_at is None
    assert await host_alerts(rt) == []
    assert rt.utterances.grace[note.alert_id]["outcome"] == "cleared before display"
