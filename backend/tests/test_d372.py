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
