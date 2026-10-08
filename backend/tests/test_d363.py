"""D-363 (user): fact-note corrections work by handle, like compliance alerts (D-356): the fact checker sees the
active notes as F1, F2 ... (no ids) and answers one {handle, fixed_by_this_line} per note, first; a note is corrected
only when the model marks it fixed. A note that appears after a later line was already checked gets a re-check (as
D-357). Demo products; the fact checker's answers are scripted."""
from __future__ import annotations

import asyncio
import logging

from .judge_fakes import CREAM, claim, close_env, make_env, speak

PANTHENOL = "DL-CR-01#key-ingredients#panthenol"
SQUALANE = "DL-CR-01#key-ingredients#squalane"
WRONG = "It has ten percent panthenol."
OTHER = "And squalane is three percent."
FIX = "Sorry, panthenol is five percent."


def _wrong(llm):
    llm.facts(WRONG, claim("ingredient_amount", "contradicted", stated="10%", correct="5%", passage_id=PANTHENOL,
                           quote="Panthenol: 5%"))


class _Recording:
    def __init__(self, llm):
        self.requests = []
        original = llm.generate

        async def generate(req, timeout_ms):
            self.requests.append(req)
            return await original(req, timeout_ms)

        llm.generate = generate


async def test_d363_a_right_value_of_another_fact_leaves_the_note_open_and_its_own_fix_closes_it(caplog):
    rt, llm = await make_env()
    rec = _Recording(llm)
    try:
        _wrong(llm)
        await speak(rt, WRONG)
        [note] = [a for a in await rt.alerts() if a.kind == "fact"]
        llm.facts(OTHER, claim("ingredient_amount", "supported", stated="3%", correct="3%", passage_id=SQUALANE))
        await speak(rt, OTHER)
        assert (await rt.get_alert(note.alert_id)).status == "active"  # no fallback by field, passage or value
        req = [r for r in rec.requests if r.agent == "fact_checker" and r.mock_primary_text == OTHER][-1]
        assert '<data name="ACTIVE_FACT_NOTES">' in req.user_message and '"handle": "F1"' in req.user_message
        assert note.alert_id not in req.user_message  # handles only, never ids
        assert list(req.output_model.model_json_schema()["properties"])[0] == "note_checks"
        llm.facts(FIX, claim("ingredient_amount", "supported", stated="5%", passage_id=PANTHENOL), fixed=["F1"])
        with caplog.at_level(logging.INFO):
            await speak(rt, FIX)
        assert (await rt.get_alert(note.alert_id)).status == "corrected"
        assert "fact notes call=" in caplog.text and note.alert_id in caplog.text  # the handle map is logged
    finally:
        await close_env(rt)


async def test_d363_a_supported_claim_alone_never_closes_a_note():
    rt, llm = await make_env()
    try:
        _wrong(llm)
        await speak(rt, WRONG)
        llm.facts(FIX, claim("ingredient_amount", "supported", stated="5%", passage_id=PANTHENOL))  # no handle marked
        await speak(rt, FIX)
        [note] = [a for a in await rt.alerts() if a.kind == "fact"]
        assert note.status == "active"
    finally:
        await close_env(rt)


async def test_d363_a_note_that_came_after_its_fix_was_checked_is_asked_again(caplog):
    """The wrong line's fact check is slow: the fix line is checked first (no note yet); when the note appears, the
    fix line is asked once more, with that note alone, and closes it."""
    rt, llm = await make_env()
    retract = "Sorry, scratch that, I misread the label."  # no claim of its own; it only fixes the note
    try:
        _wrong(llm)
        llm.delays[("fact_checker", WRONG)] = 0.3
        llm.facts(retract, fixed=["F1"])
        with caplog.at_level(logging.INFO):
            await rt.inject_transcript(WRONG)
            await asyncio.sleep(0.05)
            await rt.inject_transcript(retract)
            await rt.utterances.drain()
            await rt.ctx.scheduler.idle()
        [note] = [a for a in await rt.alerts() if a.kind == "fact"]
        assert note.status == "corrected"
        assert "fact note" in caplog.text and "re-check trigger" in caplog.text and "-> fired" in caplog.text
        assert note.product_id == CREAM
    finally:
        await close_env(rt)
