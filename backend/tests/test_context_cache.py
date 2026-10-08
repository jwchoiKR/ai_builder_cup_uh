"""Explicit-cache contract, with no network or credentials."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.providers.llm import LLMRequest, MockBackend, VertexBackend


class Out(BaseModel):
    answer: str


def request(**changes):
    req = LLMRequest(
        agent="fact", model="gemini-3.5-flash-lite", thinking_level="MINIMAL",
        prompt_version="v1", system_instruction="system", user_message="static\ndynamic",
        cache_prefix="static\n", cache_ttl_sec=120, output_model=Out,
        deadline_ms=2500, session_id="session",
    )
    return replace(req, **changes)


@pytest.fixture
def backend(monkeypatch):
    from google import genai

    reply = SimpleNamespace(
        text='{"answer":"ok"}', candidates=[], model_version="test",
        usage_metadata=SimpleNamespace(prompt_token_count=4200, candidates_token_count=4,
                                       thoughts_token_count=0, cached_content_token_count=4100),
    )
    models = SimpleNamespace(count_tokens=AsyncMock(return_value=SimpleNamespace(total_tokens=4100)),
                             generate_content=AsyncMock(return_value=reply))
    caches = SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(name="cached/1")))
    client = SimpleNamespace(aio=SimpleNamespace(models=models, caches=caches, aclose=AsyncMock()))
    monkeypatch.setattr(genai, "Client", lambda **kwargs: client)
    return VertexBackend("project", "global", context_cache=True)


@pytest.mark.asyncio
async def test_create_reuse_and_structured_output(backend):
    req = request()
    first = await backend.generate(req, 2500)
    await backend.generate(replace(req, user_message="static\nnext"), 2500)
    aio = backend._client.aio
    aio.models.count_tokens.assert_awaited_once()
    aio.caches.create.assert_awaited_once()
    create = aio.caches.create.call_args.kwargs["config"]
    assert create.system_instruction == "system"
    assert create.contents == "static\n"
    assert create.ttl == "120s"
    generate = aio.models.generate_content.call_args.kwargs
    assert generate["contents"] == "next"
    config = generate["config"]
    assert config.cached_content == "cached/1"
    assert config.system_instruction is None
    assert config.response_json_schema == Out.model_json_schema()
    assert config.response_mime_type == "application/json"
    assert config.thinking_config.thinking_level == "MINIMAL"
    assert first.usage["cached"] == 4100
    assert first.usage["prefix"] == 4100 and backend.prefix_tokens == {"fact": 4100}  # D-366


@pytest.mark.asyncio
@pytest.mark.parametrize("model,tokens", [("gemini-3.8-flash", 4095), ("gemini-2.5-flash", 2047)])
async def test_short_prefix_negative_cache(backend, model, tokens):
    backend._client.aio.models.count_tokens.return_value.total_tokens = tokens
    req = request(model=model)
    await backend.generate(req, 2500)
    await backend.generate(req, 2500)
    backend._client.aio.models.count_tokens.assert_awaited_once()
    backend._client.aio.caches.create.assert_not_awaited()
    assert backend._client.aio.models.generate_content.call_args.kwargs["contents"] == req.user_message


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"cache_prefix": ""}, {"session_id": None}, {"cache_prefix": "incorrect"}, {"model": "unknown"},
])
async def test_ineligible_request_skips_cache(backend, changes):
    await backend.generate(request(**changes), 2500)
    backend._client.aio.models.count_tokens.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_cache(backend):
    backend._context_cache = False
    await backend.generate(request(), 2500)
    backend._client.aio.models.count_tokens.assert_not_awaited()


@pytest.mark.asyncio
async def test_changed_prefix_and_expiry_recreate(backend):
    await backend.generate(request(), 2500)
    await backend.generate(request(cache_prefix="new\n", user_message="new\ndynamic"), 2500)
    assert backend._client.aio.caches.create.await_count == 2
    for entry in backend._caches.values():
        entry.expires_at = 0
    await backend.generate(request(), 2500)
    assert backend._client.aio.caches.create.await_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["count", "create", "use"])
async def test_cache_errors_fall_back_and_cool_down(backend, stage):
    aio = backend._client.aio
    if stage == "count":
        aio.models.count_tokens.side_effect = RuntimeError("count failed")
    elif stage == "create":
        aio.caches.create.side_effect = RuntimeError("create failed")
    else:
        reply = aio.models.generate_content.return_value
        aio.models.generate_content.side_effect = [RuntimeError("use failed"), reply, reply]
    req = request()
    assert (await backend.generate(req, 2500)).text == '{"answer":"ok"}'
    await backend.generate(req, 2500)
    aio.models.count_tokens.assert_awaited_once()
    call = aio.models.generate_content.call_args.kwargs
    assert call["contents"] == req.user_message
    assert call["config"].system_instruction == "system"
    assert call["config"].cached_content is None


@pytest.mark.asyncio
async def test_preparation_timeout_leaves_generation_budget(backend):
    async def slow(**kwargs):
        await asyncio.sleep(10)
    backend._client.aio.models.count_tokens.side_effect = slow
    reply = await asyncio.wait_for(backend.generate(request(), 100), 0.5)
    assert reply.text == '{"answer":"ok"}'
    assert backend._client.aio.models.generate_content.call_args.kwargs["contents"] == request().user_message


@pytest.mark.asyncio
async def test_singleflight(backend):
    async def count(**kwargs):
        await asyncio.sleep(0)
        return SimpleNamespace(total_tokens=4100)
    backend._client.aio.models.count_tokens.side_effect = count
    await asyncio.gather(*(backend.generate(request(), 2500) for _ in range(3)))
    backend._client.aio.models.count_tokens.assert_awaited_once()
    backend._client.aio.caches.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancellation_propagates(backend):
    backend._client.aio.models.count_tokens.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await backend.generate(request(), 2500)
    backend._client.aio.models.generate_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_mock_ignores_cache_metadata(tmp_path):
    backend = MockBackend(tmp_path)
    reply = await backend.generate(request(mock_fallback=lambda req: {"answer": req.user_message}), 2500)
    assert Out.model_validate_json(reply.text).answer == request().user_message


@pytest.mark.asyncio
async def test_slow_creation_is_not_cancelled_and_serves_later_calls(backend):
    """D-130: a creation slower than the caller's budget keeps running; the next call uses the cache.
    (wait_for used to cancel it, so the fact checker never got a cache: 202 failures in one eval run.)"""
    async def slow_create(**kwargs):
        await asyncio.sleep(0.3)
        return SimpleNamespace(name="cached/slow")
    backend._client.aio.caches.create.side_effect = slow_create
    req = request()
    await backend.generate(req, 1000)  # budget 0.2 s: this call runs uncached
    assert backend._client.aio.models.generate_content.call_args.kwargs["contents"] == req.user_message
    await asyncio.sleep(0.2)
    await backend.generate(req, 1000)
    assert backend._client.aio.models.generate_content.call_args.kwargs["config"].cached_content == "cached/slow"
    backend._client.aio.caches.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_sessions_with_the_same_prefix_share_one_cache(backend):
    await backend.generate(request(session_id="ses_a"), 2500)
    await backend.generate(request(session_id="ses_b"), 2500)
    backend._client.aio.caches.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_creation_failure_logs_its_reason(backend, caplog):
    backend._client.aio.caches.create.side_effect = RuntimeError("quota exceeded for cached contents")
    await backend.generate(request(), 2500)
    await asyncio.sleep(0)
    assert "context cache creation failed for fact: RuntimeError: quota exceeded" in caplog.text
