"""Adaptive micro-batch of comment triage (PLANNING 5.1.2): alone when a slot is free, batched when
comments pile up behind busy slots."""
from __future__ import annotations

import asyncio
import json

import pytest

from app.agents.comment_triage import TriageInput
from app.models.session import AgentCall, Comment
from app.providers.llm import MockBackend, RawReply, mock_key

from .helpers import live_runtime, make_ctx, say

FIRST = "How much is the cream?"
WAITING = ["Is it ok for oily skin?", "Does the ampoule sting?", "Can I use the cream at night?"]
LAST = "Is the cream fragrance free?"


class GatedBackend(MockBackend):
    """Mock backend whose single triage call for one text waits for a gate; can drop batch items."""

    def __init__(self, fixtures_dir, gate_text: str | None = None, drop_from_batch: str | None = None):
        super().__init__(fixtures_dir)
        self.gate_text, self.drop = gate_text, drop_from_batch
        self.gate, self.started = asyncio.Event(), asyncio.Event()

    async def generate(self, req, timeout_ms):
        if req.agent == "comment_triage" and req.mock_primary_text == self.gate_text:
            self.started.set()
            await self.gate.wait()
        reply = await super().generate(req, timeout_ms)
        if req.agent == "comment_triage_batch" and self.drop is not None:
            data = json.loads(reply.text)
            texts = req.mock_primary_text.split("\n")
            data["items"] = [it for it in data["items"] if texts[it["i"]] != self.drop]
            return RawReply(json.dumps(data), model_version=reply.model_version)
        return reply


async def wait_for(predicate):
    async def spin():
        while not await predicate():
            await asyncio.sleep(0)
    await asyncio.wait_for(spin(), 2)


async def calls(rt) -> list[AgentCall]:
    return [c for c in await rt.ctx.store.query(rt.path("agent_calls"), AgentCall) if c.agent.startswith("comment_triage")]


async def analysed(rt, comments: list[Comment]) -> bool:
    got = [await rt.get_comment(c.comment_id) for c in comments]
    return all(c.analysis_id for c in got)


@pytest.fixture
async def env(tmp_path, request):
    backend = GatedBackend(tmp_path, **getattr(request, "param", {"gate_text": FIRST}))
    ctx = make_ctx(backend=backend, TRIAGE_CONCURRENCY=1, TRIAGE_MAX_BATCH=3)
    rt = await live_runtime(ctx)
    yield rt, backend
    backend.gate.set()
    ctx.runtimes.shutdown()
    ctx.scheduler.shutdown()


async def test_alone_when_free_batched_when_slots_are_busy(env):
    rt, backend = env
    first = await say(rt, "Lee", FIRST, wait=False)
    await asyncio.wait_for(backend.started.wait(), 2)
    waiting = [await say(rt, f"V{i}", t, wait=False) for i, t in enumerate(WAITING)]
    last = await say(rt, "Zoe", LAST, wait=False)
    backend.gate.set()
    await wait_for(lambda: analysed(rt, [first, *waiting, last]))
    await rt.ctx.scheduler.idle()

    assert [c.agent for c in await calls(rt)] == ["comment_triage", "comment_triage_batch", "comment_triage"]
    groups = {g.canonical_question for g in await rt.groups()}
    assert {FIRST, *WAITING, LAST} <= groups  # rule-based canonical questions: every comment was grouped


@pytest.mark.parametrize("env", [{"gate_text": FIRST, "drop_from_batch": WAITING[1]}], indirect=True)
async def test_item_missing_from_the_batch_is_triaged_alone(env):
    rt, backend = env
    first = await say(rt, "Lee", FIRST, wait=False)
    await asyncio.wait_for(backend.started.wait(), 2)
    waiting = [await say(rt, f"V{i}", t, wait=False) for i, t in enumerate(WAITING)]
    backend.gate.set()
    await wait_for(lambda: analysed(rt, [first, *waiting]))
    await rt.ctx.scheduler.idle()

    agents = [c.agent for c in await calls(rt)]
    assert agents == ["comment_triage", "comment_triage_batch", "comment_triage"]
    assert WAITING[1] in {g.canonical_question for g in await rt.groups()}


async def test_batched_mock_replays_the_recorded_single_fixture(rt_free, tmp_path):
    rt = rt_free
    out = {"kind": "question", "hide_category": None, "product_id": "cream_hydra_barrier", "product_basis": "context",
           "intent": "texture", "condition_slots": {"person_type": None, "life_stage": None, "condition": None,
                                                    "combined_with": None, "time_of_day": None},
           "canonical_question": "Is it sticky?", "group_candidate_id": None, "reason": "recorded fixture"}
    path = tmp_path / "comment_triage" / f"{mock_key('comment_triage', 'so sticky or not', 'default')}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(out), encoding="utf-8")
    inps = [TriageInput(text=t, context_product_id="cream_hydra_barrier", session_id=rt.sid)
            for t in ("so sticky or not", FIRST)]
    a, b = await rt.triage.run_batch(inps, deadline_ms=5000)
    assert a.output.reason == "recorded fixture" and a.output.intent == "texture"
    assert b.output.reason == "rule-based" and b.output.intent == "price"


@pytest.fixture
async def rt_free(tmp_path):
    ctx = make_ctx(tmp_path)
    rt = await live_runtime(ctx)
    yield rt
    ctx.runtimes.shutdown()
    ctx.scheduler.shutdown()


def test_batch_prompt_reuses_the_single_comment_rules_and_examples(prompts):
    single, batch = prompts["comment_triage"].system_instruction, prompts["comment_triage_batch"].system_instruction
    rules, examples = single.split("\n\n## EXAMPLES", 1)
    assert batch.startswith(rules) and batch.endswith(examples)
    assert "### Several comments in one request" in batch
    assert "{{comments_json}}" in prompts["comment_triage_batch"].user_template
