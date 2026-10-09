"""D-340 (review H15): a 429 is retried once after LLM_RETRY_ON_429_MS, only when the deadline leaves room; off by
default (0) until measured."""
from __future__ import annotations

import pytest

from app.providers.llm import LLMError, LLMRequest
from app.models.agent_io import FactRelationOutputV5

from .judge_fakes import ScriptedBackend


class _Busy(ScriptedBackend):
    def __init__(self, fails: int):
        super().__init__()
        self.fails, self.tries = fails, 0

    async def generate(self, req, timeout_ms):
        self.tries += 1
        if self.tries <= self.fails:
            raise LLMError("429 RESOURCE_EXHAUSTED: shared capacity")
        from app.providers.llm import RawReply

        return RawReply('{"claims": []}', model_version="scripted")


@pytest.mark.parametrize("backoff, deadline, status, tries", [
    (0, 5000, "error", 1),  # off: as before
    (50, 5000, "ok", 2),  # one retry
    (50, 900, "error", 1),  # no room left after the wait
])
async def test_d340_a_429_is_retried_once(settings, clock, ids, store, bus, backoff, deadline, status, tries):
    from app.context import StoreAudit
    from app.providers.llm import LLMClient

    backend = _Busy(fails=1)
    client = LLMClient(backend, settings.model_copy(update={"LLM_RETRY_ON_429_MS": backoff}), clock, ids,
                       StoreAudit(store, bus))
    req = LLMRequest(agent="fact_checker", model="m", thinking_level="LOW", prompt_version="v", system_instruction="s",
                     user_message="u", output_model=FactRelationOutputV5, deadline_ms=deadline, hedge=False)
    res = await client.call(req)
    assert (res.status, backend.tries) == (status, tries)


async def test_d340_two_429s_are_not_retried_twice(settings, clock, ids, store, bus):
    from app.context import StoreAudit
    from app.providers.llm import LLMClient

    backend = _Busy(fails=2)
    client = LLMClient(backend, settings.model_copy(update={"LLM_RETRY_ON_429_MS": 20}), clock, ids,
                       StoreAudit(store, bus))
    req = LLMRequest(agent="fact_checker", model="m", thinking_level="LOW", prompt_version="v", system_instruction="s",
                     user_message="u", output_model=FactRelationOutputV5, deadline_ms=5000, hedge=False)
    res = await client.call(req)
    assert (res.status, res.meta.get("failure"), backend.tries) == ("error", "http_429", 2)
