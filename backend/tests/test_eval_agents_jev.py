"""Offline checks for experimental dispatch ordering and latency accounting."""
from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("structure", ["jev_selective", "jev_tiered", "gemini_selective", "gemini_tiered"])
@pytest.mark.parametrize("failed", [False, True])
async def test_jev_dispatch_and_timing(monkeypatch, settings, structure, failed):
    import app.agents.fact_checker as fc

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    # The historical eval script disables the claim filter to retain raw model output (D-389: as_given).
    original = fc.as_given
    try:
        mod = importlib.import_module("eval_agents")
    finally:
        fc.as_given = original
    started = set()
    closed = []

    class Agent:
        def __init__(self, name, latency):
            self.name, self.latency = name, latency

        def build_values(self, inp):
            return {key: [] for key in ("active_alerts_json", "open_questions_json",
                                       "prompter_points_json", "host_cues_json")}

        async def run(self, *args, **kwargs):
            started.add(self.name)
            return SimpleNamespace(status="ok", output=None, latency_ms=self.latency)

    class Client:
        async def warm_up(self):
            return {}

        async def aclose(self):
            closed.append("llm")

    class Router(Client):
        async def route(self, state):
            await asyncio.sleep(0)
            assert started == ({"compliance", "facts"} if structure.endswith("_tiered") else set())
            probs = None if failed else {"compliance": 0.0, "facts": 0.0, "context": 0.9}
            return probs, 7, "timeout" if failed else "ok"

        async def aclose(self):
            closed.append("jev")

    async def passages(*args, **kwargs):
        return []

    monkeypatch.setattr(mod, "get_settings", lambda: settings)
    monkeypatch.setattr(mod, "get_threshold", lambda: 0.05)
    monkeypatch.setattr(mod, "make_client", lambda _: (Client(), None))
    monkeypatch.setattr(mod, "JevRouter", Router)
    monkeypatch.setattr(mod, "GeminiRouter", Router)
    monkeypatch.setattr(mod, "UtteranceJudge", lambda *a: Agent("judge", 0))
    monkeypatch.setattr(mod, "ComplianceJudge", lambda *a: Agent("compliance", 11))
    monkeypatch.setattr(mod, "ContextJudge", lambda *a: Agent("context", 13))
    monkeypatch.setattr(mod, "FactChecker", lambda *a: Agent("facts", 17))
    monkeypatch.setattr(mod, "gather_fact_passages", passages)
    monkeypatch.setattr(mod, "load_cases", lambda _: [{
        "case_id": "U25", "current_product_id": "cream_hydra_barrier",
        "utterance": "Hello everyone!", "expected": {},
    }])
    row, = await mod.run(structure, 1, 1)
    urgent = failed or structure.endswith("_tiered")
    assert row["route"] == {"compliance": urgent, "facts": urgent, "context": True}
    assert row["ctx_ms"] == 20
    assert row["comp_ms"] == (11 if structure.endswith("_tiered") else 18 if failed else 7)
    assert row["facts_ms"] == (17 if structure.endswith("_tiered") else 24 if failed else 7)
    assert row["router_status"] == ("timeout" if failed else "ok")
    assert row["overrides"] == []
    assert set(closed) == {"llm", "jev"}
