"""D-310: eval rows carry every agent's token usage. D-432: the COMPLIANCE_DOCS tests went with that switch."""
from __future__ import annotations


from .judge_fakes import CREAM, ScriptedBackend


class _Record(ScriptedBackend):
    def __init__(self):
        super().__init__()
        self.reqs, self.warmed = [], []

    async def generate(self, req, timeout_ms):
        self.reqs.append(req)
        return await super().generate(req, timeout_ms)

    async def warm_cache(self, req):
        self.warmed.append(req)


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
