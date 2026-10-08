"""D-396 (user: "ㅇㅋ ㄱ"): the fact checker (v5) writes `say`, the line the host says to fix a contradiction; it is
carried onto the fact note as it is. Demo products; the verdict is scripted."""
from __future__ import annotations

from .judge_fakes import close_env, speak
from .test_d372 import LIVE, _env, _sid, _verdict


async def test_d396_the_model_s_say_line_is_on_the_note():
    rt, llm = await _env()
    line = "The live price is thirty-two dollars."
    try:
        _verdict(llm, line, "contradicts", [_sid(rt, LIVE)], stated="S$32", correct="S$36.00")
        llm.outputs[("fact_checker", line)]["claims"][0]["say"] = "The live price is S$36.00."
        await speak(rt, line)
        [note] = [a for a in await rt.alerts() if a.kind == "fact"]
        assert (note.correct_value, note.say) == ("S$36.00", "The live price is S$36.00.")
    finally:
        await close_env(rt)
