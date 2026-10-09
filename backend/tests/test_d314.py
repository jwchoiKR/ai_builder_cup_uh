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


def test_d314_vertex_config_sends_them_only_when_set():
    from app.models.agent_io import FactRelationOutputV5
    from app.providers.llm import LLMRequest

    req = LLMRequest(agent="fact_checker", model="m", thinking_level="LOW", prompt_version="v", system_instruction="s",
                     user_message="u", output_model=FactRelationOutputV5, deadline_ms=5000)
    cfg = vertex_config(req, 5000, {})
    assert cfg.temperature is None and cfg.seed is None
    req.temperature, req.seed = 0.0, 7
    cfg = vertex_config(req, 5000, {})
    assert (cfg.temperature, cfg.seed) == (0.0, 7)


@pytest.mark.parametrize("field, value", [("JUDGE_TEMPERATURE", "oops"), ("JUDGE_SEED", "1.5")])
def test_d314_a_bad_sampling_value_fails_at_startup(field, value):
    from pydantic import ValidationError

    from .conftest import make_settings

    with pytest.raises(ValidationError):
        make_settings(**{field: value})
    assert make_settings(**{field: " 7 "}).model_dump()[field] == "7"
