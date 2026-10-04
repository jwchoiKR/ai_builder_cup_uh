"""AI PD (PLANNING 5.1.1): candidates, rule fallback and the director on the mock provider."""
from __future__ import annotations

import pytest

from app.logic import pd as pdl
from app.models.data import PrompterPoint

from .judge_fakes import close_env, events, make_env, speak, violation

P = [PrompterPoint(point_id=f"x-p{i}", text=f"Point {i}.", required=i in (2, 3)) for i in range(1, 5)]


def state(**kw) -> pdl.PdState:
    base = dict(now=500_000, segment_id="seg", product_id="x", product_name="X", started_at=0, planned_ms=900_000,
                points=P, required_ids=["x-p2", "x-p3"], covered_ids=[], next_product=("y", "Y"))
    return pdl.PdState(**(base | kw))


def test_promo_first_then_missing_required_point_late_in_the_segment():
    st = state(promos=[pdl.PromoState("promo", "TIME SALE", 490_000, 1_090_000)],
               questions=[pdl.Question("g1", "Oily skin?", "Yes, a little.")])
    kinds = [c.kind for c in pdl.candidates(st)]
    assert kinds[:3] == ["promo", "cover_point", "cover_point"] and "answer_question" in kinds
    assert pdl.rule_pick(pdl.candidates(st)).ref_id == "promo"


def test_question_comes_before_required_points_early_in_the_segment():
    st = state(now=100_000, questions=[pdl.Question("g1", "Oily skin?", "Yes, a little.")])
    assert pdl.rule_pick(pdl.candidates(st)).kind == "answer_question"


def test_switch_only_when_required_points_are_done_and_time_is_nearly_up():
    assert not [c for c in pdl.candidates(state(now=800_000)) if c.kind == "switch_product"]
    done = state(now=800_000, covered_ids=["x-p2", "x-p3"])
    [sw] = [c for c in pdl.candidates(done) if c.kind == "switch_product"]
    assert sw.say == "Next up: Y" and sw.ref_id == "y"


def test_pause_offers_other_points_and_red_alert_offers_nothing():
    quiet = state(now=100_000, last_final_at=100_000 - pdl.SILENCE_MS, covered_ids=["x-p2", "x-p3"])
    assert {c.ref_id for c in pdl.candidates(quiet)} == {"x-p1", "x-p4"}
    assert pdl.candidates(state(high_alert_active=True)) == []


def test_dismissed_topics_are_not_offered_again():
    st = state(dismissed_refs=frozenset({"x-p2"}))
    assert "x-p2" not in {c.ref_id for c in pdl.candidates(st)}


# ---- director on the runtime (mock provider: rule fallback) ---------------------------------------


@pytest.fixture
async def env():
    rt, llm = await make_env()
    yield rt, llm
    await close_env(rt)


async def late_in_segment(rt) -> None:
    seg = await rt.current_segment()
    seg.started_at -= seg.planned_duration_sec * 600  # 60% of the planned time has passed
    await rt.save_segment(seg)
    rt.pd.trigger()
    await rt.ctx.scheduler.idle()


async def test_card_appears_for_a_missing_required_point_and_ends_when_said(env):
    rt, llm = env
    assert rt.pd.agent is None  # mock provider: rules only, no network
    await late_in_segment(rt)
    s = await rt.load_session()
    card = s.pd_card
    assert card is not None and card.kind == "cover_point" and card.source == "rule"
    assert card.ref_id == "cr-p2" and card.say.startswith("Ceramide NP 1%")
    [ev] = await events(rt, "pd.card")
    assert ev.payload["card_id"] == card.card_id and ev.payload["status"] == "active"
    line = "Inside there is one percent ceramide NP and five percent panthenol."
    llm.judge(line, covered=["cr-p2"])
    await speak(rt, line)
    ended = [e.payload for e in await events(rt, "pd.card") if e.payload["card_id"] == card.card_id]
    assert ended[-1]["status"] == "done"
    nxt = (await rt.load_session()).pd_card
    assert nxt is not None and nxt.ref_id != "cr-p2"


async def test_dismissed_card_is_not_shown_again(env):
    rt, _ = env
    await late_in_segment(rt)
    card = (await rt.load_session()).pd_card
    out = await rt.pd.dismiss(card.card_id)
    assert out.status == "dismissed"
    await rt.ctx.scheduler.idle()
    nxt = (await rt.load_session()).pd_card
    assert nxt is None or nxt.ref_id != card.ref_id
    assert await rt.pd.dismiss(card.card_id) is None  # already ended


async def test_no_new_card_while_a_red_alert_is_active(env):
    """The host screen hides the current card under the red overlay; the PD adds nothing new."""
    rt, llm = env
    line = "Use it every night and your wrinkles will disappear overnight."
    llm.judge(line, violations=[violation("ASEAN-3-SKIN-AGEING")])
    await speak(rt, line)
    assert any(a.status == "active" and a.severity == "HIGH" for a in await rt.alerts())
    before = len(await events(rt, "pd.card"))
    await late_in_segment(rt)
    assert len(await events(rt, "pd.card")) == before
