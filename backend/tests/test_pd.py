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
    assert (await rt.current_segment()).segment_id == seg.segment_id


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


# ---- D-113 shout-outs; D-161/D-402 alert blocks ---------------------------------------------------


def test_shout_outs_only_at_a_pause_with_no_question_waiting_and_30_s_apart():
    so = [pdl.ShoutOut("cm1", "Mei", "purchase", 99_000)]
    paused = dict(now=100_000, last_final_at=100_000 - pdl.SILENCE_MS, shoutouts=so)
    [c] = pdl.candidates(state(**paused))
    assert (c.kind, c.say) == ("shout_out", "Thank you Mei for your order!")
    assert pdl.candidates(state(questions_waiting=True, **paused)) == []  # a question on the list comes first
    assert pdl.candidates(state(last_shout_at=100_000 - 10_000, **paused)) == []


async def test_an_uncorrected_red_alert_blocks_cards_only_while_it_is_fresh(env):
    """D-161 (local SEED1 replay: a red nobody corrected blocked every card for the last 10 minutes of the show).
    A red blocks cards for RED_BLOCK_MS after it was created; then cards resume while it waits (D-177)."""
    rt, llm = env
    line = "Use it every night and your wrinkles will disappear overnight."
    llm.judge(line, violations=[violation("ASEAN-3-SKIN-AGEING")])
    await speak(rt, line)
    [red] = [a for a in await rt.alerts() if a.severity == "HIGH" and a.status == "active"]
    await late_in_segment(rt)  # a switch card would be offered now
    assert (await rt.load_session()).pd_card is None
    await rt.ctx.scheduler.advance(pdl.RED_BLOCK_MS)  # D-177: 20 s, the escalation adds nothing
    card = (await rt.load_session()).pd_card
    assert card is not None and card.kind == "switch_product"
    assert (await rt.get_alert(red.alert_id)).status == "active"  # the red still waits for its correction


async def test_d402_a_fact_note_blocks_cards_like_a_red(env):
    """D-402 (user: red and orange at the same level): an orange alert blocks AI PD cards for RED_BLOCK_MS too."""
    from .judge_fakes import price_contradiction

    rt, llm = env
    line = "And today the live price is only thirty-two dollars."
    llm.facts(line, price_contradiction("S$32"))
    await speak(rt, line)
    [note] = [a for a in await rt.alerts() if a.kind == "fact" and a.status == "active"]
    await late_in_segment(rt)
    assert (await rt.load_session()).pd_card is None
    await rt.ctx.scheduler.advance(pdl.RED_BLOCK_MS)
    card = (await rt.load_session()).pd_card
    assert card is not None and card.kind == "switch_product"
    assert (await rt.get_alert(note.alert_id)).status == "active"  # D-402: the note stays until closed


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


async def test_d431_a_question_card_stored_before_d429_ends_at_the_next_decision(env):
    """D-431 (codex review): nothing else would end it now that no question cards are made."""
    from app.models.session import PdCard

    rt, _ = env
    seg = await rt.current_segment()
    s = await rt.load_session()
    s.pd_card = PdCard(card_id="pd_old", kind="read_question", say="S$36.", ref_id="grp_x", created_at=rt.now(),
                       hold_until=rt.now() + pdl.HOLD_MS, source="rule", segment_id=seg.segment_id)
    await rt.save_session(s)
    rt.pd.trigger()
    await rt.ctx.scheduler.idle()
    assert (await rt.load_session()).pd_card is None
    [ev] = [e for e in await events(rt, "pd.card") if e.payload["card_id"] == "pd_old"]
    assert ev.payload["status"] == "done"
