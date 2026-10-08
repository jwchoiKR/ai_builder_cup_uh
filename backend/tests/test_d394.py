"""D-394 (user, audit item 11): the context judge judges "moving on" by meaning, in any wording (no "next" needed);
the line about cancelling a pending switch is sent only in the two-step mode, which has a pending switch."""
from __future__ import annotations

import pytest

from .helpers import live_runtime, make_ctx

PENDING = "cancel a pending switch"


@pytest.mark.parametrize("mode, meaning, pending", [("immediate", True, False), ("two_step", False, True)])
async def test_d394_the_switch_lines_each_mode_gets(mode, meaning, pending):
    rt = await live_runtime(make_ctx(SWITCH_MODE=mode))
    try:
        instruction = rt.utterances.context.system_instruction
        assert ('not even "next"' in instruction) is meaning
        assert (PENDING in instruction) is pending
    finally:
        rt.ctx.runtimes.shutdown()
        rt.ctx.scheduler.shutdown()
