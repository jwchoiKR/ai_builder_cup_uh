"""A comment whose triage failed is triaged again shortly, before it goes to the operator as "AI unavailable"."""
from __future__ import annotations

import json

from app.models.session import Comment
from app.providers.llm import LLMTimeout, MockBackend

from .helpers import live_runtime, make_ctx, say


class Flaky(MockBackend):
    """Triage times out for the first `failures` calls, then answers from the mock."""

    def __init__(self, fixtures_dir, failures: int):
        super().__init__(fixtures_dir)
        self.failures, self.triage_calls = failures, 0

    async def generate(self, req, timeout_ms):
        if req.agent == "comment_triage":
            self.triage_calls += 1
            if self.triage_calls <= self.failures:
                raise LLMTimeout("deadline")
        return await super().generate(req, timeout_ms)


async def run(tmp_path, failures: int, retries: int):
    backend = Flaky(tmp_path, failures)
    ctx = make_ctx(backend=backend, TRIAGE_RETRIES=retries, TRIAGE_RETRY_AFTER_MS=5000)
    rt = await live_runtime(ctx)
    return ctx, rt, backend


def close(ctx) -> None:
    ctx.runtimes.shutdown()
    ctx.scheduler.shutdown()


async def test_a_failed_triage_is_tried_again_and_the_question_is_answered(tmp_path):
    ctx, rt, backend = await run(tmp_path, failures=2, retries=2)  # one attempt = the call and its immediate repeat
    try:
        c = await say(rt, "Lee", "How much is the cream?")
        assert (await rt.get_comment(c.comment_id)).kind == "pending" and await rt.groups() == []  # waiting, no group
        assert rt.counters["triage_retries"] == 1
        await ctx.scheduler.advance(5000)
        await ctx.scheduler.idle()
        [g] = await rt.groups()
        assert (g.intent, g.route_reason) == ("price", "intent") and g.status == "auto_answered"
        assert (await rt.get_comment(c.comment_id)).kind == "question"
    finally:
        close(ctx)


async def test_after_the_last_retry_the_comment_goes_to_the_operator(tmp_path):
    ctx, rt, backend = await run(tmp_path, failures=99, retries=2)
    try:
        c = await say(rt, "Lee", "How much is the cream?")
        for _ in range(2):
            await ctx.scheduler.advance(5000)
            await ctx.scheduler.idle()
        [g] = await rt.groups()
        assert (g.route, g.route_reason, g.status) == ("OPERATOR", "ai_unavailable", "needs_review")
        assert rt.counters["triage_retries"] == 2 and backend.triage_calls == 6  # three attempts of two calls
        assert (await rt.get_comment(c.comment_id)).kind == "question"
    finally:
        close(ctx)


async def test_without_retries_the_operator_gets_it_at_once(tmp_path):
    ctx, rt, backend = await run(tmp_path, failures=99, retries=0)
    try:
        await say(rt, "Lee", "How much is the cream?")
        [g] = await rt.groups()
        assert g.route_reason == "ai_unavailable" and rt.counters["triage_retries"] == 0
    finally:
        close(ctx)


# ---- the composer's model call fails ------------------------------------------------------------------


class FlakyComposer(MockBackend):
    def __init__(self, fixtures_dir, failures: int):
        super().__init__(fixtures_dir)
        self.failures, self.calls = failures, 0

    async def generate(self, req, timeout_ms):
        if req.agent == "answer_composer":
            self.calls += 1
            if self.calls <= self.failures:
                raise LLMTimeout("deadline")
        return await super().generate(req, timeout_ms)


async def test_a_failed_draft_is_written_again_before_the_operator_gets_it(tmp_path):
    backend = FlakyComposer(tmp_path, failures=2)  # one attempt = the call and its immediate repeat
    ctx = make_ctx(backend=backend, COMPOSE_RETRIES=1, COMPOSE_RETRY_AFTER_MS=5000)
    rt = await live_runtime(ctx)
    try:
        await say(rt, "Mei", "Where is the cream made?")
        [g] = await rt.groups()
        assert g.status == "composing" and rt.counters["compose_retries"] == 1
        await ctx.scheduler.advance(5000)
        await ctx.scheduler.idle()
        [g] = await rt.groups()
        assert g.status == "auto_answered" and backend.calls == 3
    finally:
        close(ctx)


async def test_a_draft_that_keeps_failing_goes_to_the_operator(tmp_path):
    backend = FlakyComposer(tmp_path, failures=99)
    ctx = make_ctx(backend=backend, COMPOSE_RETRIES=1, COMPOSE_RETRY_AFTER_MS=5000)
    rt = await live_runtime(ctx)
    try:
        await say(rt, "Mei", "Where is the cream made?")
        await ctx.scheduler.advance(5000)
        await ctx.scheduler.idle()
        [g] = await rt.groups()
        assert (g.route, g.route_reason, g.status) == ("OPERATOR", "no_verified_answer", "needs_review")
        assert rt.counters["compose_retries"] == 1 and backend.calls == 4
    finally:
        close(ctx)


# ---- the triage model and its fallback ------------------------------------------------------------------


class SlowQuality(MockBackend):
    """The quality model times out; the fast model answers. Records which model each triage call used."""

    def __init__(self, fixtures_dir):
        super().__init__(fixtures_dir)
        self.models = []

    async def generate(self, req, timeout_ms):
        if req.agent == "comment_triage":
            self.models.append((req.model, req.thinking_level, req.deadline_ms))
            if req.model == "gemini-3.8-flash":
                raise LLMTimeout("deadline")
        return await super().generate(req, timeout_ms)


async def test_triage_runs_on_its_own_model_and_falls_back_to_the_fast_one(tmp_path):
    backend = SlowQuality(tmp_path)
    ctx = make_ctx(backend=backend, TRIAGE_MODEL="gemini-3.8-flash", TRIAGE_THINKING="LOW", TRIAGE_TIMEOUT_MS=10000,
                   TRIAGE_FALLBACK_THINKING="MEDIUM", TRIAGE_FALLBACK_TIMEOUT_MS=8000, TRIAGE_RETRIES=0)
    rt = await live_runtime(ctx)
    try:
        await say(rt, "Lee", "How much is the cream?")
        assert backend.models == [("gemini-3.8-flash", "LOW", 10000), ("gemini-3.5-flash-lite", "MEDIUM", 8000)]
        [g] = await rt.groups()
        assert g.intent == "price" and g.route_reason != "ai_unavailable"
    finally:
        close(ctx)


async def test_without_a_triage_model_both_attempts_use_the_fast_model(tmp_path):
    backend = SlowQuality(tmp_path)
    ctx = make_ctx(backend=backend, TRIAGE_MODEL="", TRIAGE_RETRIES=0)
    rt = await live_runtime(ctx)
    try:
        await say(rt, "Lee", "How much is the cream?")
        assert [m for m, _, _ in backend.models] == ["gemini-3.5-flash-lite"]
    finally:
        close(ctx)
