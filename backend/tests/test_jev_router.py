"""Router wire contract and fail-open guarantees, without external services."""
import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from scripts.experiments import jev_router as jev


def payload(value=0.04):
    return {"answers": {name: {"type": "noul", "noul": value} for name in jev.SPECIALISTS}}


async def test_wire_contract_and_warm_up_once():
    requests = []

    async def respond(request):
        requests.append(request)
        return httpx.Response(200, json=payload())

    router = jev.JevRouter(api_key="test-secret", transport=httpx.MockTransport(respond))
    try:
        await asyncio.gather(router.warm_up(), router.warm_up())
        probs, elapsed, status = await router.route({"utterance": "Hello"})
        assert len(requests) == 2
        assert status == "ok" and elapsed >= 0
        assert probs == dict.fromkeys(jev.SPECIALISTS, 0.04)
        body = json.loads(requests[-1].content)
        assert body["model"] == "typesafe/jev-1.13"
        assert body["provider"] == {"data_collection": "deny"}
        assert set(body["questions"]) == set(jev.SPECIALISTS)
        assert all(q["type"] == "noul" for q in body["questions"].values())
        assert requests[-1].url == "https://openrouter.ai/api/v1/systemone"
    finally:
        await router.aclose()


@pytest.mark.parametrize("value", [True, False, "0.4", None, float("nan"), float("inf"), -0.1, 1.1])
async def test_invalid_probability_fails_open(value):
    router = jev.JevRouter(api_key="test", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=json.dumps(payload(value)))))
    try:
        probs, _, status = await router.route({})
        assert probs is None and status == "error"
        assert all(jev.apply_route(probs, 0.05, {}).values())
    finally:
        await router.aclose()


@pytest.mark.parametrize("body", [{}, {"answers": []}, {"answers": {}},
                                  {"answers": {"compliance": {"type": "score", "noul": 0.5}}}])
async def test_missing_or_wrong_answer_fails_open(body):
    router = jev.JevRouter(api_key="test", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=body)))
    try:
        probs, _, status = await router.route({})
        assert probs is None and status == "error"
    finally:
        await router.aclose()


async def test_whole_call_deadline_and_no_retry(monkeypatch):
    monkeypatch.setattr(jev, "ROUTER_DEADLINE_MS", 20)
    attempts = 0

    async def slow(request):
        nonlocal attempts
        attempts += 1
        await asyncio.sleep(1)
        return httpx.Response(200, json=payload())

    router = jev.JevRouter(api_key="test", transport=httpx.MockTransport(slow))
    try:
        probs, elapsed, status = await router.route({})
        assert probs is None and status == "timeout"
        assert elapsed < 500 and attempts == 1
    finally:
        await router.aclose()


async def test_http_error_is_redacted_and_not_retried(capsys):
    attempts = []

    def fail(request):
        attempts.append(request)
        return httpx.Response(401, text="test-secret")

    router = jev.JevRouter(api_key="test-secret", transport=httpx.MockTransport(fail))
    try:
        result = await router.route({})
        assert result[0] is None and result[2] == "error"
        assert len(attempts) == 1
        assert "test-secret" not in repr(result) + repr(capsys.readouterr())
    finally:
        await router.aclose()


@pytest.mark.parametrize("context,hit,reason", [
    ({}, True, "compliance:reflex"),
    ({"active_alerts": [{}]}, False, "compliance:active_alert"),
    ({"active_fact_alerts": [{}]}, False, "facts:active_alert"),
    ({"open_questions": [{}]}, False, "context:open_questions"),
    ({"switch_state": {"status": "counting"}}, False, "context:switch_counting"),
])
def test_each_override(context, hit, reason):
    reflex = SimpleNamespace(scan=lambda text: [object()] if hit else [])
    forced, reasons = jev.routing_overrides({"utterance": "hello", "context": context}, reflex)
    assert reasons == [reason]
    assert [name for name, enabled in forced.items() if enabled] == [reason.split(":")[0]]
    assert jev.apply_route(dict.fromkeys(jev.SPECIALISTS, 0), 0.05, forced) == forced


def test_inclusive_threshold_and_fail_open():
    assert jev.apply_route({"compliance": 0.05, "facts": 0.049, "context": 0}, 0.05, {}) == {
        "compliance": True, "facts": False, "context": False}
    assert all(jev.apply_route(None, 1, {}).values())


@pytest.mark.parametrize("value", ["NaN", "inf", "-0.1", "1.1", "", "oops"])
def test_invalid_threshold(monkeypatch, value):
    monkeypatch.setenv("JEV_THRESHOLD", value)
    with pytest.raises(ValueError, match="finite number"):
        jev.get_threshold()


def test_threshold_default_and_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(jev, "REPO_DIR", tmp_path)
    monkeypatch.delenv("JEV_THRESHOLD", raising=False)
    assert jev.get_threshold() == 0.05
    (tmp_path / ".env").write_text("JEV_THRESHOLD=0.2\nOPENROUTER_API_KEY=fallback\n")
    assert jev.get_threshold() == 0.2
    monkeypatch.setenv("JEV_THRESHOLD", "0")
    assert jev.get_threshold() == 0
    monkeypatch.setenv("JEV_THRESHOLD", "1")
    assert jev.get_threshold() == 1
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert jev._env("OPENROUTER_API_KEY") == "fallback"
    monkeypatch.setenv("OPENROUTER_API_KEY", "environment")
    assert jev._env("OPENROUTER_API_KEY") == "environment"


def test_state_excludes_labels_and_keeps_latest_context():
    state = jev.build_state({"utterance": "Hello", "expected": {"answer": True},
                            "context": {"recent_transcript": ["old", "latest"],
                                        "open_questions": [{"canonical_question": "How much?"}],
                                        "switch_state": {"status": "counting", "target_product_id": "next"}}},
                           "Current product")
    assert state["previous_line"] == "latest"
    assert state["open_questions"] == ["How much?"]
    assert state["on_air_product"] == "Current product" and state["switch_counting"]
    assert "expected" not in state
