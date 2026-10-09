"""Mock-only checks for purpose routing, deadlines and resource ownership."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError


@pytest.fixture
def module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    from experiments import gemini_router

    return gemini_router


class Client:
    fast = SimpleNamespace(model="gemini-3.5-flash-lite", thinking_level="MINIMAL")

    def __init__(self, result=None, error=None):
        self.result, self.error = result, error
        self.requests = []
        self.closed = False

    async def call(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.result

    async def aclose(self):
        self.closed = True


async def test_request_boolean_mapping_and_shared_ownership(module):
    out = module.RouterOutput(compliance=True, facts=False, context=True, reason="test")
    client = Client(SimpleNamespace(status="ok", output=out, latency_ms=12))
    router = module.GeminiRouter(client)
    state = {"utterance": "A sample sentence", "open_questions": []}
    assert await router.route(state) == ({"compliance": 1.0, "facts": 0.0, "context": 1.0}, 12, "ok")
    request, = client.requests
    assert request.model == client.fast.model
    assert request.thinking_level == "MINIMAL"
    assert request.deadline_ms == 1500
    assert request.output_model is module.RouterOutput
    assert request.user_message.count("<data>") == 1
    rendered = request.user_message.split("<data>")[1].split("</data>")[0]
    assert json.loads(rendered) == state
    await router.aclose()
    assert not client.closed


@pytest.mark.parametrize("status", ["timeout", "error", "invalid"])
async def test_failed_results_fail_open(module, status):
    client = Client(SimpleNamespace(status=status, output=None, latency_ms=4))
    probs, elapsed, outcome = await module.GeminiRouter(client).route({"utterance": "test"})
    assert probs is None
    assert elapsed == 4
    assert outcome == ("timeout" if status == "timeout" else "error")


@pytest.mark.parametrize("error,status", [(TimeoutError(), "timeout"), (RuntimeError(), "error")])
async def test_raised_errors_fail_open(module, error, status):
    probs, _, outcome = await module.GeminiRouter(Client(error=error)).route({"utterance": "test"})
    assert probs is None
    assert outcome == status


async def test_outer_deadline_and_cached_warmup(module, monkeypatch):
    class Slow(Client):
        async def call(self, request):
            self.requests.append(request)
            await asyncio.sleep(1)

    monkeypatch.setattr(module, "GEMINI_ROUTER_DEADLINE_MS", 1)
    client = Slow()
    router = module.GeminiRouter(client)
    first, second = await asyncio.gather(router.warm_up(), router.warm_up())
    assert first == second
    assert first[0] is None and first[2] == "timeout"
    assert len(client.requests) == 1


async def test_owned_client_closed_and_retries_disabled(module, monkeypatch):
    import eval_common  # D-435: the helpers moved from run_eval
    from app.config import Settings

    client = Client(SimpleNamespace(status="error", output=None, latency_ms=0))
    client._settings = Settings(LLM_RETRY_ON_5XX=1)
    monkeypatch.setattr(eval_common, "make_client", lambda record: (client, None))
    router = module.GeminiRouter()
    assert client._settings.LLM_RETRY_ON_5XX == 0
    await router.aclose()
    assert client.closed


@pytest.mark.parametrize("value", ["false", 0, 1, None])
def test_boolean_schema_is_strict(module, value):
    with pytest.raises(ValidationError):
        module.RouterOutput(compliance=value, facts=False, context=False, reason="test")


def test_prompt_examples_do_not_reuse_eval_utterances(module):
    from app.config import get_settings

    prompt = (Path(module.__file__).parent / "prompts" / "router_purpose.md").read_text(encoding="utf-8")
    for filename in ("utterance_cases.jsonl", "route_cases.jsonl"):
        path = get_settings().data_path / "eval" / filename
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    utterance = json.loads(line)["utterance"]
                    assert utterance not in prompt
    for section in ("SYSTEM INSTRUCTION", "USER MESSAGE TEMPLATE", "OUTPUT SCHEMA", "EXAMPLES"):
        assert section in prompt
