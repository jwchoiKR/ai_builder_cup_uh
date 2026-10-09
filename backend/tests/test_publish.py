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

from app.config import get_settings as _settings  # noqa: E402
from app.logic.catalog import DataPack as _DataPack  # noqa: E402

LEX = _DataPack.load(_settings().data_path).lexicon  # D-134: English (SG) lexicon


ANSWER = "Raj is asking if it's OK for oily skin. Yes, it's a lightweight gel-cream, so just use a smaller amount on oily areas."


# ---- pure decide() ------------------------------------------------------------------------------


def jo(**kw) -> UtteranceJudgeOutput:
    base = dict(utterance_type="answer", matched="g1", is_answer=True, consistent=True)
    return UtteranceJudgeOutput.model_validate(judge_output(**{**base, **kw}))


def grp(**kw) -> QuestionGroup:
    base = dict(group_id="g1", product_id=CREAM, intent="suitability", condition_slots={},
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
    d = decide(jo(), OFFERED, grp(), ans(), lex=LEX, high_alert_active=False, facts=facts())
    assert (d.action, d.group_id) == ("post", "g1")


def test_fact_timeout_does_not_block():
    assert decide(jo(), OFFERED, grp(), ans(), lex=LEX, high_alert_active=False, facts=None).action == "post"


def test_condition_1_answer_to_offered_question():
    assert decide(jo(is_answer=False), OFFERED, grp(), ans(), lex=LEX, high_alert_active=False, facts=None).action == "none"
    assert decide(jo(), {}, grp(), ans(), lex=LEX, high_alert_active=False, facts=None).action == "none"
    assert decide(jo(matched=None), OFFERED, grp(), ans(), lex=LEX, high_alert_active=False, facts=None).action == "none"
    assert decide(jo(), OFFERED, None, ans(), lex=LEX, high_alert_active=False, facts=None).action == "none"


def test_condition_2_inconsistent_is_verbal():
    assert decide(jo(consistent=False), OFFERED, grp(), ans(), lex=LEX, high_alert_active=False, facts=None).action == "verbal_not_posted"


@pytest.mark.parametrize("group, answer", [
    (grp(), None),
    (grp(), ans(verified=False)),
    (grp(route="OPERATOR"), ans()),
])
def test_condition_3_verified_answer_and_not_operator(group, answer):
    assert decide(jo(), OFFERED, group, answer, lex=LEX, high_alert_active=False, facts=None).action == "verbal_not_posted"


# ---- D-110: stricter spoken-answer posting ---------------------------------------------------------


def test_bound_to_the_answer_shown_and_the_current_state():
    shown_older = {"g1": ans().model_copy(update={"answer_id": "a0"})}
    d = decide(jo(), shown_older, grp(), ans(), lex=LEX, high_alert_active=False, facts=None)
    assert (d.action, d.reason) == ("verbal_not_posted", "stale answer")
    keyed = ans().model_copy(update={"cache_key": "k_old"})
    d = decide(jo(), {"g1": keyed}, grp(), keyed, lex=LEX, high_alert_active=False, facts=None, current_key="k_new")
    assert (d.action, d.reason) == ("verbal_not_posted", "stale answer")
    assert decide(jo(), {"g1": keyed}, grp(), keyed, lex=LEX, high_alert_active=False, facts=None,
                  current_key="k_old").action == "post"


@pytest.mark.parametrize("kind", ["question_readout", "product_talk", "other"])
def test_only_an_answer_utterance_posts(kind):
    assert decide(jo(utterance_type=kind), OFFERED, grp(), ans(), lex=LEX, high_alert_active=False,
                  facts=None).action == "verbal_not_posted"


def test_hedge_or_new_number_holds_the_post_even_when_the_judge_says_consistent():
    draft = ans().model_copy(update={"text": "It is 50 mL."})
    offered = {"g1": draft}
    for said, reason in [("I think it's 50 mL.", "host sounded unsure or took it back"),
                         ("It's forty mils.", "a number differs from the verified draft")]:
        d = decide(jo(), offered, grp(), draft, lex=LEX, high_alert_active=False, facts=None, utterance=said)
        assert (d.action, d.reason) == ("verbal_not_posted", reason)
    assert decide(jo(), offered, grp(), draft, lex=LEX, high_alert_active=False, facts=CHECKED,
                  utterance="Fifty mils in this jar.").action == "post"


CHECKED = FactCheckOutput(claims=[], reason="")


def test_d195_a_number_line_without_a_completed_fact_check_is_not_posted():
    """A fact check that timed out or failed (facts=None) never lets a line that states a number post."""
    draft = ans().model_copy(update={"text": "It is S$36.00 today."})
    kw = dict(lex=LEX, high_alert_active=False, utterance="It's thirty-six dollars today.")
    d = decide(jo(), {"g1": draft}, grp(), draft, facts=None, **kw)
    assert (d.action, d.reason) == ("verbal_not_posted", "check incomplete")
    assert decide(jo(), {"g1": draft}, grp(), draft, facts=CHECKED, **kw).action == "post"
    plain = ans().model_copy(update={"text": "Yes."})  # no number said: nothing for the fact check to confirm
    assert decide(jo(), {"g1": plain}, grp(), plain, facts=None, lex=LEX, high_alert_active=False,
                  utterance="Yes, it is.").action == "post"


def test_d195_another_offered_draft_never_accepts_a_number():
    """Two drafts open: the cream's answer said with the ampoule's price is held, not accepted via the other draft."""
    cream = ans().model_copy(update={"text": "The cream is S$36.00 today."})
    ampoule = ans().model_copy(update={"answer_id": "a2", "group_id": "g2", "text": "The ampoule is S$32.00 today."})
    offered = {"g1": cream, "g2": ampoule}
    d = decide(jo(), offered, grp(), cream, facts=CHECKED, lex=LEX, high_alert_active=False,
               utterance="The cream is thirty-two dollars today.")
    assert (d.action, d.reason) == ("verbal_not_posted", "a number differs from the verified draft")


def _verbal_cases() -> list[dict]:
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "data" / "eval"
    return [json.loads(line) for name in ("verbal_post_cases.jsonl", "verbal_post_holdout.jsonl")
            for line in (root / name).read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.mark.parametrize("said, numbers", [
    ("zero point two percent", {"0.2"}),
    ("between five point five and six point zero", {"5.5", "6"}),
    ("pH 5.5 to 6.0", {"5.5", "6"}),
    ("fifty mils, thirty-six dollars", {"50", "36"}),
])
def test_spoken_numbers_include_spoken_decimals(said, numbers):

    assert LEX.spoken_numbers(said) == numbers


@pytest.mark.parametrize("case", _verbal_cases(), ids=lambda c: c["case_id"])
def test_code_checks_on_the_verbal_post_cases(case):
    """The code layer alone: it never blocks an expected post, and it blocks every wrong number,
    hedge and retraction (the other near-misses are the judge's job)."""
    from app.logic.publish import verbal_check

    qs = {q["group_id"]: q["suggested_answer"] for q in case["context"]["open_questions"]}
    # D-195: the numbers are checked against the draft of the group the line answers, not the one on screen
    shown = case["expected"].get("matched_group") or case["shown_group_id"]
    if shown not in qs:
        return  # other_group: no draft shown for this question
    # D-196: a line answering two shown questions is linked to both, so the other draft's numbers count
    linked = [a for g, a in qs.items() if g != shown] if case["case_id"] in ("V14", "V46") else []
    held = verbal_check(case["utterance"], qs[shown], LEX, linked)
    exp = case["expected"]
    if exp["post"]:
        assert held is None, held
    elif exp["category"] in ("wrong_number", "hedge", "retracted"):
        assert held is not None


def test_condition_4_compliance():
    assert decide(jo(), OFFERED, grp(), ans(), lex=LEX, high_alert_active=True, facts=None).action == "none"
    with_violation = jo(violations=[violation("ASEAN-3-SKIN-AGEING")])
    assert decide(with_violation, OFFERED, grp(), ans(), lex=LEX, high_alert_active=False, facts=None).action == "none"
    negated = jo(violations=[violation("ASEAN-3-SKIN-ACNE", negated=True)])
    assert decide(negated, OFFERED, grp(), ans(), lex=LEX, high_alert_active=False, facts=None).action == "post"


def test_condition_5_contradicted_fact():
    f = facts(price_contradiction())
    assert decide(jo(), OFFERED, grp(), ans(), lex=LEX, high_alert_active=False, facts=f).action == "none"
    ok = facts(claim("texture", "supported"))
    assert decide(jo(), OFFERED, grp(), ans(), lex=LEX, high_alert_active=False, facts=ok).action == "post"


@pytest.mark.parametrize("group", [grp(published_message_id="m1"), grp(status="answered")])
def test_condition_6_no_published_answer_yet(group):
    assert decide(jo(), OFFERED, group, ans(), lex=LEX, high_alert_active=False, facts=None).action == "verbal_not_posted"


def test_ai_answered_group_is_confirmed():
    g = grp(status="auto_answered", route="AUTO", published_message_id="m1")
    assert decide(jo(), OFFERED, g, ans(), lex=LEX, high_alert_active=False, facts=None).action == "confirm_ai"
    assert decide(jo(consistent=False), OFFERED, g, ans(), lex=LEX, high_alert_active=False, facts=None).action == "verbal_not_posted"


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
    answer_script(llm, g.group_id, violations=[violation("ASEAN-3-SKIN-AGEING")])  # D-434: a cited section
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


@pytest.mark.parametrize("change", ["closed", "new_answer"])
async def test_a_pending_host_answer_is_dropped_when_its_question_changes(env, change):
    """Review B4 (D-117): the 2 s cancel window must not post a reply whose question was closed (e.g. a
    price question closed by a time sale) or whose answer changed meanwhile."""
    rt, llm = env
    g = await oily_on_host(rt)
    answer_script(llm, g.group_id)
    await speak(rt, ANSWER)
    [m] = await messages(rt, "host_answer")
    assert m.state == "pending"
    g = await rt.get_group(g.group_id)
    if change == "closed":
        g.status = "closed"
    else:
        g.answer_id = "ans_other"
    await rt.save_group(g)
    await advance(rt, 2000)
    [m] = await messages(rt, "host_answer")
    assert m.state == "cancelled" and await events(rt, "message.cancelled")
    assert (await rt.get_group(g.group_id)).status != "answered"


async def _relink_env(env, line: str):
    """D-175: the context judge links `line` to nothing at first; asked about the one question again, it links it."""
    from .judge_fakes import judge_output as jout

    rt, llm = env
    g = await oily_on_host(rt)
    ans = await rt.get_answer(g.answer_id)
    ans.text = draft = "Yes. It has a lightweight gel-cream texture, so use a smaller amount on oily areas."  # the FAQ
    await rt.save_answer(ans)
    llm.judge(line, utterance_type="product_talk")
    calls = []
    generate = llm.generate

    async def second_links(req, timeout_ms):
        if req.agent == "context_judge":
            calls.append(req.user_message)
            if len(calls) == 2:
                llm.outputs[("utterance_judge", line)] = jout(utterance_type="answer", matched=g.group_id,
                                                              is_answer=True, consistent=True)
        return await generate(req, timeout_ms)
    llm.generate = second_links
    await speak(rt, line)
    await advance(rt, 2000)
    return rt, g, draft, calls


async def test_d175_a_line_the_judge_did_not_link_is_asked_about_its_one_question_again(env):
    rt, g, draft, calls = await _relink_env(env, "Raj, yes: " + "lightweight gel-cream texture, use a smaller amount on oily areas.")
    assert len(calls) == 2 and calls[1].count('"group_id"') == 1  # the second call offers that one question
    [m] = await messages(rt, "host_answer")
    assert m.state == "published" and (await rt.get_group(g.group_id)).status == "answered"


async def test_d175_a_line_with_another_number_is_not_asked_again(env):
    rt, g, draft, calls = await _relink_env(env, "Raj, yes: lightweight gel-cream texture, use 3 pumps on oily areas.")
    assert len(calls) == 1 and await messages(rt, "host_answer") == []


async def test_d175_a_context_timeout_is_asked_again_about_the_one_question(env):
    """D-175 (verbal eval: every remaining miss was a context-judge timeout): the line is still published when the
    second call links it, and compliance still decides."""
    from app.providers.llm import LLMTimeout

    from .judge_fakes import judge_output as jout

    rt, llm = env
    g = await oily_on_host(rt)
    ans = await rt.get_answer(g.answer_id)
    ans.text = "Yes. It has a lightweight gel-cream texture, so use a smaller amount on oily areas."
    await rt.save_answer(ans)
    line = "Raj, yes: lightweight gel-cream texture, use a smaller amount on oily areas."
    llm.outputs[("utterance_judge", line)] = jout(utterance_type="answer", matched=g.group_id, is_answer=True,
                                                  consistent=True)
    calls = []
    generate = llm.generate

    async def first_times_out(req, timeout_ms):
        if req.agent == "context_judge":
            calls.append(req.user_message)
            if len(calls) == 1:
                raise LLMTimeout("deadline")
        return await generate(req, timeout_ms)
    llm.generate = first_times_out
    await speak(rt, line)
    await advance(rt, 2000)
    assert len(calls) == 2
    [m] = await messages(rt, "host_answer")
    assert m.state == "published"


# ---- D-196: one sentence, several shown questions -----------------------------------------------------------------


def _two(utterance: str, also: list[str]):
    size = ans().model_copy(update={"text": "It is 50 mL."})
    amp = ans().model_copy(update={"answer_id": "a2", "group_id": "g2", "text": "It is 30 mL."})
    offered = {"g1": size, "g2": amp}
    j = jo()
    j.answer.also_answered_group_ids = also
    kw = dict(lex=LEX, high_alert_active=False, facts=CHECKED, utterance=utterance)
    first = decide(j, offered, grp(), size, **kw)
    second = None
    if also:
        j2 = j.model_copy(deep=True)
        j2.answer.matched_group_id, j2.answer.also_answered_group_ids = "g2", ["g1"]
        second = decide(j2, offered, grp(group_id="g2", answer_id="a2"), amp, **kw)
    return first, second


def test_d196_a_line_answering_two_linked_questions_posts_each():
    first, second = _two("The ampoule is 30 mL and the cream is 50 mL.", ["g2"])
    assert first.action == "post" and second.action == "post"


def test_d196_without_the_second_link_the_other_number_is_held():
    first, _ = _two("The ampoule is 30 mL and the cream is 50 mL.", [])
    assert (first.action, first.reason) == ("verbal_not_posted", "a number differs from the verified draft")


def test_d196_a_linked_draft_whose_number_was_not_said_is_held():
    """Linked to both, but the line only states the ampoule's 30: the cream's draft (50) is not posted."""
    first, second = _two("The ampoule is 30 mL.", ["g2"])
    assert (first.action, first.reason) == ("verbal_not_posted", "a number of this draft was not said")
    assert second.action == "post"


@pytest.mark.parametrize("linked_both", [True, False])
async def test_d196_the_pipeline_posts_every_group_one_line_answers(env, linked_both):
    rt, llm = env
    g1 = await oily_on_host(rt)
    await say(rt, "Mia", "Can I use it while pregnant?")
    g2 = next(g for g in await rt.groups() if g.group_id != g1.group_id)
    assert g2.status == "ready"
    line = "Yes, it's a lightweight gel-cream, so use a smaller amount on oily areas, and please ask your doctor first if you are pregnant."
    out = judge_output(utterance_type="answer", matched=g1.group_id, is_answer=True, consistent=True)
    out["answer"]["also_answered_group_ids"] = [g2.group_id] if linked_both else []
    llm.outputs[("utterance_judge", line)] = out
    await speak(rt, line)
    await rt.ctx.scheduler.advance(2000)
    posted = await messages(rt, "host_answer")
    expected = (g1.group_id, g2.group_id) if linked_both else (g1.group_id,)
    assert sorted(m.idempotency_key for m in posted) == sorted(f"host_answer:{g}" for g in expected)


class _FactsFailOnce(__import__("tests.judge_fakes", fromlist=["ScriptedBackend"]).ScriptedBackend):
    def __init__(self):
        super().__init__()
        self.failed: set[str] = set()

    async def generate(self, req, timeout_ms):
        if req.agent == "fact_checker" and req.mock_primary_text not in self.failed:
            self.failed.add(req.mock_primary_text)
            self.calls.append((req.agent, req.mock_primary_text))
            from app.providers.llm import LLMError
            raise LLMError("scripted failure")
        return await super().generate(req, timeout_ms)


# D-388 (user): a failed fact call is retried for every line, not only a line with a number
@pytest.mark.parametrize("line, calls", [("It's thirty-six dollars today.", 2), ("It feels so light.", 2)])
async def test_d203_a_failed_fact_check_on_a_number_line_runs_once_more(line, calls):
    from .helpers import live_runtime, make_ctx

    backend = _FactsFailOnce()
    backend.facts(line)
    rt = await live_runtime(make_ctx(backend=backend))
    try:
        await speak(rt, line)
        assert [a for a, _ in backend.calls].count("fact_checker") == calls
    finally:
        await close_env(rt)


async def test_d204_a_red_alert_in_the_cancel_window_stops_the_post(env):
    rt, llm = env
    g = await oily_on_host(rt)
    answer_script(llm, g.group_id)
    await speak(rt, ANSWER)
    [m] = await messages(rt, "host_answer")
    assert m.state == "pending"
    line = "And honestly this cream cures eczema."
    llm.judge(line, violations=[violation("ASEAN-2D-DISEASE", "cures eczema")])
    await speak(rt, line)
    await rt.ctx.scheduler.advance(2000)
    [m] = await messages(rt, "host_answer")
    assert m.state == "cancelled"
