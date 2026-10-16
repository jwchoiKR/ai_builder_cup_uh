"""D-490: the prompter judge sees the on-air product's points only; a twin point on the next product cannot be ticked
by it (10/16 14:26: the next product's identical test disclaimer was ticked instead of the one on air)."""
from __future__ import annotations

from .judge_fakes import close_env, speak
from .test_d450 import LINE, NEXT_P1, P1, P2, _Backend, _covered, _show


async def test_the_points_input_holds_only_the_on_air_products_ids():
    llm = _Backend()
    llm.outputs[("prompter_judge", LINE)] = _covered(P1)
    rt = await _show(llm)
    try:
        await speak(rt, LINE)
        await rt.utterances.drain()
        [req] = [r for r in llm.requests if r.agent == "prompter_judge"]
        assert P1 in req.user_message and P2 in req.user_message
        assert NEXT_P1 not in req.user_message
    finally:
        await close_env(rt)


async def test_a_twin_point_on_the_next_product_is_not_ticked_and_is_logged(caplog):
    caplog.set_level("INFO")
    llm = _Backend()
    llm.outputs[("prompter_judge", LINE)] = _covered(NEXT_P1)  # the model answers with the next product's id anyway
    rt = await _show(llm)
    try:
        await speak(rt, LINE)
        await rt.utterances.drain()
        assert list((await rt.current_segment()).covered_point_ids) == []
        assert (await rt.load_session()).pre_covered == {}
        assert any("ids not of the line's product skipped" in r.getMessage() and NEXT_P1 in r.getMessage()
                   for r in caplog.records)
    finally:
        await close_env(rt)
