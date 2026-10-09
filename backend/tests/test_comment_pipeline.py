"""Comment path end to end inside one process (mock LLM with rule-based fallbacks)."""
from __future__ import annotations

import pytest

from app.models.session import Comment, Message, QuestionGroup
from app.pipelines import comments as ops
from app.pipelines.runtime import ActionError, RateLimited
from app.providers.llm import LLMError

from .helpers import live_runtime, make_ctx, say

CREAM = "cream_hydra_barrier"


@pytest.fixture
async def rt(tmp_path):
    ctx = make_ctx(tmp_path)  # empty fixture dir: agents use their rule-based fallbacks
    runtime = await live_runtime(ctx)
    yield runtime
    ctx.runtimes.shutdown()
    ctx.scheduler.shutdown()


async def groups(rt) -> list[QuestionGroup]:
    return await rt.groups()


async def messages(rt) -> list[Message]:
    return await rt.ctx.store.query(rt.path("messages"), Message, order_by="created_at")


class FakeArmor:
    """Model Armor stand-in (D-125): blocks texts with "ignore previous", records every call."""

    def __init__(self, fail: Exception | None = None, delay_s: float = 0.0):
        self.seen: list[str] = []
        self.fail, self.delay_s = fail, delay_s

    async def screen(self, text):
        self.seen.append(text)
        if self.delay_s:
            await __import__("asyncio").sleep(self.delay_s)
        if self.fail:
            raise self.fail
        return ("blocked", "pi_and_jailbreak") if "ignore previous" in text.lower() else ("pass", "no match")


async def armored(rt, armor):
    rt.ctx.armor = armor
    return rt


async def test_d206_an_unknown_armor_result_is_not_a_pass(monkeypatch):
    from app.providers import armor as armor_mod

    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"sanitizationResult": {}}

    client = armor_mod.ModelArmorClient("p", "us-central1", "t")

    async def post(*_a, **_k):
        return Resp()

    async def token():
        return "x"

    monkeypatch.setattr(client._http, "post", post)
    monkeypatch.setattr(client, "_token", token)
    verdict, _ = await client.screen("hello")
    assert verdict == "unscreened"


def _triage_recorder():
    """The triage prompts the model received (D-157)."""
    from .judge_fakes import ScriptedBackend

    class Recorder(ScriptedBackend):
        def __init__(self):
            super().__init__()
            self.triage_messages: list[str] = []

        async def generate(self, req, timeout_ms):
            if req.agent == "comment_triage":
                self.triage_messages.append(req.user_message)
            return await super().generate(req, timeout_ms)
    return Recorder()


def test_a_short_comments_triage_cache_entry_belongs_to_its_host_line():
    from app.logic.cache import triage_cache_key

    assert triage_cache_key("50 can?", CREAM) == triage_cache_key("50 can?", CREAM, None)  # unchanged without a line
    assert triage_cache_key("50 can?", CREAM, "Spend over S$60 for the pouch.") != triage_cache_key("50 can?", CREAM)


def test_the_batch_triage_carries_each_comments_host_line():
    from app.agents.inputs import comments_json

    items = comments_json([("50 can?", CREAM, "Spend over S$60 for the pouch."), ("price?", CREAM, None)], 300)
    assert [i["recent_host_line"] for i in items] == ["Spend over S$60 for the pouch.", None]


def _composer_backend(failures: int):
    """The composer times out `failures` times, then drafts as usual (D-157)."""
    from app.providers.llm import LLMTimeout

    from .judge_fakes import ScriptedBackend

    class Flaky(ScriptedBackend):
        def __init__(self):
            super().__init__()
            self.left = failures

        async def generate(self, req, timeout_ms):
            if req.agent == "answer_composer" and self.left:
                self.left -= 1
                raise LLMTimeout("deadline")
            return await super().generate(req, timeout_ms)
    return Flaky()
