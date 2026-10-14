"""D-466: the fact checker runs on gemini-3.8-flash LOW by default (the compliance and context judges stay on
Flash-Lite). Its context cache still applies, and a 504 or our own timeout still reaches the operator's failure cards
with the code and the deadline. Made-up lines only."""
from __future__ import annotations

import pytest

from app.providers.llm import LLMTimeout, VertexBackend, _coded

from .helpers import make_ctx
from .judge_fakes import close_env, speak
from .test_context_cache import backend, request  # noqa: F401 (the fixture)
from .test_d462 import show
from .test_d464 import LINE, _Failing, failures


def test_the_fact_checker_runs_on_3_8_flash_and_the_judges_on_flash_lite():
    llm = make_ctx().llm
    assert (llm.facts.model, llm.facts.thinking_level) == ("gemini-3.8-flash", "LOW")
    assert llm.compliance.model == llm.context.model == "gemini-3.5-flash-lite"


async def test_its_context_cache_is_created_and_used(backend: VertexBackend):  # noqa: F811
    await backend.generate(request(model="gemini-3.8-flash"), 2500)
    aio = backend._client.aio
    assert aio.caches.create.call_args.kwargs["model"] == "gemini-3.8-flash"
    assert aio.models.generate_content.call_args.kwargs["config"].cached_content == "cached/1"


@pytest.mark.parametrize("error, status", [(lambda: _coded(LLMTimeout("504 DEADLINE_EXCEEDED"), 504), 504),
                                           (lambda: LLMTimeout("ReadTimeout"), None)])
async def test_a_504_or_our_own_timeout_reaches_the_cards_with_its_code(error, status):
    rt = await show(_Failing({"fact_checker": error}))
    try:
        await speak(rt, LINE)
        await rt.utterances.drain()
        got = (await failures(rt))["fact_checker"]
        assert (got["cause"], got["http_status"]) == ("timeout", status)
        assert 0 < got["deadline_ms"] <= rt.settings.FACT_LATE_MS  # what is left of the line's 5 s
    finally:
        await close_env(rt)
