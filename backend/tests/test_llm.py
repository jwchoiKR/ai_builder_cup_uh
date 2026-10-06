from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import BaseModel

from app.context import StoreAudit
from app.models.agent_io import CommentTriageOutput
from app.models.session import AgentCall, Event
from app.providers.llm import (
    LLMClient,
    LLMError,
    LLMRequest,
    LLMServerError,
    LLMTimeout,
    MockBackend,
    RawReply,
    mock_key,
    vertex_config,
)
from app.store.base import AGENT_CALLS_GLOBAL, sub


class Out(BaseModel):
    answer: str
    n: int


class FakeBackend:
    """Plays a script of replies: a string (JSON text), an exception, or ("sleep", seconds)."""

    name = "fake"

    def __init__(self, *script) -> None:
        self.script = list(script)
        self.calls: list[int] = []

    async def generate(self, req, timeout_ms):
        self.calls.append(timeout_ms)
        step = self.script.pop(0)
        if isinstance(step, tuple) and step[0] == "sleep":
            await asyncio.sleep(step[1])
            return RawReply('{"answer":"late","n":1}')
        if isinstance(step, Exception):
            raise step
        return RawReply(step, model_version="fake-1")

    async def warm_up(self, model, timeout_ms):
        if self.script and isinstance(self.script[0], Exception):
            raise self.script.pop(0)

    async def aclose(self):
        return None


def _req(**kw) -> LLMRequest:
    values = dict(agent="test_agent", model="m", thinking_level="MINIMAL", prompt_version="test_v1",
                  system_instruction="sys", user_message="<data>hi</data>", output_model=Out,
                  deadline_ms=500, session_id="ses_1", mock_primary_text="Hi")
    values.update(kw)
    return LLMRequest(**values)


@pytest.fixture
def make_client(settings, clock, ids, store, bus):
    def _make(backend, retry=1):
        s = settings.model_copy(update={"LLM_RETRY_ON_5XX": retry})
        return LLMClient(backend, s, clock, ids, StoreAudit(store, bus))
    return _make


async def test_ok_call_is_validated_and_audited(make_client, store):
    client = make_client(FakeBackend('{"answer":"yes","n":2}'))
    res = await client.call(_req())
    assert res.status == "ok" and res.output == Out(answer="yes", n=2)
    assert res.call_id == "call_000001" and res.meta["model_version"] == "fake-1"
    call = await store.get(sub("ses_1", "agent_calls"), res.call_id, AgentCall)
    assert call.status == "ok" and call.output == {"answer": "yes", "n": 2}
    assert call.prompt_version == "test_v1" and call.input_preview == "Hi" and len(call.input_hash) == 40
    events = await store.query(sub("ses_1", "events"), Event)
    assert [e.type for e in events] == ["agent.call"]


async def test_call_without_session_is_audited_globally(make_client, store):
    client = make_client(FakeBackend('{"answer":"yes","n":2}'))
    res = await client.call(_req(session_id=None))
    assert await store.get(AGENT_CALLS_GLOBAL, res.call_id, AgentCall) is not None


@pytest.mark.parametrize("reply", ['{"answer":"x"}', "not json", '{"answer":"x","n":"many"}'])
async def test_schema_or_json_failure_is_invalid(make_client, store, reply):
    res = await make_client(FakeBackend(reply)).call(_req())
    assert res.status == "invalid" and res.output is None and res.error
    call = await store.get(sub("ses_1", "agent_calls"), res.call_id, AgentCall)
    assert call.output == {"raw": reply}


async def test_deadline_gives_timeout_and_no_retry(make_client):
    backend = FakeBackend(("sleep", 5), '{"answer":"x","n":1}')
    res = await make_client(backend).call(_req(deadline_ms=100))
    assert res.status == "timeout" and res.output is None
    assert 90 <= res.latency_ms < 1000
    assert len(backend.calls) == 1


async def test_backend_timeout_is_not_retried(make_client):
    backend = FakeBackend(LLMTimeout("ReadTimeout"), '{"answer":"x","n":1}')
    res = await make_client(backend).call(_req())
    assert res.status == "timeout" and len(backend.calls) == 1


async def test_5xx_is_retried_once(make_client):
    backend = FakeBackend(LLMServerError("503"), '{"answer":"x","n":1}')
    res = await make_client(backend).call(_req())
    assert res.status == "ok" and len(backend.calls) == 2
    assert backend.calls[1] <= backend.calls[0]  # retry gets only the remaining time


async def test_5xx_twice_is_error(make_client):
    backend = FakeBackend(LLMServerError("500"), LLMServerError("503"), '{"answer":"x","n":1}')
    res = await make_client(backend).call(_req())
    assert res.status == "error" and len(backend.calls) == 2


async def test_retry_disabled(make_client):
    backend = FakeBackend(LLMServerError("503"), '{"answer":"x","n":1}')
    res = await make_client(backend, retry=0).call(_req())
    assert res.status == "error" and len(backend.calls) == 1


async def test_4xx_is_error_without_retry(make_client):
    backend = FakeBackend(LLMError("400 INVALID_ARGUMENT"), '{"answer":"x","n":1}')
    res = await make_client(backend).call(_req())
    assert res.status == "error" and "400" in res.error and len(backend.calls) == 1


async def test_unexpected_exception_never_raises(make_client):
    res = await make_client(FakeBackend(RuntimeError("boom"))).call(_req())
    assert res.status == "error" and "boom" in res.error


async def test_warm_up_reports_per_model(make_client):
    client = make_client(FakeBackend(RuntimeError("cold")))
    status = await client.warm_up()
    assert set(status) == {client.fast.model, client.quality.model}
    assert any(v.startswith("failed") for v in status.values())


# ---- mock backend ----------------------------------------------------------------------------


def test_mock_key_normalises_text():
    assert mock_key("a", "  How much   IS it? ", "default") == mock_key("a", "how much is it?", "default")
    assert mock_key("a", "x", "U01") != mock_key("a", "x", "default")


async def test_mock_fixture_lookup_order(tmp_path, make_client):
    backend = MockBackend(tmp_path)
    scenario_file = backend.fixture_path("test_agent", "Hi", "S05")
    default_file = backend.fixture_path("test_agent", "Hi", "default")
    default_file.parent.mkdir(parents=True)
    default_file.write_text(json.dumps({"answer": "default", "n": 1}), encoding="utf-8")
    client = make_client(backend)

    assert (await client.call(_req(mock_scenario="S05"))).output.answer == "default"  # falls back
    scenario_file.write_text(json.dumps({"answer": "scene", "n": 2}), encoding="utf-8")
    assert (await client.call(_req(mock_scenario="S05"))).output.answer == "scene"
    fallback = (await client.call(_req(mock_primary_text="other", mock_fallback=lambda r: {"answer": "rule", "n": 0})))
    assert fallback.output.answer == "rule"
    missing = await client.call(_req(mock_primary_text="other"))
    assert missing.status == "error" and "no mock fixture" in missing.error


def test_mock_ids_are_deterministic(ids):
    assert [ids.new("al_", "s1"), ids.new("al_", "s1"), ids.new("al_", "s2"), ids.new("cm_", "s1")] == [
        "al_000001", "al_000002", "al_000001", "cm_000001",
    ]


# ---- vertex request config ---------------------------------------------------------------------


def test_vertex_config_uses_verified_fields():
    req = _req(output_model=CommentTriageOutput, thinking_level="MINIMAL")
    schema = CommentTriageOutput.model_json_schema()
    cfg = vertex_config(req, 2500, schema)
    assert cfg.response_mime_type == "application/json"
    assert cfg.response_json_schema is schema and cfg.response_schema is None
    assert cfg.thinking_config.thinking_level.value == "MINIMAL"
    assert cfg.temperature is None  # D-008
    assert cfg.automatic_function_calling.disable is True
    assert cfg.http_options is None  # no X-Server-Timeout (D-047); asyncio.wait_for enforces the deadline
    assert cfg.system_instruction == "sys"
    assert set(schema["$defs"]["ConditionSlots"]["required"]) == {
        "person_type", "life_stage", "condition", "combined_with", "time_of_day",
    }


@pytest.fixture
def make_hedged(settings, clock, ids, store, bus):
    def _make(backend, hedge_ms=50):
        s = settings.model_copy(update={"JUDGE_HEDGE_MS": hedge_ms})
        return LLMClient(backend, s, clock, ids, StoreAudit(store, bus))
    return _make


async def test_d184_a_slow_judge_call_gets_a_second_request_and_the_first_answer_wins(make_hedged):
    """D-184 (cloud 00008: a fact check timed out after 6 s with no second try, so a wrong fact was never noted)."""
    backend = FakeBackend(("sleep", 5), '{"answer":"second","n":2}')
    client = make_hedged(backend)
    res = await client.call(_req(agent="fact_checker", deadline_ms=1000))
    assert res.status == "ok" and res.output.answer == "second" and res.latency_ms < 500
    assert len(backend.calls) == 2 and client.hedges["fact_checker"] == {"hedged": 1, "second_won": 1}


async def test_d184_a_fast_answer_or_another_agent_sends_one_request(make_hedged):
    backend = FakeBackend('{"answer":"x","n":1}', ("sleep", 5))
    client = make_hedged(backend)
    assert (await client.call(_req(agent="compliance_judge", deadline_ms=1000))).status == "ok"
    assert len(backend.calls) == 1 and client.hedges == {}
    other = FakeBackend(("sleep", 5), '{"answer":"x","n":1}')
    res = await make_hedged(other).call(_req(agent="answer_composer", deadline_ms=200))
    assert res.status == "timeout" and len(other.calls) == 1  # not on the alert path: no second request


async def test_d184_an_error_on_one_request_waits_for_the_other(make_hedged):
    class Slow(FakeBackend):
        async def generate(self, req, timeout_ms):
            self.calls.append(timeout_ms)
            if len(self.calls) == 1:
                await asyncio.sleep(0.2)
                raise LLMError("400 bad request")
            await asyncio.sleep(0.3)
            return RawReply('{"answer":"second","n":2}')

    res = await make_hedged(Slow()).call(_req(agent="context_judge", deadline_ms=1000))
    assert res.status == "ok" and res.output.answer == "second"
    both_slow = FakeBackend(("sleep", 5), ("sleep", 5))
    res = await make_hedged(both_slow).call(_req(agent="compliance_judge", deadline_ms=300))
    assert res.status == "timeout" and len(both_slow.calls) == 2


async def test_d184_hedging_off(make_hedged):
    backend = FakeBackend(("sleep", 5), '{"answer":"x","n":1}')
    res = await make_hedged(backend, hedge_ms=0).call(_req(agent="compliance_judge", deadline_ms=200))
    assert res.status == "timeout" and len(backend.calls) == 1


async def test_d187_tokens_are_audited_and_summed_per_agent(make_client, store, tmp_path):
    from app.providers import llm as llm_mod

    class WithUsage(FakeBackend):
        async def generate(self, req, timeout_ms):
            self.calls.append(timeout_ms)
            return RawReply('{"answer":"x","n":1}', "fake-1", {"prompt": 900, "output": 20, "thoughts": 5, "cached": 600})

    llm_mod.USAGE.clear()
    client = make_client(WithUsage())
    res = await client.call(_req(agent="compliance_judge"))
    await client.call(_req(agent="compliance_judge"))
    call = await store.get(sub("ses_1", "agent_calls"), res.call_id, AgentCall)
    assert call.usage == {"prompt": 900, "output": 20, "thoughts": 5, "cached": 600}
    assert llm_mod.USAGE["compliance_judge"] == {"calls": 2, "prompt": 1800, "output": 40, "thoughts": 10, "cached": 1200}
    out = tmp_path / "usage.json"
    llm_mod.write_usage_report(str(out))
    assert json.loads(out.read_text(encoding="utf-8"))["total"]["calls"] == 2
    llm_mod.USAGE.clear()
