"""AI PD (PLANNING 5.1.1): candidates, rule fallback and the director on the mock provider."""
from __future__ import annotations

import pytest

from app.logic import pd as pdl
from app.models.data import PrompterPoint

from .helpers import say
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


# ---- D-113: one question card at a time, paced ---------------------------------------------------

Q = [pdl.Question("g1", "Oily skin?", "Yes, a little.", askers=2), pdl.Question("g2", "Size?", "50 mL.")]


def kinds_at(**kw) -> list[str]:
    return [c.kind for c in pdl.candidates(state(now=100_000, **kw))]


def test_question_cards_wait_for_a_pause_and_the_gap():
    talking = dict(last_final_at=100_000 - 2_000)
    paused = dict(last_final_at=100_000 - pdl.SILENCE_MS)
    assert kinds_at(questions=Q, **talking) == []  # mid-sentence: nothing
    assert kinds_at(questions=Q, **paused) == ["answer_question", "answer_question"]
    recent = dict(paused, last_question_card_at=100_000 - pdl.Q_GAP_MS + 1)
    assert kinds_at(questions=Q, **recent) == []  # 45 s gap between question cards
    [c, _] = pdl.candidates(state(now=100_000, questions=Q, **paused))
    assert (c.say, c.detail, c.askers) == ("Yes, a little.", "Oily skin?", 2)


def test_operator_push_skips_the_gap_and_the_host_pull_takes_the_top_one_now():
    pushed = [pdl.Question("g9", "Pregnant?", "Ask your doctor.", pushed=True), *Q]
    recent = dict(last_final_at=100_000 - pdl.SILENCE_MS, last_question_card_at=100_000 - 1_000)
    [c] = pdl.candidates(state(now=100_000, questions=pushed, **recent))
    assert (c.ref_id, c.priority) == ("g9", 0)
    talking = dict(last_final_at=100_000 - 2_000, last_question_card_at=100_000 - 1_000)
    assert pdl.candidates(state(now=100_000, questions=pushed, **talking)) == []  # a push still waits for a pause
    [top] = pdl.candidates(state(now=100_000, questions=Q, pull=True, **talking))
    assert (top.ref_id, top.priority) == ("g1", 0)


def test_read_out_and_which_product_cards():
    qs = [pdl.Question("g3", "How much?", "S$36.", kind="read", askers=4),
          pdl.Question("g4", "Does it sting?", None, kind="clarify")]
    read, clarify = pdl.candidates(state(now=100_000, questions=qs, product_names=["Cream", "Ampoule"]))
    assert (read.kind, read.say, read.detail) == ("read_question", "S$36.", "4 people asked: How much?")
    assert (clarify.kind, clarify.say) == ("clarify_product", "Which product do you mean: Cream or Ampoule?")


def test_shout_outs_only_at_a_pause_with_no_question_waiting_and_30_s_apart():
    so = [pdl.ShoutOut("cm1", "Mei", "purchase", 99_000)]
    paused = dict(last_final_at=100_000 - pdl.SILENCE_MS, shoutouts=so)
    [c] = pdl.candidates(state(now=100_000, **paused))
    assert (c.kind, c.say) == ("shout_out", "Thank you Mei for your order!")
    assert kinds_at(questions=Q[:1], **paused) == ["answer_question"]  # questions first, no shout-out
    assert kinds_at(last_shout_at=100_000 - 10_000, **paused) == []


async def test_a_paced_question_card_on_the_runtime_and_the_host_pull(env):
    rt, _ = env
    await say(rt, "Mei", "Is the cream okay for oily skin?")
    [g] = await rt.groups()
    assert g.route == "HOST" and g.status == "ready"
    await rt.ctx.scheduler.advance(1000)
    card = (await rt.load_session()).pd_card
    assert card is not None and card.kind == "answer_question" and card.ref_id == g.group_id and card.askers == 1
    await rt.pd.dismiss(card.card_id)
    await say(rt, "Raj", "Can I use it under makeup?")
    await rt.ctx.scheduler.advance(1000)
    assert (await rt.load_session()).pd_card is None  # within the 45 s gap
    rt.pd.pull()
    await rt.ctx.scheduler.advance(1000)
    pulled = (await rt.load_session()).pd_card
    assert pulled is not None and pulled.kind == "answer_question" and pulled.ref_id != g.group_id


def test_a_question_waiting_past_its_ceiling_gets_a_card_at_the_next_break():
    """D-146 (sealed show replay): a talkative host never pauses 8 s; a waiting question still gets its card,
    right after a final, once it has waited 90 s (30 s when sensitive or 3+ askers)."""
    just_after_final = dict(last_final_at=100_000 - 500)
    mid = dict(last_final_at=100_000 - 4_000)  # talking, not at a break
    fresh = [pdl.Question("g1", "Under makeup?", "Yes.", waiting_ms=60_000)]
    old = [pdl.Question("g1", "Under makeup?", "Yes.", waiting_ms=pdl.CEILING_MS)]
    urgent = [pdl.Question("g2", "Pregnant?", "Ask your doctor.", waiting_ms=pdl.URGENT_CEILING_MS, urgent=True)]
    assert kinds_at(questions=fresh, **just_after_final) == []
    assert kinds_at(questions=old, **mid) == []  # waits for the break
    assert kinds_at(questions=old, **just_after_final) == ["answer_question"]
    [c] = pdl.candidates(state(now=100_000, questions=urgent + old, **just_after_final))[:1]
    assert (c.ref_id, c.priority) == ("g2", 1)  # the urgent one first
    recent_card = dict(just_after_final, last_question_card_at=100_000 - pdl.DUE_GAP_MS + 1)
    assert kinds_at(questions=old, **recent_card) == []
    assert kinds_at(questions=old, high_alert_active=True, **just_after_final) == []  # a red alert pre-empts


class SaysNone:
    """The AI PD model when the host is always mid-topic: it picks "none" every time."""

    def __init__(self):
        self.calls = 0

    async def choose(self, state, candidates, deadline_ms):
        from app.agents.ai_pd import PdChoice

        self.calls += 1
        return PdChoice(choice="none", reason="Host is mid-topic; nothing urgent."), 5, "ok"


async def test_a_due_question_card_shows_even_when_the_model_says_none(env):
    """00007 show replays: verified HOST drafts waited 4-7 minutes and never got a card. The host talked with
    4 s gaps, so the card was only offered as due (D-146); the model said "none" (mid-topic), and the same
    candidate id was never asked about again."""
    rt, _ = env
    rt.pd.agent = SaysNone()
    await speak(rt, "Welcome everyone, today we start with the cream.")
    await say(rt, "Mei", "Is the cream okay for oily skin?")
    [g] = await rt.groups()
    assert g.route == "HOST" and g.status == "ready"
    for _ in range(30):  # 120 s of talking, never an 8 s pause
        await rt.ctx.scheduler.advance(4000)
        await speak(rt, "Look at the texture, it is so light on the skin.")
        await rt.ctx.scheduler.advance(500)
        card = (await rt.load_session()).pd_card
        if card is not None:
            break
    assert card is not None and card.ref_id == g.group_id
    assert rt.pd.agent.calls == 0  # D-163: a due question is decided by the rules, the model is not asked


async def test_an_uncorrected_red_alert_blocks_cards_only_while_it_is_fresh(env):
    """D-161 (local SEED1 replay: a red nobody corrected blocked every card for the last 10 minutes of the show).
    A red blocks cards for RED_BLOCK_MS after it was created; then cards resume while it waits (D-177)."""
    rt, llm = env
    await speak(rt, "Welcome everyone, today we start with the cream.")  # talking: no pause, no card yet
    await say(rt, "Mei", "Is the cream okay for oily skin?")
    [g] = await rt.groups()
    assert g.route == "HOST" and g.status == "ready" and (await rt.load_session()).pd_card is None
    line = "Use it every night and your wrinkles will disappear overnight."
    llm.judge(line, violations=[violation("ASEAN-3-SKIN-AGEING")])
    await speak(rt, line)
    [red] = [a for a in await rt.alerts() if a.severity == "HIGH" and a.status == "active"]
    await rt.ctx.scheduler.advance(pdl.SILENCE_MS)  # a pause: the card would be offered now
    assert (await rt.load_session()).pd_card is None
    await rt.ctx.scheduler.advance(pdl.RED_BLOCK_MS - pdl.SILENCE_MS)  # D-177: 20 s, the escalation adds nothing
    card = (await rt.load_session()).pd_card
    assert card is not None and card.ref_id == g.group_id
    assert (await rt.get_alert(red.alert_id)).status == "active"  # the red still waits for its correction


def test_a_fresh_red_alert_is_one_created_within_the_block():
    from app.models.session import Alert

    base = dict(alert_id="al", kind="compliance", status="active", transcript_id="t", product_id="p",
                severity="HIGH", rule_id="R", created_at=0)
    assert pdl.red_blocks([Alert(**base)], pdl.RED_BLOCK_MS - 1)
    assert not pdl.red_blocks([Alert(**base)], pdl.RED_BLOCK_MS)
    assert not pdl.red_blocks([Alert(**base, escalated_at=5_000)], pdl.RED_BLOCK_MS)  # D-177
    assert not pdl.red_blocks([Alert(**{**base, "severity": "MEDIUM"})], 1)
    assert not pdl.red_blocks([Alert(**{**base, "status": "corrected"})], 1)


class SlowTimeout:
    """The AI PD model when its call runs out: 2.5 s pass on the show clock, then no choice."""

    def __init__(self, clock):
        self.clock, self.calls = clock, 0

    async def choose(self, state, candidates, deadline_ms):
        self.calls += 1
        self.clock.advance(2_500)
        return None, 2_500, "timeout"


async def test_a_due_question_card_does_not_wait_for_the_model(env):
    """D-163 (local SEED1 replay on HEAD): how-to-use waited 285 s with a verified draft. Due at a break (2 s after
    a final), it went to the model, which timed out after ~2.1 s; the re-check then found the break over and dropped
    the card, and the unchanged candidate key never decided it again. A due question is decided by the rules at once."""
    rt, _ = env
    rt.pd.agent = SlowTimeout(rt.ctx.clock)
    await speak(rt, "Welcome everyone, today we start with the cream.")
    await say(rt, "Mei", "Is the cream okay for oily skin?")
    [g] = await rt.groups()
    assert g.route == "HOST" and g.status == "ready"
    for _ in range(30):  # 120 s of talking, never an 8 s pause
        await rt.ctx.scheduler.advance(4000)
        await speak(rt, "Look at the texture, it is so light on the skin.")
        card = (await rt.load_session()).pd_card
        if card is not None:
            break
    assert card is not None and card.ref_id == g.group_id
