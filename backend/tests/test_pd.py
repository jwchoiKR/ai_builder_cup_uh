"""AI PD (PLANNING 5.1.1): candidates, rule fallback and the director on the mock provider. D-429 (user): no
question cards and no question timing; the host reads the ranked questions from the list."""
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


def test_no_talking_point_cards_and_no_question_cards():
    """D-107: the prompter's highlighted next point is the talking-point cue, so no cover_point card. D-429: a
    question waiting on the host's list makes no card."""
    st = state(promos=[pdl.PromoState("promo", "TIME SALE", 490_000, 1_090_000)], questions_waiting=True,
               last_final_at=500_000 - pdl.SILENCE_MS)
    assert [c.kind for c in pdl.candidates(st)] == ["promo"]
    assert pdl.rule_pick(pdl.candidates(st)).ref_id == "promo"
    assert pdl.candidates(state()) == []  # 55% of the time, required points missing: no card at all


def test_switch_late_names_the_missing_required_points_verbatim():
    assert not [c for c in pdl.candidates(state(now=700_000)) if c.kind == "switch_product"]  # 78%
    late = pdl.candidates(state(now=800_000))
    assert [c.kind for c in late] == ["switch_product"]
    assert late[0].say == "Before switching: Point 2; Point 3, then introduce Y." and late[0].ref_id == "y"
    assert late[0].detail == "2 required points left"
    one_left = pdl.candidates(state(now=800_000, covered_ids=["x-p2"]))[0]
    assert one_left.say == "Before switching: Point 3, then introduce Y." and one_left.cid != late[0].cid
    done = pdl.candidates(state(now=800_000, covered_ids=["x-p2", "x-p3"]))
    assert [c.kind for c in done] == ["switch_product"] and done[0].say == "Next up: Y"


def test_wrap_up_on_the_last_product_names_the_missing_points():
    [w] = pdl.candidates(state(now=800_000, next_product=None, covered_ids=["x-p2"]))
    assert w.kind == "wrap_up"
    assert w.say == "Before wrapping up: Point 3, then thank viewers and remind them of today's live price."


def test_pause_offers_nothing_new_and_red_alert_offers_nothing():
    quiet = state(now=100_000, last_final_at=100_000 - pdl.SILENCE_MS, covered_ids=["x-p2", "x-p3"])
    assert pdl.candidates(quiet) == []
    assert pdl.candidates(state(alert_block=True, now=800_000)) == []


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


# ---- D-113 shout-outs; D-161/D-402 alert blocks ---------------------------------------------------


def test_shout_outs_only_at_a_pause_with_no_question_waiting_and_30_s_apart():
    so = [pdl.ShoutOut("cm1", "Mei", "purchase", 99_000)]
    paused = dict(now=100_000, last_final_at=100_000 - pdl.SILENCE_MS, shoutouts=so)
    [c] = pdl.candidates(state(**paused))
    assert (c.kind, c.say) == ("shout_out", "Thank you Mei for your order!")
    assert pdl.candidates(state(questions_waiting=True, **paused)) == []  # a question on the list comes first
    assert pdl.candidates(state(last_shout_at=100_000 - 10_000, **paused)) == []


def test_a_fresh_alert_is_one_created_within_the_block():
    from app.models.session import Alert

    base = dict(alert_id="al", kind="compliance", status="active", transcript_id="t", product_id="p",
                severity="HIGH", rule_id="R", created_at=0)
    assert pdl.alert_blocks([Alert(**base)], pdl.RED_BLOCK_MS - 1)
    assert not pdl.alert_blocks([Alert(**base)], pdl.RED_BLOCK_MS)
    assert not pdl.alert_blocks([Alert(**base, escalated_at=5_000)], pdl.RED_BLOCK_MS)  # D-177
    assert not pdl.alert_blocks([Alert(**{**base, "status": "corrected"})], 1)
    # D-402: orange blocks the same way: a MEDIUM compliance alert and a fact note
    assert pdl.alert_blocks([Alert(**{**base, "severity": "MEDIUM"})], 1)
    fact = {**base, "kind": "fact", "severity": None, "rule_id": None}
    assert pdl.alert_blocks([Alert(**fact)], pdl.RED_BLOCK_MS - 1)
    assert not pdl.alert_blocks([Alert(**fact)], pdl.RED_BLOCK_MS)
    assert not pdl.alert_blocks([Alert(**{**fact, "status": "dismissed"})], 1)
