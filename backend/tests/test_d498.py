"""D-498 (user: "재시도 하는 버튼을 추가하는 방향으로"): a failed recap can be written again. Only a failed summary is
rerun; one being written or ready is left alone; before the show ends it is refused."""
from __future__ import annotations

import pytest

from app.pipelines import summary as summary_mod
from app.pipelines.runtime import ActionError
from app.pipelines.summary import SummaryDoc, _load, _save, retry_summary

from .judge_fakes import ScriptedBackend, close_env
from .test_d462 import show


@pytest.fixture
def runs(monkeypatch):
    calls = []

    async def fake_run(rt, **kw):
        calls.append(rt.sid)
    monkeypatch.setattr(summary_mod, "run_summary", fake_run)
    return calls


async def _ended(rt, status):
    await rt.end()
    await rt.ctx.scheduler.idle()
    await _save(rt, SummaryDoc(status=status, stats={"n": 1}, error="x" if status == "failed" else None,
                               created_at=1, updated_at=1))


async def test_a_failed_summary_is_written_again(runs):
    rt = await show(ScriptedBackend())
    try:
        await _ended(rt, "failed")
        runs.clear()
        assert await retry_summary(rt) == "computing"
        await rt.ctx.scheduler.idle()
        doc = await _load(rt)
        assert doc.status == "computing" and doc.error is None and doc.stats == {"n": 1}
        assert runs == [rt.sid]
        assert await retry_summary(rt) == "computing"  # a second press while it runs: nothing new
        assert runs == [rt.sid]
    finally:
        await close_env(rt)


@pytest.mark.parametrize("status", ["computing", "ready"])
async def test_a_summary_being_written_or_ready_is_left_alone(runs, status):
    rt = await show(ScriptedBackend())
    try:
        await _ended(rt, status)
        runs.clear()
        assert await retry_summary(rt) == status
        assert (await _load(rt)).status == status and runs == []
    finally:
        await close_env(rt)


async def test_before_the_end_it_is_refused(runs):
    rt = await show(ScriptedBackend())
    try:
        with pytest.raises(ActionError) as e:
            await retry_summary(rt)
        assert e.value.status == 409 and runs == []
    finally:
        await close_env(rt)


def test_an_unknown_show_is_a_404():
    from fastapi.testclient import TestClient

    from app.main import create_app

    from .conftest import make_settings

    with TestClient(create_app(make_settings())) as client:
        r = client.post("/api/sessions/ses_missing/summary/retry")
        assert r.status_code == 404
