"""D-314 (eval): JUDGE_TEMPERATURE and JUDGE_SEED set the live judges' sampling (compliance judge, fact checker,
context judge); empty sends nothing (the model's default, D-008). Every call logs what it sent."""
from __future__ import annotations

import pytest

from app.models.session import AgentCall
from app.providers.llm import vertex_config

from .judge_fakes import ScriptedBackend, close_env, speak


class _Record(ScriptedBackend):
    def __init__(self):
        super().__init__()
        self.reqs = []

    async def generate(self, req, timeout_ms):
        self.reqs.append(req)
        return await super().generate(req, timeout_ms)


@pytest.mark.parametrize("temperature, seed, sent", [("", "", (None, None)), ("0", "7", (0.0, 7)),
                                                     ("", "7", (None, 7))])
async def test_d314_the_judges_sampling(temperature, seed, sent):
    from .helpers import live_runtime, make_ctx

    llm = _Record()
    rt = await live_runtime(make_ctx(backend=llm, JUDGE_TEMPERATURE=temperature, JUDGE_SEED=seed))
    try:
        await speak(rt, "It's only thirty-two dollars today.")
        await rt.utterances.drain()
        judged = {r.agent: (r.temperature, r.seed) for r in llm.reqs}
        assert {judged[a] for a in ("compliance_judge", "fact_checker", "context_judge")} == {sent}
        calls = await rt.ctx.store.query(rt.path("agent_calls"), AgentCall)
        assert {(c.temperature, c.seed) for c in calls if c.agent == "fact_checker"} == {sent}  # logged
    finally:
        await close_env(rt)


def test_d314_vertex_config_sends_them_only_when_set():
    from app.models.agent_io import FactRelationOutput
    from app.providers.llm import LLMRequest

    req = LLMRequest(agent="fact_checker", model="m", thinking_level="LOW", prompt_version="v", system_instruction="s",
                     user_message="u", output_model=FactRelationOutput, deadline_ms=5000)
    cfg = vertex_config(req, 5000, {})
    assert cfg.temperature is None and cfg.seed is None
    req.temperature, req.seed = 0.0, 7
    cfg = vertex_config(req, 5000, {})
    assert (cfg.temperature, cfg.seed) == (0.0, 7)
