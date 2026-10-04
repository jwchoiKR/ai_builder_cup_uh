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


def test_no_talking_point_cards_promo_first_then_questions():
    """D-107: the prompter's highlighted next point is the talking-point cue, so no cover_point card."""
    st = state(promos=[pdl.PromoState("promo", "TIME SALE", 490_000, 1_090_000)],
               questions=[pdl.Question("g1", "Oily skin?", "Yes, a little.")])
    assert [c.kind for c in pdl.candidates(st)] == ["promo", "answer_question"]
    assert pdl.rule_pick(pdl.candidates(st)).ref_id == "promo"
    assert pdl.candidates(state()) == []  # 55% of the time, required points missing: no card at all


def test_switch_late_names_the_missing_required_points_verbatim_before_questions():
    q = [pdl.Question("g1", "Oily skin?", "Yes, a little.")]
    assert not [c for c in pdl.candidates(state(now=700_000, questions=q)) if c.kind == "switch_product"]  # 78%
    late = pdl.candidates(state(now=800_000, questions=q))
    assert [c.kind for c in late] == ["switch_product", "answer_question"]
    assert late[0].say == "Before switching: Point 2; Point 3, then introduce Y." and late[0].ref_id == "y"
    assert late[0].detail == "2 required points left"
    one_left = pdl.candidates(state(now=800_000, covered_ids=["x-p2"]))[0]
    assert one_left.say == "Before switching: Point 3, then introduce Y." and one_left.cid != late[0].cid
    done = pdl.candidates(state(now=800_000, covered_ids=["x-p2", "x-p3"], questions=q))
    assert [c.kind for c in done] == ["answer_question", "switch_product"] and done[1].say == "Next up: Y"


def test_wrap_up_on_the_last_product_names_the_missing_points():
    [w] = pdl.candidates(state(now=800_000, next_product=None, covered_ids=["x-p2"]))
    assert w.kind == "wrap_up"
    assert w.say == "Before wrapping up: Point 3, then thank viewers and remind them of today's live price."


def test_pause_offers_nothing_new_and_red_alert_offers_nothing():
    quiet = state(now=100_000, last_final_at=100_000 - pdl.SILENCE_MS, covered_ids=["x-p2", "x-p3"])
    assert pdl.candidates(quiet) == []
    assert pdl.candidates(state(high_alert_active=True, now=800_000)) == []


def test_dismissed_topics_are_not_offered_again():
    st = state(now=800_000, dismissed_refs=frozenset({"y"}))
    assert "y" not in {c.ref_id for c in pdl.candidates(st)}


# ---- director on the runtime (mock provider: rule fallback) ---------------------------------------


@pytest.fixture
async def env():
    rt, llm = await make_env()
    yield rt, llm
    await close_env(rt)


async def late_in_segment(rt, share: float = 0.85) -> None:
    seg = await rt.current_segment()
    seg.started_at -= int(seg.planned_duration_sec * 1000 * share)
    await rt.save_segment(seg)
    rt.pd.trigger()
    await rt.ctx.scheduler.idle()


async def test_no_card_mid_segment_and_no_premature_switch(env):
    """D-107: without cover_point cards nothing is shown mid-segment, and a late switch card never
    switches by itself: the D-090 switch rules (a named transition, then a point of the new product) apply."""
    rt, _ = env
    assert rt.pd.agent is None  # mock provider: rules only, no network
    seg = await rt.current_segment()
    await late_in_segment(rt, 0.6)
    assert (await rt.load_session()).pd_card is None
    await late_in_segment(rt, 0.3)  # now 90% of the planned time
    s = await rt.load_session()
    assert s.pd_card is not None and s.pd_card.kind == "switch_product" and s.pd_card.source == "rule"
    assert s.pd_card.say.startswith("Before switching: Ceramide NP 1%, panthenol 5%, squalane 3%")
    assert s.switch.status == "idle" and (await rt.current_segment()).segment_id == seg.segment_id


async def test_switch_card_text_drops_a_point_once_it_is_said(env):
    rt, llm = env
    await late_in_segment(rt)
    card = (await rt.load_session()).pd_card
    assert "Ceramide NP" in card.say
    [ev] = await events(rt, "pd.card")
    assert ev.payload["card_id"] == card.card_id and ev.payload["status"] == "active"
    line = "Inside there is one percent ceramide NP and five percent panthenol."
    llm.judge(line, covered=["cr-p2"])
    await speak(rt, line)
    await rt.ctx.scheduler.advance(pdl.HOLD_MS)
    await rt.ctx.scheduler.idle()
    now = (await rt.load_session()).pd_card
    assert now is not None and now.card_id == card.card_id and "Ceramide NP" not in now.say


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
