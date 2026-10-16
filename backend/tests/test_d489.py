"""D-489: the prompter judge has no deadline, but a call with no answer after PROMPTER_HEDGE_MS (4 s) sends one
identical second request; the first answer wins."""
from __future__ import annotations

import pytest

from app.config import Settings
from app.context import StoreAudit
from app.providers.llm import LLMClient

from .test_llm import FakeBackend, _req


@pytest.fixture
def client_with(settings, clock, ids, store, bus):
    def _make(backend, hedge_ms=50):
        s = settings.model_copy(update={"PROMPTER_HEDGE_MS": hedge_ms, "HEDGED_AGENTS": "", "HEDGE_DELAYS": ""})
        return LLMClient(backend, s, clock, ids, StoreAudit(store, bus))
    return _make


def test_the_default_is_4_s():
    assert Settings.model_fields["PROMPTER_HEDGE_MS"].default == 4000


async def test_a_slow_first_call_gets_the_second_requests_answer(client_with):
    backend = FakeBackend(("sleep", 5), '{"answer":"second","n":2}')
    client = client_with(backend)
    res = await client.call(_req(agent="prompter_judge", deadline_ms=None))
    assert res.status == "ok" and res.output.answer == "second" and res.latency_ms < 500
    assert len(backend.calls) == 2 and client.hedges["prompter_judge"] == {"hedged": 1, "second_won": 1}


async def test_a_fast_first_call_sends_no_second_request(client_with):
    backend = FakeBackend('{"answer":"x","n":1}', ("sleep", 5))
    client = client_with(backend)
    assert (await client.call(_req(agent="prompter_judge", deadline_ms=None))).status == "ok"
    assert len(backend.calls) == 1 and client.hedges == {}


async def test_zero_turns_it_off(client_with):
    backend = FakeBackend(("sleep", 0.2), '{"answer":"second","n":2}')
    res = await client_with(backend, hedge_ms=0).call(_req(agent="prompter_judge", deadline_ms=None))
    assert res.status == "ok" and res.output.answer == "late" and len(backend.calls) == 1
