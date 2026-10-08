"""D-341 (review H17/H18): the context verdict is logged at INFO (D-415: switch decisions are D-349's log)."""
from __future__ import annotations

from .judge_fakes import close_env, make_env, speak


async def test_d341_context_and_switch_decisions_are_logged(caplog):
    caplog.set_level("INFO", logger="app.pipelines.utterances")
    rt, _ = await make_env()
    try:
        await speak(rt, "It feels light and soft.")
        await rt.utterances.drain()
        lines = [r.getMessage() for r in caplog.records]
        assert any(m.startswith("context ") and "type=" in m and "transition=" in m for m in lines)
    finally:
        await close_env(rt)
