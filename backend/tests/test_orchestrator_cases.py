"""The utterance orchestrator (UtterancePipeline) on 10 cases: one final transcript in, the right
branch out (compliance alert, correction, fact note, prompter, host answer, product switch).

The agents are scripted (ScriptedBackend), so these tests check the orchestrator's branching, not the
models. Tricky sentences with the real agents on Vertex AI: `scripts/eval_orchestrator.py`
(docs/eval/orchestrator-cases.md).
"""
from __future__ import annotations

import pytest

from app.models.session import Message

from .judge_fakes import (rid, AMPOULE, CREAM, PRICE_PASSAGE, PRICE_QUOTE, advance, claim, close_env, events, make_env,
                          price_contradiction, speak, violation)
from .test_publish import oily_on_host

PROMPTER = "It's a lightweight gel-cream, so it absorbs really quickly."
WRINKLES = "Use it every night and your wrinkles will disappear overnight."
SAY = "Helps keep skin hydrated for up to 24 hours in our in-house test."  # D-209: approved wording, not the model's
APOLOGY = "Oh, I'm sorry."
FIX = "Let me correct that. It helps keep your skin hydrated for up to twenty-four hours in our in-house test."
NEGATED = "Just to be clear, it does not treat acne. It's a moisturiser."
QUOTED = "Someone asked if it cures eczema. No, it's a cosmetic, it doesn't treat any skin condition."
WRONG = "And today the live price is only thirty-two dollars."
RIGHT = "Sorry, my mistake, the live price is thirty-six dollars."
ANSWER = "Raj is asking if it's OK for oily skin. Yes, it's a lightweight gel-cream, so just use a smaller amount on oily areas."
INTRO = "Okay, now let me show you our Deep Hydration Ampoule. It has four percent niacinamide."
INFO = "It's a watery gel, just two to three drops after toner."
GAP_MS = 4000  # between lines: separate sentences, never merged


@pytest.fixture
async def env():
    rt, llm = await make_env()
    yield rt, llm
    await close_env(rt)


async def compliance(rt):
    return [a for a in await rt.alerts() if a.kind == "compliance"]


async def facts(rt):
    return [a for a in await rt.alerts() if a.kind == "fact"]


async def host_answers(rt):
    return [m for m in await rt.ctx.store.query(rt.path("messages"), Message) if m.kind == "host_answer"]


async def violate(rt, llm):
    llm.judge(WRINKLES, violations=[violation("ASEAN-3-SKIN-AGEING", "your wrinkles will disappear overnight", say=SAY)])
    await speak(rt, WRINKLES)
    [a] = [x for x in await compliance(rt) if x.status == "active"]
    return a


# ---- the 10 cases ---------------------------------------------------------------------------------


async def case_01_prompter_point(rt, llm):
    """Ordinary product talk: only the prompter branch fires."""
    llm.judge(PROMPTER, covered=["cr-p1"])
    await speak(rt, PROMPTER)
    assert "cr-p1" in (await rt.current_segment()).covered_point_ids
    assert await rt.alerts() == [] and await host_answers(rt) == []


async def case_02_compliance_violation(rt, llm):
    """A HIGH claim: the judge raises it, the host gets the red alert (D-410: no reflex mark first)."""
    a = await violate(rt, llm)
    assert (a.rule_id, a.severity, a.say_instead) == (rid("ASEAN-3-SKIN-AGEING"), "HIGH", SAY)
    assert a.shown_at is not None
    await advance(rt, 5000)
    assert (await rt.get_alert(a.alert_id)).escalated_at is not None  # not corrected in 5 s


async def case_03_the_judge_decides_a_correction(rt, llm):
    """D-390: the judge lists the alert as corrected; its verdict is applied as given (D-089's word check is gone)."""
    a = await violate(rt, llm)
    await advance(rt, GAP_MS)
    llm.judge(APOLOGY, corrects=[a.alert_id], utterance_type="correction")
    await speak(rt, APOLOGY)
    assert (await rt.get_alert(a.alert_id)).status == "corrected"


async def case_04_correction(rt, llm):
    """The approved wording after the alert corrects it."""
    a = await violate(rt, llm)
    await advance(rt, GAP_MS)
    llm.judge(FIX, corrects=[a.alert_id], utterance_type="correction")
    t = await speak(rt, FIX)
    a = await rt.get_alert(a.alert_id)
    assert a.status == "corrected" and a.corrected_by_transcript_id == t.transcript_id


async def case_05_negated_claim(rt, llm):
    """A negated claim: the judge marks it negated, nothing reaches the host."""
    llm.judge(NEGATED, violations=[violation("ASEAN-3-SKIN-ACNE", "treat acne", negated=True)])
    await speak(rt, NEGATED)
    assert await compliance(rt) == []


async def case_06_quoted_claim(rt, llm):
    """A viewer's question read out: quoted, so no alert."""
    llm.judge(QUOTED, violations=[violation("ASEAN-2D-DISEASE", "cures eczema", quoted=True)])
    await speak(rt, QUOTED)
    assert not [a for a in await compliance(rt) if a.status == "active"]


async def case_07_wrong_fact(rt, llm):
    """A wrong price: only the fact branch fires (amber note with the sheet value)."""
    llm.facts(WRONG, price_contradiction("S$32"))
    await speak(rt, WRONG)
    [note] = await facts(rt)
    assert (note.status, note.field, note.stated_value, note.correct_value) == ("active", "price", "S$32", "S$36.00")
    assert await compliance(rt) == []


async def case_08_fact_corrected(rt, llm):
    """The host states the right price: the note is corrected."""
    llm.facts(WRONG, price_contradiction("S$32"))
    await speak(rt, WRONG)
    await advance(rt, GAP_MS)
    llm.facts(RIGHT, claim("price", "supported", stated="S$36.00", passage_id=PRICE_PASSAGE, quote=PRICE_QUOTE),
              fixed=["F1"])
    t = await speak(rt, RIGHT)
    [note] = await facts(rt)
    assert note.status == "corrected" and note.corrected_by_transcript_id == t.transcript_id


async def case_09_host_answer_published(rt, llm):
    """The host answers a question on screen, consistent with the suggested answer: posted after 2 s."""
    g = await oily_on_host(rt)
    llm.judge(ANSWER, utterance_type="answer", matched=g.group_id, is_answer=True, consistent=True)
    await speak(rt, ANSWER)
    [m] = await host_answers(rt)
    assert m.state == "pending" and m.reply_to_author_names == ["Raj"]
    await advance(rt, 2000)
    [m] = await host_answers(rt)
    assert m.state == "published" and (await rt.get_group(g.group_id)).status == "answered"


async def case_10_product_switch(rt, llm):
    """D-415: a transition that names the next product switches at once (D-349/D-351), no countdown."""
    llm.judge(INTRO, utterance_type="transition", transition=True, target=AMPOULE, confidence="high", covered=["am-p1"])
    llm.judge(INFO, covered=["am-p2"])
    await speak(rt, INTRO)
    seg = await rt.current_segment()
    assert (seg.product_id, seg.start_reason) == (AMPOULE, "auto_speech")
    await advance(rt, GAP_MS)
    await speak(rt, INFO)
    assert (await rt.current_segment()).covered_point_ids == ["am-p1", "am-p2"]
    assert await events(rt, "segment.started")


CASES = [case_01_prompter_point, case_02_compliance_violation, case_03_the_judge_decides_a_correction,
         case_04_correction, case_05_negated_claim, case_06_quoted_claim, case_07_wrong_fact,
         case_08_fact_corrected, case_09_host_answer_published, case_10_product_switch]


@pytest.mark.parametrize("case", CASES, ids=[c.__name__.removeprefix("case_") for c in CASES])
async def test_orchestrator_case(env, case):
    rt, llm = env
    assert (await rt.current_segment()).product_id == CREAM
    await case(rt, llm)
