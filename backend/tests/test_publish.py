"""Host spoken answer -> publish decision (DEV_SPEC §8.6, §14.1 publish)."""
from __future__ import annotations

import pytest

from app.logic.publish import decide
from app.models.agent_io import FactCheckOutput, UtteranceJudgeOutput
from app.models.session import Answer, Message, QuestionGroup
from app.pipelines import comments as ops
from app.pipelines import utterances as utt
from app.pipelines.runtime import ActionError

from .helpers import say
from .judge_fakes import CREAM, advance, claim, close_env, events, judge_output, make_env, price_contradiction, speak, violation

ANSWER = "Raj is asking if it's OK for oily skin. Yes, it's a lightweight gel-cream, so just use a smaller amount on oily areas."


# ---- pure decide() ------------------------------------------------------------------------------


def jo(**kw) -> UtteranceJudgeOutput:
    base = dict(utterance_type="answer", matched="g1", is_answer=True, consistent=True)
    return UtteranceJudgeOutput.model_validate(judge_output(**{**base, **kw}))


def grp(**kw) -> QuestionGroup:
    base = dict(group_id="g1", product_id=CREAM, intent="skin_type_suitability", condition_slots={},
                canonical_question="Is it suitable for oily skin?", member_comment_ids=["c1"], unique_author_ids=["u1"],
                first_at=0, last_at=0, route="HOST", route_reason="intent", status="ready", answer_id="a1")
    return QuestionGroup(**{**base, **kw})


def ans(verified=True) -> Answer:
    return Answer(answer_id="a1", group_id="g1", text="Yes.", citations=[], origin="ai", verified=verified,
                  verify_errors=[], needs_human=False, created_at=0)


def facts(*claims) -> FactCheckOutput:
    return FactCheckOutput.model_validate({"claims": list(claims), "reason": ""})


OFFERED = {"g1": ans()}  # the verified answer shown with the question


def test_all_conditions_hold_posts():
    d = decide(jo(), OFFERED, grp(), ans(), high_alert_active=False, facts=facts())
    assert (d.action, d.group_id) == ("post", "g1")


def test_fact_timeout_does_not_block():
    assert decide(jo(), OFFERED, grp(), ans(), high_alert_active=False, facts=None).action == "post"


def test_condition_1_answer_to_offered_question():
    assert decide(jo(is_answer=False), OFFERED, grp(), ans(), high_alert_active=False, facts=None).action == "none"
    assert decide(jo(), {}, grp(), ans(), high_alert_active=False, facts=None).action == "none"
    assert decide(jo(matched=None), OFFERED, grp(), ans(), high_alert_active=False, facts=None).action == "none"
    assert decide(jo(), OFFERED, None, ans(), high_alert_active=False, facts=None).action == "none"


def test_condition_2_inconsistent_is_verbal():
    assert decide(jo(consistent=False), OFFERED, grp(), ans(), high_alert_active=False, facts=None).action == "verbal_not_posted"


@pytest.mark.parametrize("group, answer", [
    (grp(), None),
    (grp(), ans(verified=False)),
    (grp(route="OPERATOR"), ans()),
])
def test_condition_3_verified_answer_and_not_operator(group, answer):
    assert decide(jo(), OFFERED, group, answer, high_alert_active=False, facts=None).action == "verbal_not_posted"


# ---- D-110: stricter spoken-answer posting ---------------------------------------------------------


def test_bound_to_the_answer_shown_and_the_current_state():
    shown_older = {"g1": ans().model_copy(update={"answer_id": "a0"})}
    d = decide(jo(), shown_older, grp(), ans(), high_alert_active=False, facts=None)
    assert (d.action, d.reason) == ("verbal_not_posted", "stale answer")
    keyed = ans().model_copy(update={"cache_key": "k_old"})
    d = decide(jo(), {"g1": keyed}, grp(), keyed, high_alert_active=False, facts=None, current_key="k_new")
    assert (d.action, d.reason) == ("verbal_not_posted", "stale answer")
    assert decide(jo(), {"g1": keyed}, grp(), keyed, high_alert_active=False, facts=None,
                  current_key="k_old").action == "post"


@pytest.mark.parametrize("kind", ["question_readout", "product_talk", "other"])
def test_only_an_answer_utterance_posts(kind):
    assert decide(jo(utterance_type=kind), OFFERED, grp(), ans(), high_alert_active=False,
                  facts=None).action == "verbal_not_posted"


def test_hedge_or_new_number_holds_the_post_even_when_the_judge_says_consistent():
    draft = ans().model_copy(update={"text": "It is 50 mL."})
    offered = {"g1": draft}
    for said, reason in [("I think it's 50 mL.", "host sounded unsure or took it back"),
                         ("It's forty mils.", "a number differs from the verified draft")]:
        d = decide(jo(), offered, grp(), draft, high_alert_active=False, facts=None, utterance=said)
        assert (d.action, d.reason) == ("verbal_not_posted", reason)
    assert decide(jo(), offered, grp(), draft, high_alert_active=False, facts=None,
                  utterance="Fifty mils in this jar.").action == "post"


def _verbal_cases() -> list[dict]:
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "data" / "eval" / "verbal_post_cases.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.mark.parametrize("case", _verbal_cases(), ids=lambda c: c["case_id"])
def test_code_checks_on_the_verbal_post_cases(case):
    """The code layer alone: it never blocks an expected post, and it blocks every wrong number,
    hedge and retraction (the other near-misses are the judge's job)."""
    from app.logic.publish import verbal_check

    qs = {q["group_id"]: q["suggested_answer"] for q in case["context"]["open_questions"]}
    shown = case["shown_group_id"]
    if shown not in qs:
        return  # other_group: no draft shown for this question
    held = verbal_check(case["utterance"], qs[shown], [a for g, a in qs.items() if g != shown])
    exp = case["expected"]
    if exp["post"]:
        assert held is None, held
    elif exp["category"] in ("wrong_number", "hedge", "retracted"):
        assert held is not None


def test_condition_4_compliance():
    assert decide(jo(), OFFERED, grp(), ans(), high_alert_active=True, facts=None).action == "none"
    with_violation = jo(violations=[violation("ASEAN-3-SKIN-AGEING")])
    assert decide(with_violation, OFFERED, grp(), ans(), high_alert_active=False, facts=None).action == "none"
    negated = jo(violations=[violation("ASEAN-3-SKIN-ACNE", negated=True)])
    assert decide(negated, OFFERED, grp(), ans(), high_alert_active=False, facts=None).action == "post"


def test_condition_5_contradicted_fact():
    f = facts(price_contradiction())
    assert decide(jo(), OFFERED, grp(), ans(), high_alert_active=False, facts=f).action == "none"
    ok = facts(claim("texture", "supported"))
    assert decide(jo(), OFFERED, grp(), ans(), high_alert_active=False, facts=ok).action == "post"


@pytest.mark.parametrize("group", [grp(published_message_id="m1"), grp(status="answered")])
def test_condition_6_no_published_answer_yet(group):
    assert decide(jo(), OFFERED, group, ans(), high_alert_active=False, facts=None).action == "verbal_not_posted"


def test_ai_answered_group_is_confirmed():
    g = grp(status="auto_answered", route="AUTO", published_message_id="m1")
    assert decide(jo(), OFFERED, g, ans(), high_alert_active=False, facts=None).action == "confirm_ai"
    assert decide(jo(consistent=False), OFFERED, g, ans(), high_alert_active=False, facts=None).action == "verbal_not_posted"


# ---- pipeline ----------------------------------------------------------------------------------


@pytest.fixture
async def env():
    rt, llm = await make_env()
    yield rt, llm
    await close_env(rt)


async def oily_on_host(rt) -> QuestionGroup:
    await say(rt, "Raj", "Is it OK for oily skin?")
    [g] = await rt.groups()
    assert g.status == "ready" and [s.group_id for s in (await rt.load_session()).host_slots] == [g.group_id]
    return g


async def messages(rt, kind=None) -> list[Message]:
    ms = await rt.ctx.store.query(rt.path("messages"), Message, order_by="created_at")
    return [m for m in ms if kind is None or m.kind == kind]


def answer_script(llm, gid, text=ANSWER, **kw):
    llm.judge(text, utterance_type="answer", matched=gid, is_answer=True, consistent=True, **kw)


async def test_pending_then_published_after_window(env):
    rt, llm = env
    g = await oily_on_host(rt)
    answer_script(llm, g.group_id)
    await speak(rt, ANSWER)
    [m] = await messages(rt, "host_answer")
    assert m.state == "pending" and m.publish_at == m.created_at + 2000 and m.idempotency_key == f"host_answer:{g.group_id}"
    assert m.reply_to_author_names == ["Raj"] and (await events(rt, "message.pending"))
    assert [s.group_id for s in (await rt.load_session()).host_slots] == [g.group_id]  # still on host while pending
    await advance(rt, 1999)
    assert (await messages(rt, "host_answer"))[0].state == "pending"
    await advance(rt, 1)
    [m] = await messages(rt, "host_answer")
    g = await rt.get_group(g.group_id)
    assert m.state == "published" and m.published_at is not None
    assert g.status == "answered" and g.published_message_id == m.message_id and g.host_slot == "none"
    assert (await rt.load_session()).host_slots == []
    assert await events(rt, "message.published")


async def test_cancel_within_window(env):
    rt, llm = env
    g = await oily_on_host(rt)
    answer_script(llm, g.group_id)
    await speak(rt, ANSWER)
    [m] = await messages(rt, "host_answer")
    await advance(rt, 1000)
    await utt.cancel_message(rt, m.message_id)
    await advance(rt, 5000)
    [m] = await messages(rt, "host_answer")
    assert m.state == "cancelled" and (await rt.get_group(g.group_id)).status == "ready"
    assert await events(rt, "message.cancelled")
    with pytest.raises(ActionError) as e:
        await utt.cancel_message(rt, m.message_id)
    assert e.value.status == 409


async def test_idempotent_host_answer(env):
    rt, _ = env
    g = await oily_on_host(rt)
    answer = await rt.get_answer(g.answer_id)
    async with rt.lock:
        m1 = await utt.post_host_answer_locked(rt, g, answer)
        m2 = await utt.post_host_answer_locked(rt, g, answer)
    assert m1.message_id == m2.message_id and len(await messages(rt, "host_answer")) == 1


async def test_blocked_by_active_high_alert(env):
    rt, llm = env
    g = await oily_on_host(rt)
    bad = "It kills the bacteria on your skin."
    llm.judge(bad, violations=[violation("ASEAN-3-SKIN-ANTIMICROBIAL")])
    await speak(rt, bad)
    answer_script(llm, g.group_id)
    await speak(rt, ANSWER)
    await advance(rt, 3000)
    assert await messages(rt, "host_answer") == []
    g = await rt.get_group(g.group_id)
    assert g.status == "ready" and g.host_verbal_answer_transcript_id is None


async def test_blocked_by_violation_in_the_answer(env):
    rt, llm = env
    g = await oily_on_host(rt)
    answer_script(llm, g.group_id, violations=[violation("BRAND-SUPERLATIVE", severity="MEDIUM")])
    await speak(rt, ANSWER)
    await advance(rt, 3000)
    assert await messages(rt, "host_answer") == []


async def test_blocked_by_contradicted_fact(env):
    rt, llm = env
    g = await oily_on_host(rt)
    answer_script(llm, g.group_id)
    llm.facts(ANSWER, price_contradiction())
    await speak(rt, ANSWER)
    await advance(rt, 3000)
    assert await messages(rt, "host_answer") == []


async def test_not_an_answer_or_unknown_group_does_nothing(env):
    rt, llm = env
    g = await oily_on_host(rt)
    llm.judge("Someone is asking about oily skin, I'll get to that.", utterance_type="question_readout",
              matched=g.group_id, is_answer=False)
    await speak(rt, "Someone is asking about oily skin, I'll get to that.")
    answer_script(llm, "grp_999999", text="Yes it is fine.")
    await speak(rt, "Yes it is fine.")
    g = await rt.get_group(g.group_id)
    assert g.status == "ready" and g.host_slot == "on_host" and await messages(rt, "host_answer") == []


async def test_inconsistent_answer_is_verbal_not_posted(env):
    rt, llm = env
    g = await oily_on_host(rt)
    llm.judge(ANSWER, utterance_type="answer", matched=g.group_id, is_answer=True, consistent=False)
    t = await speak(rt, ANSWER)
    g = await rt.get_group(g.group_id)
    assert g.host_verbal_answer_transcript_id == t.transcript_id and g.host_slot == "none"
    assert (await rt.load_session()).host_slots == [] and await messages(rt, "host_answer") == []
    await ops.post_suggested(rt, g.group_id)  # operator: "Post suggested answer"
    [m] = await messages(rt, "host_answer")
    assert m.state == "published" and (await rt.get_group(g.group_id)).status == "answered"


async def test_operator_routed_group_is_never_posted_from_speech(env):
    rt, llm = env
    await say(rt, "Jun", "Can I use it while pregnant?")
    [g] = await rt.groups()
    assert g.route == "HOST" and (await rt.get_answer(g.answer_id)).verified  # D-113: sensitive goes to the host
    g.route = "OPERATOR"  # a general question the operator handles (team show)
    await rt.save_group(g)
    await ops.push_to_host(rt, g.group_id)
    text = "It hasn't been tested on pregnant women, please ask your doctor."
    answer_script(llm, g.group_id, text=text)
    t = await speak(rt, text)
    await advance(rt, 3000)
    g = await rt.get_group(g.group_id)
    assert await messages(rt, "host_answer") == [] and g.host_verbal_answer_transcript_id == t.transcript_id
    assert (await rt.load_session()).host_slots == []


async def test_ai_answered_group_is_confirmed_not_reposted(env):
    rt, llm = env
    await say(rt, "Lee", "How much is the cream?")
    [g] = await rt.groups()
    assert g.status == "auto_answered"
    text = "It's thirty-six dollars today."
    answer_script(llm, g.group_id, text=text)
    await speak(rt, text)
    await advance(rt, 3000)
    g = await rt.get_group(g.group_id)
    assert g.host_confirmed and g.status == "auto_answered"
    assert [m.kind for m in await messages(rt)] == ["ai_answer"]
