"""D-356: the compliance judge sees ACTIVE_ALERTS by per-call handle (A1, A2 ...) and answers one
{handle, fixed_by_this_line} per alert, first in its output; code restores the ids. D-358/D-434: the production
(originals) path always works this way. Made-up lines; the judge's answers are scripted as raw production JSON."""
from __future__ import annotations

import pytest

import logging

from app.models.agent_io import ComplianceOutputO, with_alert_checks

from .judge_fakes import close_env, speak, violation

CLAIM = "Honestly this balm heals scars in a week."
FIX = "Sorry, I take that back; it helps skin look smoother."


def test_d356_the_answer_starts_with_one_check_per_alert_and_recalls_no_ids():
    s = with_alert_checks(ComplianceOutputO).model_json_schema()
    assert list(s["properties"])[0] == "alert_checks" and "correction" not in s["properties"]
    assert s["$defs"]["AlertCheck"]["required"] == ["handle", "fixed_by_this_line"]


async def _show(answer_checks, caplog, handles=True):
    from .helpers import live_runtime, make_ctx
    from .judge_fakes import ScriptedBackend

    class Backend(ScriptedBackend):
        def __init__(self):
            super().__init__()
            self.fix_request = None

        async def generate(self, req, timeout_ms):
            if req.agent == "compliance_judge" and req.mock_primary_text == FIX:
                self.fix_request = req
            return await super().generate(req, timeout_ms)

    llm = Backend()
    llm.judge(CLAIM, violations=[violation("ASEAN-2D-DISEASE", "heals scars in a week")])
    out = {"compliance": {"violations": []}, "reason": "scripted"}
    if handles:
        out = {"alert_checks": answer_checks, **out}
    else:
        out["correction"] = {"corrects_alert_ids": answer_checks}
    llm.outputs[("compliance_judge", FIX)] = out
    # D-434: the production path always uses handles; the id-list answer is the legacy rules path's
    settings = {} if handles else {"CORRECTION_HANDLES": False}
    rt = await live_runtime(make_ctx(backend=llm, CORRECTION_CHECK="judge", **settings))
    try:
        with caplog.at_level(logging.INFO):
            await speak(rt, CLAIM)
            await speak(rt, FIX)
            await rt.utterances.drain()
        [a] = [a for a in await rt.alerts() if a.kind == "compliance" and a.span == "heals scars in a week"]
        return a, llm.fix_request
    finally:
        await close_env(rt)


async def test_d356_a_handle_marked_fixed_corrects_its_alert(caplog):
    a, req = await _show([{"handle": "A1", "fixed_by_this_line": True}], caplog)
    assert a.status == "corrected"
    assert '"handle":"A1"' in req.user_message and a.alert_id not in req.user_message  # no id is shown
    assert '"status":"active"' in req.user_message
    assert "compliance handles call=" in caplog.text and a.alert_id in caplog.text  # the map is logged


async def test_d356_not_fixed_or_an_unknown_handle_corrects_nothing(caplog):
    a, _ = await _show([{"handle": "A1", "fixed_by_this_line": False}, {"handle": "A9", "fixed_by_this_line": True}],
                       caplog)
    assert a.status == "active"
    assert "unknown handles dropped: ['A9']" in caplog.text


@pytest.mark.legacy_live  # D-434: an id-list answer exists only on the rules-JSON path (deleted with it, N4)
async def test_d356_an_id_the_judge_was_not_shown_is_logged_when_dropped(caplog):
    a, _ = await _show(["al_not_shown"], caplog, handles=False)
    assert a.status == "active"
    assert "correction ids dropped: not in ACTIVE_ALERTS: ['al_not_shown']" in caplog.text
