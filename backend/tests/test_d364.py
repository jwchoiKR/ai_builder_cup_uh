"""D-364: codex review of D-363: corrections in line order, notes the model can tell apart, and a re-check in the
line's own context. Demo products; the fact checker's answers are scripted."""
from __future__ import annotations

import pytest

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


async def test_d364_a_late_fix_from_an_older_line_closes_only_the_note_it_saw():
    """T1 wrong, T2 fix (its verdict comes last), T3 wrong again: D-398, T3's claim is its own note; T2's fix closes
    T1's note (the one it was shown) and never T3's, raised after it."""
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
        notes = sorted((a for a in await rt.alerts() if a.kind == "fact"), key=lambda a: a.created_at)
        assert [a.status for a in notes] == ["corrected", "active"]
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



async def test_d398_two_wrong_claims_under_one_passage_are_corrected_one_at_a_time():
    """D-398: each contradicted claim is its own note with its own handle, even when both cite one passage."""
    rt, llm = await make_env()
    first, second = "It has ten percent panthenol.", "Honestly, it is twelve percent panthenol."
    fix_second, fix_first = "Sorry, not twelve.", "And not ten either: five percent."
    try:
        _wrong(llm, first)
        _wrong(llm, second)
        from .judge_fakes import advance

        await speak(rt, first)
        await advance(rt, 5000)  # 5 s apart, so "newest first" has an order
        await speak(rt, second)
        notes = sorted((a for a in await rt.alerts() if a.kind == "fact"), key=lambda a: a.created_at)
        assert len(notes) == 2 and notes[0].passage_id == notes[1].passage_id
        llm.facts(fix_second, fixed=["F1"])  # newest first: F1 is the second claim's note
        await speak(rt, fix_second)
        assert [(await rt.get_alert(a.alert_id)).status for a in notes] == ["active", "corrected"]
        llm.facts(fix_first, fixed=["F1"])  # now the first claim's note is the only one, F1
        await speak(rt, fix_first)
        assert [(await rt.get_alert(a.alert_id)).status for a in notes] == ["corrected", "corrected"]
    finally:
        await close_env(rt)


async def test_d398_a_merged_verdict_replaces_the_fragment_s_note():
    """D-398: a fragment ("... ten percent panthenol and") raised a note; the merged sentence's verdict finds no error
    for it (the host goes on to correct the amount), so the fragment's note goes."""
    from .judge_fakes import advance

    rt, llm = await make_env()
    fragment, rest = "It has ten percent panthenol and", "sorry, five percent, I misread."
    try:
        _wrong(llm, fragment)
        llm.facts(f"{fragment} {rest}")  # the whole sentence: no error
        await speak(rt, fragment)
        [note] = [a for a in await rt.alerts() if a.kind == "fact"]
        await advance(rt, 1200)
        await speak(rt, rest)
        assert (await rt.get_alert(note.alert_id)).status == "cleared"
        assert [a for a in await rt.alerts() if a.kind == "fact" and a.status == "active"] == []
    finally:
        await close_env(rt)


pytestmark = pytest.mark.legacy_live  # D-434: not migrated yet (removed in its batch)
