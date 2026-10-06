"""D-310 (COMPLIANCE_DOCS): the compliance judge's cached prefix also holds the on-air product's documents, so names
said as sound-alikes can be matched and the prefix reaches the cache minimum; each product's cache is warmed at the
start of the show. Eval rows carry every agent's token usage."""
from __future__ import annotations

import pytest

from .judge_fakes import AMPOULE, CREAM, ScriptedBackend, close_env, speak


class _Record(ScriptedBackend):
    def __init__(self):
        super().__init__()
        self.reqs, self.warmed = [], []

    async def generate(self, req, timeout_ms):
        self.reqs.append(req)
        return await super().generate(req, timeout_ms)

    async def warm_cache(self, req):
        self.warmed.append(req)


@pytest.mark.parametrize("docs", [False, True])
async def test_d310_the_documents_in_the_compliance_prefix(docs):
    from .helpers import live_runtime, make_ctx

    llm = _Record()
    rt = await live_runtime(make_ctx(backend=llm, COMPLIANCE_DOCS=docs))
    try:
        await rt.ctx.scheduler.idle()
        await speak(rt, "It feels light and soft.")
        await rt.utterances.drain()
        [req] = [r for r in llm.reqs if r.agent == "compliance_judge"]
        assert req.user_message.startswith('<data name="PRODUCT_DOCUMENTS">') is docs
        assert req.cache_prefix.startswith('<data name="PRODUCT_DOCUMENTS">') is docs
        assert ("PRODUCT_DOCUMENTS (and any files" in req.system_instruction) is docs
        if docs:
            assert "Live broadcast price" in req.cache_prefix  # the on-air product's passages
            warmed = {r.cache_prefix: r for r in llm.warmed if r.agent == "compliance_judge"}
            assert len(warmed) == 2  # every product of the show, not only the first
            assert req.cache_prefix in warmed  # the live call meets the warmed cache
            assert warmed[req.cache_prefix].system_instruction == req.system_instruction
        else:
            assert not any(r.agent == "compliance_judge" for r in llm.warmed)
    finally:
        await close_env(rt)


async def test_d310_each_product_gets_its_own_documents():
    from .helpers import live_runtime, make_ctx

    rt = await live_runtime(make_ctx(backend=ScriptedBackend(), COMPLIANCE_DOCS=True))
    try:
        cream, _ = rt.utterances.compliance.documents(CREAM)
        ampoule, _ = rt.utterances.compliance.documents(AMPOULE)
        assert CREAM in cream and AMPOULE not in cream and AMPOULE in ampoule
    finally:
        await close_env(rt)


async def test_d310_eval_rows_carry_every_agent_s_usage(monkeypatch):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import eval_adversarial

    from .helpers import make_ctx

    real_sleep = __import__("asyncio").sleep
    monkeypatch.setattr(__import__("asyncio"), "sleep", lambda _s: real_sleep(0))
    ctx = make_ctx(backend=ScriptedBackend())
    try:
        row = await eval_adversarial.run_case(ctx, {"case_id": "U", "type": "t", "utterance": "It feels light.",
                                                    "current_product_id": CREAM, "expected": {"risky": False}}, 0)
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
    agents = {c["agent"] for c in row["calls"] if "usage" in c}
    assert {"compliance_judge", "fact_checker"} <= agents
