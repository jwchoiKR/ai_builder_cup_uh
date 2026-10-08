"""D-364: codex review of D-363: corrections in line order, notes the model can tell apart, and a re-check in the
line's own context. Demo products; the fact checker's answers are scripted."""
from __future__ import annotations

import asyncio

from .judge_fakes import claim, close_env, make_env, speak

PANTHENOL = "DL-CR-01#key-ingredients#panthenol"
SQUALANE = "DL-CR-01#key-ingredients#squalane"


def _wrong(llm, line: str, passage: str = PANTHENOL, quote: str = "Panthenol: 5%", correct: str = "5%"):
    llm.facts(line, claim("ingredient_amount", "contradicted", stated="10%", correct=correct, passage_id=passage,
                          quote=quote))


class _Recording:
    def __init__(self, llm):
        self.requests = []
        original = llm.generate

        async def generate(req, timeout_ms):
            self.requests.append(req)
            return await original(req, timeout_ms)

        llm.generate = generate


async def test_d364_a_late_fix_from_an_older_line_does_not_close_a_note_shown_again_later():
    """T1 wrong, T2 fix (its verdict comes last), T3 wrong again: the note T3 re-showed stays open."""
    rt, llm = await make_env()
    t1, t2, t3 = "It has ten percent panthenol.", "Sorry, scratch that.", "Yeah, ten percent panthenol, so good."
    try:
        _wrong(llm, t1)
        await speak(rt, t1)
        llm.facts(t2, fixed=["F1"])
        llm.delays[("fact_checker", t2)] = 0.3
        _wrong(llm, t3)
        await rt.inject_transcript(t2)
        await asyncio.sleep(0.05)
        await rt.inject_transcript(t3)
        await rt.utterances.drain()
        await rt.ctx.scheduler.idle()
        [note] = [a for a in await rt.alerts() if a.kind == "fact"]
        assert note.status == "active"  # T2's fix is older than T3's showing
    finally:
        await close_env(rt)


async def test_d364_each_note_says_what_it_is_about():
    """Two notes with the same field and values (10% -> 5%) differ by the host's words and the source sentence."""
    rt, llm = await make_env()
    rec = _Recording(llm)
    try:
        _wrong(llm, "Ten percent panthenol in here.")
        _wrong(llm, "And ten percent squalane too.", SQUALANE, "Squalane: 3%", "3%")
        await speak(rt, "Ten percent panthenol in here.")
        await speak(rt, "And ten percent squalane too.")
        await speak(rt, "Isn't that great.")
        req = [r for r in rec.requests if r.agent == "fact_checker" and r.mock_primary_text == "Isn't that great."][-1]
        block = req.user_message.split('<data name="ACTIVE_FACT_NOTES">')[1]
        assert '"subject": "Panthenol: 5%"' in block and '"subject": "Squalane: 3%"' in block
        assert '"host_said"' in block
    finally:
        await close_env(rt)


async def test_d364_a_re_check_runs_in_the_line_s_own_context():
    """The late-note re-check sends the line's original input (product, previous lines, passages) plus the note."""
    rt, llm = await make_env()
    rec = _Recording(llm)
    wrong, retract = "It has ten percent panthenol.", "Sorry, scratch that, I misread the label."
    try:
        _wrong(llm, wrong)
        llm.delays[("fact_checker", wrong)] = 0.3
        llm.facts(retract, fixed=["F1"])
        await rt.inject_transcript(wrong)
        await asyncio.sleep(0.05)
        await rt.inject_transcript(retract)
        await rt.utterances.drain()
        await rt.ctx.scheduler.idle()
        calls = [r for r in rec.requests if r.agent == "fact_checker" and r.mock_primary_text == retract]
        assert len(calls) == 2  # the line's own check, then the re-check with the note
        first, again = calls
        assert '<data name="ACTIVE_FACT_NOTES">' in again.user_message
        assert again.user_message.split('<data name="ACTIVE_FACT_NOTES">')[0].rstrip() == first.user_message.rstrip()
        [note] = [a for a in await rt.alerts() if a.kind == "fact"]
        assert note.status == "corrected"
    finally:
        await close_env(rt)
