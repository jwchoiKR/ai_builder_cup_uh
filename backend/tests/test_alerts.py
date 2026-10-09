"""Compliance alert lifecycle (DEV_SPEC §8.4, §14.1 alerts)."""
from __future__ import annotations

import pytest

from app.logic import alerts as alert_logic
from app.models.session import Alert
from app.pipelines import utterances as utt
from app.pipelines.runtime import ActionError

from .judge_fakes import CREAM, advance, close_env, events, make_env, speak, violation

WRINKLES = "Use it every night and your wrinkles will disappear overnight."
BACTERIA = "It kills the bacteria on your skin."


@pytest.fixture
async def env():
    rt, llm = await make_env()
    yield rt, llm
    await close_env(rt)


async def only_alert(rt) -> Alert:
    [a] = await rt.alerts()
    return a


# ---- judge confirms / clears -------------------------------------------------------------------


async def test_a_judge_violation_is_an_active_alert(env):
    rt, llm = env
    llm.judge(WRINKLES, violations=[violation("ASEAN-3-SKIN-AGEING", "your wrinkles will disappear overnight",
                                              severity="MEDIUM", say="With regular use, it helps keep skin hydrated.")])
    t = await speak(rt, WRINKLES)
    a = await only_alert(rt)
    assert (a.kind, a.status, a.rule_id) == ("compliance", "active", "ASEAN-3-SKIN-AGEING")
    assert a.severity == "MEDIUM"  # D-391: the model's severity and wording, as given
    assert a.span == "your wrinkles will disappear overnight" and a.say_instead == "With regular use, it helps keep skin hydrated."
    assert a.shown_at is not None and a.transcript_id == t.transcript_id and not a.unverified
    # D-410: no provisional alert first; the judge's verdict is the only alert event
    assert [e.type for e in await events(rt) if e.type.startswith("alert.")] == ["alert.created"]


async def test_judge_violation_without_reflex_hit_creates_active(env):
    rt, llm = env
    llm.judge(BACTERIA, violations=[violation("ASEAN-3-SKIN-ANTIMICROBIAL", "kills the bacteria")])
    await speak(rt, BACTERIA)
    a = await only_alert(rt)
    assert a.status == "active" and a.shown_at is not None
    assert [e.type for e in await events(rt) if e.type.startswith("alert.")] == ["alert.created"]


async def test_unknown_rule_is_dropped(env):
    rt, llm = env
    llm.judge(BACTERIA, violations=[violation("NOT-A-RULE")])
    await speak(rt, BACTERIA)
    assert await rt.alerts() == []


@pytest.mark.parametrize("text, rule, flags", [
    ("Just to be clear, it does not treat acne. It's a moisturiser.", "ASEAN-3-SKIN-ACNE", {"negated": True}),
    ("Someone asked if it cures eczema.", "ASEAN-2D-DISEASE", {"quoted": True}),
])
async def test_negated_or_quoted_gives_no_alert(env, text, rule, flags):
    rt, llm = env
    llm.judge(text, violations=[violation(rule, **flags)])
    await speak(rt, text)
    assert await rt.alerts() == []


# ---- judge failure: D-410, the neutral card only ----------------------------------------------------


@pytest.mark.parametrize("text", [WRINKLES, "Hello everyone."])
async def test_judge_failure_gives_the_check_card_and_no_alert(env, text):
    rt, llm = env
    llm.fail("utterance_judge", text)
    t = await speak(rt, text)
    assert await rt.alerts() == []
    failed = await events(rt, "judge.failed")  # D-416: one per failed judge (both split judges fail here)
    assert {f.payload["agent"] for f in failed} == {"compliance_judge", "context_judge"}
    assert all(f.payload["transcript_id"] == t.transcript_id and f.payload["alert_ids"] == [] for f in failed)
    [card] = await events(rt, "line.check")  # the line is unchecked once
    assert card.payload["text"] == text and card.payload["rule_ids"] == []


# ---- escalation, correction, dismiss ------------------------------------------------------------


async def test_escalation_at_five_seconds_and_no_auto_expiry(env):
    rt, llm = env
    llm.judge(BACTERIA, violations=[violation("ASEAN-3-SKIN-ANTIMICROBIAL")])
    await speak(rt, BACTERIA)
    await advance(rt, 4999)
    assert (await only_alert(rt)).escalated_at is None
    await advance(rt, 1)
    a = await only_alert(rt)
    assert a.escalated_at == a.shown_at + 5000 and a.status == "active"
    [esc] = await events(rt, "alert.escalated")
    assert esc.payload["alert_id"] == a.alert_id
    await advance(rt, 600_000)  # no auto-expiry
    assert (await only_alert(rt)).status == "active"
    assert len(await events(rt, "alert.escalated")) == 1


async def test_medium_alert_is_not_escalated(env):
    rt, llm = env
    text = "Honestly this is the best moisturiser in Singapore."
    llm.judge(text, violations=[violation("BRAND-SUPERLATIVE", "the best moisturiser in Singapore", severity="MEDIUM")])
    await speak(rt, text)
    await advance(rt, 6000)
    a = await only_alert(rt)
    assert a.status == "active" and a.severity == "MEDIUM" and a.escalated_at is None


async def test_correction_resolves_only_the_listed_alert(env):
    """D-117: no longer every alert of the same transcript (§8.4.5); each claim needs its own correction."""
    rt, llm = env
    double = "It cures eczema and kills the bacteria on your skin."
    other = "You'll look ten years younger after one bottle."
    llm.judge(double, violations=[violation("ASEAN-2D-DISEASE", "cures eczema"),
                                  violation("ASEAN-3-SKIN-ANTIMICROBIAL", "kills the bacteria")])
    llm.judge(other, violations=[violation("ASEAN-3-SKIN-AGEING", "ten years younger")])
    t1 = await speak(rt, double)
    await speak(rt, other)
    first = next(a for a in await rt.alerts() if a.rule_id == "ASEAN-2D-DISEASE")
    fix = "Let me correct that. It helps relieve the feeling of dryness."
    llm.judge(fix, corrects=[first.alert_id], utterance_type="correction")
    t3 = await speak(rt, fix)
    by_rule = {a.rule_id: a for a in await rt.alerts()}
    a = by_rule["ASEAN-2D-DISEASE"]
    assert a.transcript_id == t1.transcript_id
    assert a.status == "corrected" and a.resolved_at is not None
    assert a.corrected_by_transcript_id == t3.transcript_id and a.corrected_text == fix
    assert by_rule["ASEAN-3-SKIN-ANTIMICROBIAL"].status == "active"  # same sentence, not corrected
    assert by_rule["ASEAN-3-SKIN-AGEING"].status == "active"  # other transcript, not listed


async def test_corrected_before_five_seconds_is_not_escalated(env):
    rt, llm = env
    llm.judge(BACTERIA, violations=[violation("ASEAN-3-SKIN-ANTIMICROBIAL")])
    await speak(rt, BACTERIA)
    a = await only_alert(rt)
    await advance(rt, 2000)
    fix = "Let me correct that. It helps relieve the feeling of dryness."  # D-089: says the approved claim
    llm.judge(fix, corrects=[a.alert_id], utterance_type="correction")
    await speak(rt, fix)
    await advance(rt, 10_000)
    a = await only_alert(rt)
    assert a.status == "corrected" and a.escalated_at is None
    assert a.resolved_at - a.shown_at == 2000
    assert await events(rt, "alert.escalated") == []


async def test_correction_ids_not_offered_are_ignored(env):
    rt, llm = env
    llm.judge(BACTERIA, violations=[violation("ASEAN-3-SKIN-ANTIMICROBIAL")])
    await speak(rt, BACTERIA)
    llm.judge("Sorry.", corrects=["al_999999"], utterance_type="correction")
    await speak(rt, "Sorry.")
    assert (await only_alert(rt)).status == "active"


async def test_dismiss(env):
    rt, llm = env
    llm.judge(BACTERIA, violations=[violation("ASEAN-3-SKIN-ANTIMICROBIAL")])
    await speak(rt, BACTERIA)
    a = await only_alert(rt)
    await utt.dismiss_alert(rt, a.alert_id)
    a = await only_alert(rt)
    assert a.status == "dismissed" and a.dismissed_reason == "false_alarm" and a.resolved_at is not None
    await advance(rt, 6000)
    assert (await only_alert(rt)).escalated_at is None
    with pytest.raises(ActionError) as e:
        await utt.dismiss_alert(rt, a.alert_id)
    assert e.value.status == 409
    with pytest.raises(ActionError) as e:
        await utt.dismiss_alert(rt, "al_missing")
    assert e.value.status == 404


async def test_multiple_active_high_alerts(env):
    rt, llm = env
    llm.judge(BACTERIA, violations=[violation("ASEAN-3-SKIN-ANTIMICROBIAL")])
    llm.judge(WRINKLES, violations=[violation("ASEAN-3-SKIN-AGEING")])
    await speak(rt, BACTERIA)
    await advance(rt, 1000)
    await speak(rt, WRINKLES)
    active = [a for a in await rt.alerts() if a.status == "active"]
    assert len(active) == 2 and all(a.severity == "HIGH" for a in active)
    assert alert_logic.high_alert_active(active)


async def test_repeat_of_active_rule_creates_a_second_alert(env):
    rt, llm = env
    llm.judge(BACTERIA, violations=[violation("ASEAN-3-SKIN-ANTIMICROBIAL")])
    await speak(rt, BACTERIA)
    await advance(rt, 5000)  # a separate sentence, outside the adjacent-final window (D-118)
    again = "Really, it kills bacteria."
    llm.judge(again, violations=[violation("ASEAN-3-SKIN-ANTIMICROBIAL", "kills bacteria")])
    await speak(rt, again)
    alerts = await rt.alerts()
    assert [a.status for a in alerts] == ["active", "active"]


async def test_d387_two_claims_of_one_rule_in_adjacent_finals_are_two_alerts(env):
    """D-118 merged these by rule inside the adjacent-final window; D-387 (user): each violation the model returns is
    its own alert."""
    rt, llm = env
    first, second = "The ampoule treats acne.", "So you will never break out again."
    llm.judge(first, violations=[violation("ASEAN-3-SKIN-ACNE", "treats acne")])
    llm.judge(second, violations=[violation("ASEAN-3-SKIN-ACNE", "never break out again")])
    await speak(rt, first)
    await advance(rt, 1500)
    await speak(rt, second)
    assert [(a.span, a.status) for a in await rt.alerts() if a.kind == "compliance"] == [
        ("treats acne", "active"), ("never break out again", "active")]


async def test_render_ack(env):
    rt, llm = env
    llm.judge(BACTERIA, violations=[violation("ASEAN-3-SKIN-ANTIMICROBIAL")])
    await speak(rt, BACTERIA)
    a = await only_alert(rt)
    await advance(rt, 300)
    await utt.render_ack(rt, a.alert_id)
    await advance(rt, 300)
    await utt.render_ack(rt, a.alert_id)  # only the first ack counts
    assert (await only_alert(rt)).host_rendered_at == a.shown_at + 300


# ---- pure functions -----------------------------------------------------------------------------


def test_dismiss_function_states():
    a = Alert(alert_id="al_1", kind="compliance", status="corrected", transcript_id="t", product_id=CREAM, created_at=0)
    assert alert_logic.dismiss(a, 5) is False
    a.status = "active"
    assert alert_logic.dismiss(a, 5) and a.status == "dismissed" and a.resolved_at == 5


@pytest.mark.parametrize("agent", ["compliance_judge", "context_judge", "fact_checker"])
async def test_judge_health_turns_amber_after_two_failed_finals_and_recovers(env, agent):
    """D-137 (feature B2): silence must not look like safety. Two failed finals in a row of one judge
    turn the host's health dot amber; its next answer turns it back."""
    rt, llm = env
    for text in ("The cream feels light.", "It absorbs quickly."):
        llm.fail(agent, text)
        await speak(rt, text)
    assert rt.utterances.degraded == [agent]
    assert (await rt.snapshot("host"))["judge_health"] == {"degraded": [agent]}
    await speak(rt, "Use it every morning.")
    assert rt.utterances.degraded == []
    assert [e.payload["degraded"] for e in await events(rt, "judge.health")] == [[agent], []]


async def test_one_failed_final_is_not_a_health_problem(env):
    rt, llm = env
    llm.fail("compliance_judge", "The cream feels light.")
    await speak(rt, "The cream feels light.")
    await speak(rt, "It absorbs quickly.")
    assert rt.utterances.degraded == [] and await events(rt, "judge.health") == []


async def test_extend_adds_two_minutes_to_the_on_air_segment(env):
    """D-138 (feature B3): the plan, the overtime check and the AI PD's thresholds all move together."""
    rt, _ = env
    seg = await rt.current_segment()
    planned = seg.planned_duration_sec
    rt.overtime_emitted.add(seg.segment_id)
    out = await rt.extend_segment()
    assert out.planned_duration_sec == planned + 120
    assert (await rt.current_segment()).planned_duration_sec == planned + 120
    assert seg.segment_id not in rt.overtime_emitted  # it can be reported again, after the new end
    assert (await rt.pd._state()).planned_ms == (planned + 120) * 1000
    [e] = await events(rt, "segment.extended")
    assert e.payload["added_sec"] == 120


async def test_two_failures_within_a_minute_turn_amber_even_with_answers_between(env):
    """D-144 (cloud lines run, LT055): two fact-checker timeouts 58 s apart, other lines answered between."""
    rt, llm = env
    llm.fail("fact_checker", "The cream feels light.")
    await speak(rt, "The cream feels light.")
    await speak(rt, "It absorbs quickly.")  # answered on time
    assert rt.utterances.degraded == []
    await advance(rt, 50_000)
    llm.fail("fact_checker", "Use it every morning.")
    await speak(rt, "Use it every morning.")
    assert rt.utterances.degraded == ["fact_checker"]
    await speak(rt, "It comes in a tube.")  # the next on-time answer clears it
    assert rt.utterances.degraded == []
    await advance(rt, 70_000)  # outside the window: one more failure alone is nothing
    llm.fail("fact_checker", "It is made in Korea.")
    await speak(rt, "It is made in Korea.")
    assert rt.utterances.degraded == []


async def test_a_fact_call_slower_than_the_on_time_line_counts_for_the_health_dot(env):
    """D-144: the fact call may answer until FACT_LATE_MS (its note still shows), but past FACT_TIMEOUT_MS
    it counts as a timeout for the dot."""
    rt, llm = env
    assert rt.settings.FACT_LATE_MS >= rt.settings.FACT_TIMEOUT_MS  # D-255: both 5 s by default
    await rt.utterances._note_health("fact_checker", "timeout")
    await advance(rt, 1000)
    await rt.utterances._note_health("fact_checker", "timeout")
    assert rt.utterances.degraded == ["fact_checker"]


pytestmark = pytest.mark.legacy_live  # D-434: not migrated yet (removed in its batch)
