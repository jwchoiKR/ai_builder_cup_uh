"""Event-gated races: no model calls or timing-dependent sleeps."""
from __future__ import annotations

import asyncio

import pytest

from .helpers import live_runtime, make_ctx
from .judge_fakes import ScriptedBackend, close_env, events, speak, violation, price_contradiction, claim, AMPOULE
from app.pipelines.utterances import operator_switch, undo_switch


class GatedBackend(ScriptedBackend):
    def __init__(self):
        super().__init__()
        self.gates = {}
        self.started = {}

    def block(self, agent, text):
        key = (agent, text)
        self.gates[key] = asyncio.Event()
        self.started[key] = asyncio.Event()
        return self.gates[key], self.started[key]

    async def generate(self, req, timeout_ms):
        key = (req.agent, req.mock_primary_text)
        if key in self.gates:
            self.started[key].set()
            await self.gates[key].wait()
        return await super().generate(req, timeout_ms)


@pytest.fixture
async def env():
    llm = GatedBackend()
    rt = await live_runtime(make_ctx(backend=llm))
    yield rt, llm
    for gate in llm.gates.values():
        gate.set()
    await close_env(rt)


async def wait_for(predicate):
    async def spin():
        while not await predicate():
            await asyncio.sleep(0)
    await asyncio.wait_for(spin(), 2)


async def test_three_finals_second_compliance_is_immediate_context_is_ordered(env):
    rt, llm = env
    texts = ['First statement.', 'Second statement.', 'Third statement.']
    gates = []
    for i, text in enumerate(texts):
        llm.judge(text, covered=[f'cr-p{i + 1}'],
                  violations=[violation('ASEAN-3-SKIN-AGEING')] if i == 1 else [])
        gates.append(llm.block('compliance_judge', text))
    context_gate, context_started = llm.block('context_judge', texts[0])
    for text in texts:
        await speak(rt, text, wait=False)
    await asyncio.wait_for(asyncio.gather(*(started.wait() for _, started in gates)), 2)
    gates[1][0].set()

    async def active():
        return any(a.status == 'active' for a in await rt.alerts())
    await wait_for(active)
    assert len(await events(rt, 'transcript.final')) == 3
    # Only the session-start prompter event exists: no context verdict was applied out of order.
    assert not [e for e in await events(rt, 'prompter.updated') if e.payload['covered_point_ids']]
    for gate, _ in gates:
        gate.set()
    context_gate.set()
    await rt.utterances.drain()
    assert (await rt.current_segment()).covered_point_ids == ['cr-p1', 'cr-p2', 'cr-p3']


async def test_late_nonreflex_violation_is_corrected_before_emission(env):
    rt, llm = env
    first = 'An unusual promised benefit.'
    correction = 'It does not make wrinkles disappear.'
    llm.judge(first, violations=[violation('ASEAN-3-SKIN-AGEING', span='make wrinkles disappear')])
    gate, started = llm.block('compliance_judge', first)
    t = await speak(rt, first, wait=False)
    await asyncio.wait_for(started.wait(), 2)
    second = await speak(rt, correction, wait=False)

    async def prepared():
        return (second.transcript_id, 'compliance') in rt.utterances._applied
    await wait_for(prepared)
    gate.set()
    await rt.utterances.drain()
    alerts = [a for a in await rt.alerts() if a.transcript_id == t.transcript_id]
    assert alerts and all(a.status == 'corrected' for a in alerts)
    assert all(e.payload['status'] != 'active' for e in await events(rt, 'alert.created')
               if e.payload['transcript_id'] == t.transcript_id)


async def test_late_context_cannot_change_new_segment(env):
    rt, llm = env
    text = 'An old statement.'
    llm.judge(text, covered=['am-p1'], transition=True, target=AMPOULE, confidence='high')
    gate, started = llm.block('context_judge', text)
    await speak(rt, text, wait=False)
    await asyncio.wait_for(started.wait(), 2)
    new = await operator_switch(rt, AMPOULE)
    gate.set()
    await rt.utterances.drain()
    assert (await rt.current_segment()).segment_id == new.segment_id
    assert (await rt.current_segment()).covered_point_ids == []
    assert (await rt.load_session()).switch.status == 'idle'


async def test_d374_an_older_line_s_late_contradiction_is_applied_as_given(env):
    """D-117 dropped an older line's contradiction once a newer line was judged supported; D-374: no ordering drop."""
    rt, llm = env
    first, second = 'A former price.', 'A corrected price.'
    llm.facts(first, price_contradiction())
    llm.facts(second, claim('price', 'supported'))
    gate, started = llm.block('fact_checker', first)
    await speak(rt, first, wait=False)
    await asyncio.wait_for(started.wait(), 2)
    t = await speak(rt, second, wait=False)

    async def applied():
        return (t.transcript_id, 'facts') in rt.utterances._applied
    await wait_for(applied)
    gate.set()
    await rt.utterances.drain()
    assert [a.status for a in await rt.alerts() if a.kind == 'fact'] == ['active']


async def test_merged_supported_fact_does_not_erase_delayed_fragment(env):
    rt, llm = env
    first, second = 'A former price', 'is thirty-six dollars.'
    joined = f'{first} {second}'
    llm.facts(first, price_contradiction())
    llm.facts(joined, claim('price', 'supported'))
    gate, started = llm.block('fact_checker', first)
    await speak(rt, first, wait=False)
    await asyncio.wait_for(started.wait(), 2)
    t = await speak(rt, second, wait=False)

    async def applied():
        return (t.transcript_id, 'facts') in rt.utterances._applied
    await wait_for(applied)
    gate.set()
    await rt.utterances.drain()
    assert [a for a in await rt.alerts() if a.kind == 'fact' and a.status == 'active']


@pytest.mark.parametrize('mode', ['split3', 'split', 'single'])
async def test_rollback_modes_keep_inference_concurrent(mode):
    llm = GatedBackend()
    rt = await live_runtime(make_ctx(backend=llm, JUDGE_MODE=mode))
    agent = {'split3': 'compliance_judge', 'split': 'utterance_judge', 'single': 'judge_single'}[mode]
    first, second = 'First complete sentence.', 'Second complete sentence.'
    gate, started = llm.block(agent, first)
    try:
        await speak(rt, first, wait=False)
        await asyncio.wait_for(started.wait(), 2)
        t = await speak(rt, second, wait=False)

        async def applied():
            return (t.transcript_id, 'compliance') in rt.utterances._applied
        await wait_for(applied)
        gate.set()
        await rt.utterances.drain()
        assert len(await events(rt, 'transcript.final')) == 2
    finally:
        gate.set()
        await close_env(rt)


async def test_judge_timeout_does_not_block_later_context():
    llm = GatedBackend()
    rt = await live_runtime(make_ctx(backend=llm, JUDGE_TIMEOUT_MS=50))
    first = 'First complete sentence.'
    gate, started = llm.block('compliance_judge', first)
    llm.judge('Second sentence.', covered=['cr-p1'])
    try:
        await speak(rt, first, wait=False)
        await asyncio.wait_for(started.wait(), 2)
        await speak(rt, 'Second sentence.', wait=False)
        await asyncio.wait_for(rt.utterances.drain(), 2)
        assert any(e.payload['status'] == 'timeout' for e in await events(rt, 'judge.failed'))
        assert (await rt.current_segment()).covered_point_ids == ['cr-p1']
    finally:
        gate.set()
        await close_env(rt)


async def test_fact_application_is_idempotent(env):
    from app.models.agent_io import FactCheckOutput
    rt, llm = env
    text = 'A wrong price.'
    llm.facts(text, price_contradiction())
    t = await speak(rt, text)
    before = len(await events(rt, 'alert.created'))
    facts = FactCheckOutput.model_validate({'claims': [price_contradiction()], 'reason': 'again'})
    async with rt.lock:
        await rt.utterances._apply_facts_locked(t, facts, set())
    assert len(await events(rt, 'alert.created')) == before


async def test_new_fact_applies_while_previous_facts_and_own_context_wait(env):
    rt, llm = env
    first, second = 'An earlier statement.', 'A newer wrong price.'
    previous_gate, started = llm.block('fact_checker', first)
    context_gate, _ = llm.block('context_judge', second)
    llm.facts(second, price_contradiction())
    await speak(rt, first, wait=False)
    await asyncio.wait_for(started.wait(), 2)
    t = await speak(rt, second, wait=False)

    async def active():
        return any(a.kind == 'fact' and a.transcript_id == t.transcript_id for a in await rt.alerts())
    await wait_for(active)
    assert not previous_gate.is_set() and not context_gate.is_set()
    previous_gate.set()
    context_gate.set()
    await rt.utterances.drain()


async def test_switch_and_undo_reject_old_context(env):
    rt, llm = env
    text = 'An old statement.'
    llm.judge(text, covered=['cr-p1'])
    gate, started = llm.block('context_judge', text)
    old = await rt.current_segment()
    await speak(rt, text, wait=False)
    await asyncio.wait_for(started.wait(), 2)
    await operator_switch(rt, AMPOULE)
    await undo_switch(rt)
    gate.set()
    await rt.utterances.drain()
    assert (await rt.current_segment()).segment_id == old.segment_id
    assert (await rt.current_segment()).covered_point_ids == []


async def test_merged_rule_deduplicates_late_fragment_failure(env):
    rt, llm = env
    first, second = 'It kills the bacteria on your skin', 'with one application.'
    joined = f'{first} {second}'
    rule = 'ASEAN-3-SKIN-ANTIMICROBIAL'
    llm.fail('compliance_judge', first)
    llm.judge(joined, violations=[violation(rule)])
    gate, started = llm.block('compliance_judge', first)
    await speak(rt, first, wait=False)
    await asyncio.wait_for(started.wait(), 2)
    t = await speak(rt, second, wait=False)

    async def applied():
        return (t.transcript_id, 'compliance') in rt.utterances._applied
    await wait_for(applied)
    gate.set()
    await rt.utterances.drain()
    assert len([a for a in await rt.alerts() if a.rule_id == rule and a.status == 'active']) == 1


async def test_simultaneously_ready_compliance_precedes_facts(env):
    from app.models.agent_io import ComplianceOutput, FactCheckOutput
    from app.providers.llm import AgentResult
    rt, _ = env
    release, comp_started, facts_started = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def compliance(*args, **kwargs):
        comp_started.set()
        await release.wait()
        return AgentResult(status='ok', output=ComplianceOutput.model_validate({
            'compliance': {'violations': [violation('ASEAN-3-SKIN-AGEING')]},
            'correction': {'corrects_alert_ids': []}, 'reason': 'test'}), latency_ms=0, call_id='comp')

    async def facts(*args, **kwargs):
        facts_started.set()
        await release.wait()
        return AgentResult(status='ok', output=FactCheckOutput.model_validate({
            'claims': [price_contradiction()], 'reason': 'test'}), latency_ms=0, call_id='facts')

    rt.utterances.compliance.run = compliance
    rt.utterances._run_facts = facts
    await speak(rt, 'A neutral complete sentence.', wait=False)
    await asyncio.wait_for(asyncio.gather(comp_started.wait(), facts_started.wait()), 2)
    release.set()
    await rt.utterances.drain()
    assert [e.payload['kind'] for e in await events(rt, 'alert.created')] == ['compliance', 'fact']
