"""D-394 (user, audit item 11): the context judge judges "moving on" by meaning, in any wording (no "next" needed).
D-415: the two-step mode and its pending-switch line are gone."""
from __future__ import annotations


from .helpers import live_runtime, make_ctx

PENDING = "cancel a pending switch"


async def test_d394_the_switch_lines_the_context_judge_gets():
    rt = await live_runtime(make_ctx())
    try:
        instruction = rt.utterances.context.system_instruction
        assert 'not even "next"' in instruction and PENDING not in instruction
    finally:
        rt.ctx.runtimes.shutdown()
        rt.ctx.scheduler.shutdown()
