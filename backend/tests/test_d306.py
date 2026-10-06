"""D-306: verifier slowness shown honestly. While the verifier works the host sees a grey "checking" chip (events
verify.started / verify.done), an alert appears only when it answers, and with no answer the alert is kept,
"unverified (AI response delayed)" with its failure type; the operator gets the count by cause. Every call records
its failure type (http_504, client_timeout, http_429, other_error)."""
from __future__ import annotations

import pytest

from app.providers.llm import LLMError, failure_kind

from .conftest import SHIPPED
from .judge_fakes import ScriptedBackend, close_env, events, make_env, speak, violation


@pytest.mark.parametrize("status, error, kind", [
    ("ok", None, None),
    ("timeout", "deadline 5000 ms", "client_timeout"),
    ("error", "504 DEADLINE_EXCEEDED. {'error': {'code': 504}}", "http_504"),
    ("error", "429 RESOURCE_EXHAUSTED", "http_429"),
    ("error", "scripted failure", "other_error"),
    ("invalid", "1 validation error", "other_error"),
])
def test_d306_failure_kind(status, error, kind):
    assert failure_kind(status, error) == kind


class _Busy(ScriptedBackend):
    """The verifier's calls fail as Google's shared capacity does."""

    async def generate(self, req, timeout_ms):
        if req.agent == "verifier":
            raise LLMError("504 DEADLINE_EXCEEDED")
        return await super().generate(req, timeout_ms)


LINE = "This cream cures eczema, honestly."


async def test_d306_no_verifier_answer_keeps_the_alert_unverified_with_its_cause():
    from .helpers import live_runtime, make_ctx

    llm = _Busy()
    llm.judge(LINE, violations=[violation("ASEAN-2D-DISEASE", "cures eczema")])
    rt = await live_runtime(make_ctx(backend=llm, **SHIPPED))
    try:
        await speak(rt, LINE)
        await rt.utterances.drain()
        [a] = [a for a in await rt.alerts() if a.kind == "compliance"]
        assert (a.status, a.unverified, a.unverified_reason) == ("active", True, "http_504")
        started, done = await events(rt, "verify.started"), await events(rt, "verify.done")
        assert [e.payload["kind"] for e in started] == ["compliance"] and len(done) == 1
        [health] = await events(rt, "verify.health")
        assert health.payload == {"no_answer": 1, "by": {"http_504": 1}}
        assert rt.utterances.verify_health() == {"no_answer": 1, "by": {"http_504": 1}}
    finally:
        await close_env(rt)


async def test_d306_the_chip_shows_only_while_the_verifier_works():
    rt, llm = await make_env(**SHIPPED)
    try:
        await speak(rt, "It feels light and soft.")  # no candidate: no verifier, no chip
        await rt.utterances.drain()
        assert await events(rt, "verify.started") == []
        llm.judge(LINE, violations=[violation("ASEAN-2D-DISEASE", "cures eczema")])
        await speak(rt, LINE)
        await rt.utterances.drain()
        evs = [(e.type, e.payload.get("status")) for e in await events(rt)
               if e.type in ("verify.started", "verify.done", "alert.created", "alert.updated")]
        started, done = evs.index(("verify.started", None)), evs.index(("verify.done", None))
        active = [i for i, (_, status) in enumerate(evs) if status == "active"]
        assert started < done and active and min(active) > started  # the alert is active only after the check
        assert await events(rt, "verify.health") == []  # every call answered
    finally:
        await close_env(rt)


def test_d306_the_verifier_waits_5_s_and_is_hedged_at_2_s_only_when_named(settings, clock, ids, store, bus):
    from app.config import Settings
    from app.context import StoreAudit
    from app.providers.llm import LLMClient

    defaults = {k: Settings.model_fields[k].default for k in ("VERIFY_TIMEOUT_MS", "HEDGED_AGENTS", "HEDGE_DELAYS")}
    assert defaults["VERIFY_TIMEOUT_MS"] == 5000
    client = LLMClient(ScriptedBackend(), settings.model_copy(update=defaults), clock, ids, StoreAudit(store, bus))
    assert "verifier" not in client._hedged_agents  # D-308: off until compared
    named = defaults | {"HEDGED_AGENTS": defaults["HEDGED_AGENTS"] + ",verifier"}
    client = LLMClient(ScriptedBackend(), settings.model_copy(update=named), clock, ids, StoreAudit(store, bus))
    assert "verifier" in client._hedged_agents and client._hedge_delays["verifier"] == 2000
