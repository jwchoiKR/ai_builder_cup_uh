"""Compliance alert lifecycle (DEV_SPEC §8.4, §14.1 alerts)."""
from __future__ import annotations

import pytest

from app.logic import alerts as alert_logic
from app.models.session import Alert
from app.pipelines import utterances as utt
from app.pipelines.runtime import ActionError

from .judge_fakes import rid, CREAM, advance, close_env, events, make_env, speak, violation

WRINKLES = "Use it every night and your wrinkles will disappear overnight."
BACTERIA = "It kills the bacteria on your skin."


@pytest.fixture
async def env():
    rt, llm = await make_env()
    yield rt, llm
    await close_env(rt)


async def only_alert(rt) -> Alert:
    [a] = await rt.alerts()
    return a


# ---- judge confirms / clears -------------------------------------------------------------------


# ---- judge failure: D-410, the neutral card only ----------------------------------------------------


# ---- escalation, correction, dismiss ------------------------------------------------------------


# ---- pure functions -----------------------------------------------------------------------------


def test_dismiss_function_states():
    a = Alert(alert_id="al_1", kind="compliance", status="corrected", transcript_id="t", product_id=CREAM, created_at=0)
    assert alert_logic.dismiss(a, 5) is False
    a.status = "active"
    assert alert_logic.dismiss(a, 5) and a.status == "dismissed" and a.resolved_at == 5
