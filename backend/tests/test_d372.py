"""D-372 (user): the prompter's "said" ticks for price lines, ingredient amounts and cautions come from the fact
checker's verdicts (prompter mode, FACT_PROMPT=v5): a supported claim the host asserts or endorses ticks the snapshot
items it cites; a contradiction or reported speech ticks nothing; a correction ticks the item as it closes the note;
in the dual scope after a switch, only the cited product's items. Demo products; the verdicts are scripted."""
from __future__ import annotations

from app.agents.fact_checker import sentence_index
from app.logic.prompter import prompter_passages

from .judge_fakes import AMPOULE, CREAM, close_env, events, make_env, speak

LIVE = "DL-CR-01#prompter#live-price"


async def _env(**settings):
    return await make_env(FACT_MODE="prompter", FACT_RELATION=True, FACT_PROMPT="v5", **settings)


def _sid(rt, passage_id: str, products=(CREAM,)) -> str:
    """The sentence id the model sees for a snapshot item (the same passages give the same ids)."""
    passages = [x for pid in products for x in prompter_passages(rt.catalog, pid, rt.points)]
    _, index = sentence_index(passages)
    return next(sid for sid, (p, _) in index.items() if p.passage_id == passage_id)


def _verdict(llm, line: str, relation: str, evidence: list[str], *, stance="HOST_ASSERTS", product=CREAM,
             stated="S$36", correct=None, fixed=()):
    llm.outputs[("fact_checker", line)] = {"claims": [{
        "span": line, "stance": stance, "product_id": product, "field": "price", "stated_value": stated,
        "evidence": evidence, "source_value": "S$36.00", "relation": relation, "correct_value": correct}],
        "note_checks": [{"handle": h, "fixed_by_this_line": True} for h in fixed]}


async def _ticks(rt) -> list[str]:
    return list((await rt.current_segment()).ticked_item_ids)


async def test_d372_a_right_value_ticks_its_item_and_updates_the_prompter():
    rt, llm = await _env()
    try:
        _verdict(llm, "The live price is thirty-six dollars.", "consistent", [_sid(rt, LIVE)])
        await speak(rt, "The live price is thirty-six dollars.")
        assert await _ticks(rt) == [LIVE]
        assert (await events(rt, "prompter.updated"))[-1].payload["ticked_item_ids"] == [LIVE]
    finally:
        await close_env(rt)


async def test_d372_a_wrong_value_and_reported_speech_tick_nothing():
    rt, llm = await _env()
    try:
        _verdict(llm, "The live price is thirty-two dollars.", "contradicts", [_sid(rt, LIVE)], stated="S$32",
                 correct="S$36.00")
        _verdict(llm, "A viewer asks if it is thirty-six dollars.", "consistent", [_sid(rt, LIVE)],
                 stance="REPORTS_OR_ASKS")
        await speak(rt, "The live price is thirty-two dollars.")
        await speak(rt, "A viewer asks if it is thirty-six dollars.")
        assert await _ticks(rt) == []
    finally:
        await close_env(rt)


async def test_d372_a_correction_closes_the_note_and_ticks_the_item():
    rt, llm = await _env()
    try:
        _verdict(llm, "The live price is thirty-two dollars.", "contradicts", [_sid(rt, LIVE)], stated="S$32",
                 correct="S$36.00")
        await speak(rt, "The live price is thirty-two dollars.")
        [note] = [a for a in await rt.alerts() if a.kind == "fact"]
        _verdict(llm, "Sorry, it is thirty-six dollars.", "consistent", [_sid(rt, LIVE)], fixed=["F1"])
        await speak(rt, "Sorry, it is thirty-six dollars.")
        assert (await rt.get_alert(note.alert_id)).status == "corrected"
        assert await _ticks(rt) == [LIVE]
    finally:
        await close_env(rt)


async def test_d372_in_the_dual_scope_only_the_cited_product_is_ticked():
    rt, llm = await _env(SWITCH_MODE="immediate")
    try:
        move = "Okay, let's move on to the ampoule."
        llm.judge(move, utterance_type="transition", transition=True, target=AMPOULE, confidence="high")
        await speak(rt, move)
        cream_seg = next(x for x in await rt.segments() if x.product_id == CREAM)
        assert (await rt.current_segment()).product_id == AMPOULE
        line = "And the cream was thirty-six dollars."
        _verdict(llm, line, "consistent", [_sid(rt, LIVE, (AMPOULE, CREAM))])
        await speak(rt, line)
        assert await _ticks(rt) == []  # the ampoule's own items stay as they were
        assert (await rt.get_segment(cream_seg.segment_id)).ticked_item_ids == [LIVE]
    finally:
        await close_env(rt)


# ---- D-373: codex review of D-372 -------------------------------------------------------------------------------------

AMP_LIVE = "DL-AM-01#prompter#live-price"


async def _settle(rt) -> None:
    await rt.utterances.drain()
    await rt.ctx.scheduler.idle()


async def test_d373_a_re_check_that_fixes_the_note_ticks_the_item():
    """The wrong line's check is slow; the fix line is checked first (no note, no claim); its re-check with the note
    comes back supported and fixed: the note closes and the item is ticked."""
    import asyncio

    rt, llm = await _env()
    wrong, fix = "The live price is thirty-two dollars.", "Sorry, scratch that, it is the usual price."
    try:
        _verdict(llm, wrong, "contradicts", [_sid(rt, LIVE)], stated="S$32", correct="S$36.00")
        llm.delays[("fact_checker", wrong)] = 0.3
        llm.outputs[("fact_checker", fix)] = {"claims": []}
        original = llm.generate

        async def generate(req, timeout_ms):
            if req.agent == "fact_checker" and req.mock_primary_text == fix and "ACTIVE_FACT_NOTES" in req.user_message:
                _verdict(llm, fix, "consistent", [_sid(rt, LIVE)], fixed=["F1"])
            return await original(req, timeout_ms)

        llm.generate = generate
        await rt.inject_transcript(wrong)
        await asyncio.sleep(0.05)
        await rt.inject_transcript(fix)
        await _settle(rt)
        [note] = [a for a in await rt.alerts() if a.kind == "fact"]
        assert note.status == "corrected" and await _ticks(rt) == [LIVE]
    finally:
        await close_env(rt)


async def test_d373_a_right_value_ticks_even_when_a_later_wrong_verdict_arrives_first():
    import asyncio

    rt, llm = await _env()
    right, wrong = "The live price is thirty-six dollars.", "I mean thirty-two dollars."
    try:
        _verdict(llm, right, "consistent", [_sid(rt, LIVE)])
        llm.delays[("fact_checker", right)] = 0.3
        _verdict(llm, wrong, "contradicts", [_sid(rt, LIVE)], stated="S$32", correct="S$36.00")
        await rt.inject_transcript(right)
        await asyncio.sleep(0.05)
        await rt.inject_transcript(wrong)
        await _settle(rt)
        assert await _ticks(rt) == [LIVE]
        assert [a.status for a in await rt.alerts() if a.kind == "fact"] == ["active"]  # the later wrong line's note
    finally:
        await close_env(rt)


async def test_d373_a_verdict_after_the_dual_scope_ends_still_ticks_the_product_the_line_was_about():
    """Said 9 s after the switch (inside the 10 s scope), the verdict lands at 11 s: the cream's segment is ticked."""
    import asyncio

    from .judge_fakes import advance

    rt, llm = await _env(SWITCH_MODE="immediate")
    try:
        move = "Okay, let's move on to the ampoule."
        llm.judge(move, utterance_type="transition", transition=True, target=AMPOULE, confidence="high")
        await speak(rt, move)
        cream_seg = next(x for x in await rt.segments() if x.product_id == CREAM)
        await advance(rt, 9_000)
        line = "And the cream was thirty-six dollars."
        _verdict(llm, line, "consistent", [_sid(rt, LIVE, (AMPOULE, CREAM))])
        llm.delays[("fact_checker", line)] = 0.3
        await rt.inject_transcript(line)
        await asyncio.sleep(0.05)
        rt.ctx.clock.set(rt.ctx.clock.now_ms() + 2_000)  # 11 s, while the call is still out (advance would wait)
        await _settle(rt)
        assert rt.utterances._scoped((await rt.load_session()).switch).previous_product_id is None  # scope over
        assert (await rt.get_segment(cream_seg.segment_id)).ticked_item_ids == [LIVE]
        assert await _ticks(rt) == []
    finally:
        await close_env(rt)


async def test_d373_a_late_verdict_for_an_undone_segment_waits_for_the_product_s_next_segment():
    """Cream -> ampoule -> cream -> ampoule, the last switch undone before the ampoule line's verdict lands: the tick
    is not put on the first ampoule segment; it shows when the ampoule goes on air again."""
    import asyncio

    from app.pipelines.utterances import operator_switch, undo_switch

    rt, llm = await _env(SWITCH_MODE="immediate")
    try:
        await operator_switch(rt, AMPOULE)
        first_amp = (await rt.current_segment()).segment_id
        await operator_switch(rt, CREAM)
        await operator_switch(rt, AMPOULE)
        line = "The ampoule is on its live price today."
        _verdict(llm, line, "consistent", [_sid(rt, AMP_LIVE, (AMPOULE,))], product=AMPOULE)
        llm.delays[("fact_checker", line)] = 0.3
        await rt.inject_transcript(line)
        await asyncio.sleep(0.05)
        await undo_switch(rt)
        await _settle(rt)
        assert (await rt.get_segment(first_amp)).ticked_item_ids == []
        assert (await rt.load_session()).pre_covered.get(AMPOULE) == [AMP_LIVE]
        await operator_switch(rt, AMPOULE)
        assert await _ticks(rt) == [AMP_LIVE]
    finally:
        await close_env(rt)


async def test_d376_a_line_naming_the_next_product_waits_for_its_next_segment():
    """Cream -> ampoule -> cream -> ampoule, the last switch undone: a line said on the reopened cream segment that
    ticks the ampoule (the next product) goes to pre_covered, not to the first, stale ampoule segment."""
    from app.pipelines.utterances import operator_switch, undo_switch

    rt, llm = await _env(SWITCH_MODE="immediate")
    try:
        from .judge_fakes import advance

        await advance(rt, 1000)  # D-381: one second apart (the first ampoule left within the dual scope)
        first_amp = (await operator_switch(rt, AMPOULE)).segment_id
        await advance(rt, 1000)
        await operator_switch(rt, CREAM)
        await advance(rt, 1000)
        await operator_switch(rt, AMPOULE)
        await undo_switch(rt)  # back on the cream; the ampoule just left (dual scope)
        line = "And the ampoule is on its live price today."
        _verdict(llm, line, "consistent", [_sid(rt, AMP_LIVE, (CREAM, AMPOULE))], product=AMPOULE)
        await speak(rt, line)
        assert (await rt.get_segment(first_amp)).ticked_item_ids == []
        assert (await rt.load_session()).pre_covered.get(AMPOULE) == [AMP_LIVE]
    finally:
        await close_env(rt)


async def test_d377_the_product_that_just_left_is_ticked_even_when_it_is_also_the_next_one():
    """Cream -> ampoule -> cream by the operator, then the ampoule's price said right inside the dual scope: the
    ampoule segment that just left the air is ticked (the ampoule is also the run sheet's next product)."""
    from app.pipelines.utterances import operator_switch

    from .judge_fakes import advance

    rt, llm = await _env(SWITCH_MODE="immediate")
    try:
        await advance(rt, 30_000)
        amp = (await operator_switch(rt, AMPOULE)).segment_id
        await advance(rt, 30_000)
        await operator_switch(rt, CREAM)
        await advance(rt, 3_000)
        line = "And the ampoule was on its live price."
        _verdict(llm, line, "consistent", [_sid(rt, AMP_LIVE, (CREAM, AMPOULE))], product=AMPOULE)
        await speak(rt, line)
        assert (await rt.get_segment(amp)).ticked_item_ids == [AMP_LIVE]
        assert not (await rt.load_session()).pre_covered.get(AMPOULE)
    finally:
        await close_env(rt)


async def test_d382_a_second_undo_after_the_line_does_not_change_its_reopen_state():
    """Cream -> ampoule (B1) -> cream -> ampoule (B2), undo; the ampoule's price is said; then ampoule (B3) and undo
    again before the verdict lands: the line is judged on the reopen before it, so B1 is not ticked."""
    import asyncio

    from app.pipelines.utterances import operator_switch, undo_switch

    from .judge_fakes import advance

    rt, llm = await _env(SWITCH_MODE="immediate")
    try:
        await advance(rt, 1000)
        first_amp = (await operator_switch(rt, AMPOULE)).segment_id
        await advance(rt, 1000)
        await operator_switch(rt, CREAM)
        await advance(rt, 1000)
        await operator_switch(rt, AMPOULE)
        await undo_switch(rt)
        await advance(rt, 1000)
        line = "And the ampoule is on its live price today."
        _verdict(llm, line, "consistent", [_sid(rt, AMP_LIVE, (CREAM, AMPOULE))], product=AMPOULE)
        llm.delays[("fact_checker", line)] = 0.3
        await rt.inject_transcript(line)
        await asyncio.sleep(0.05)
        rt.ctx.clock.set(rt.ctx.clock.now_ms() + 1000)  # while the call is out: another switch and undo
        await operator_switch(rt, AMPOULE)
        await undo_switch(rt)
        await _settle(rt)
        assert (await rt.get_segment(first_amp)).ticked_item_ids == []
        assert (await rt.load_session()).pre_covered.get(AMPOULE) == [AMP_LIVE]
    finally:
        await close_env(rt)
