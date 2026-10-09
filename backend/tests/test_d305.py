"""D-305, D-434: the production defaults end to end on the demo pack, with the model's answers scripted: a fact
alert from the relation arm, a failed compliance call gives the check card and no alert, a viewer question is grouped,
and the demo show starts."""
from __future__ import annotations

import json
import re

from .helpers import say
from .judge_fakes import CREAM, ScriptedBackend, close_env, events, make_env, speak


class _V5Facts(ScriptedBackend):
    """The fact checker answers in raw production JSON (v5: stance, evidence by SOURCE sentence id, relation, say),
    citing the prompter snapshot's live price sentence."""

    async def generate(self, req, timeout_ms):
        if req.agent != "fact_checker":
            return await super().generate(req, timeout_ms)
        from app.providers.llm import RawReply

        m = re.search(r'\["(S\d+)",\s*"Live price: S\$36\.00"\]', req.user_message)
        claims = [] if m is None or "thirty-two" not in req.mock_primary_text else [{
            "span": "thirty-two dollars", "stance": "HOST_ASSERTS", "product_id": CREAM, "field": "price",
            "stated_value": "S$32", "evidence": [m.group(1)], "source_value": "S$36.00", "relation": "contradicts",
            "correct_value": "S$36.00", "say": "Sorry, the live price is S$36.00."}]
        return RawReply(json.dumps({"claims": claims}), model_version="scripted")


async def test_d305_a_fact_alert_from_the_relation_arm():
    from .helpers import live_runtime, make_ctx

    rt = await live_runtime(make_ctx(backend=_V5Facts()))
    try:
        await speak(rt, "It's only thirty-two dollars today.")
        await rt.utterances.drain()
        [a] = [a for a in await rt.alerts() if a.kind == "fact"]
        assert a.correct_value == "S$36.00" and a.evidence_ids and a.say == "Sorry, the live price is S$36.00."
        assert a.passage_id == "DL-CR-01#prompter#live-price" and a.quote == "Live price: S$36.00"
    finally:
        await close_env(rt)


async def test_d305_a_failed_compliance_call_gives_the_check_card_without_the_regex():
    rt, llm = await make_env()
    try:
        line = "It feels light and soft."
        llm.fail("utterance_judge", line)
        await speak(rt, line)
        await rt.utterances.drain()
        assert len(await events(rt, "line.check")) == 1
        assert [a for a in await rt.alerts() if a.kind == "compliance"] == []
    finally:
        await close_env(rt)


async def test_d305_a_viewer_question_is_grouped():
    rt, _ = await make_env()
    try:
        await say(rt, "Mei", "How much is the cream today?")
        assert len(await rt.groups()) == 1
    finally:
        await close_env(rt)


def test_d305_the_demo_show_starts(tmp_path):
    import json

    from fastapi.testclient import TestClient

    from app.main import create_app

    from .helpers import make_settings
    from .judge_fakes import ScriptedBackend
    from .test_clean_base import clean_data

    data, onb = clean_data(tmp_path), tmp_path / "onb"
    show = json.loads((data / "demo_release" / "show.json").read_text(encoding="utf-8"))["release_ids"]
    with TestClient(create_app(make_settings(DATA_DIR=str(data), ONBOARDING_DIR=str(onb), DEMO_TOOLS_ENABLED=True),
                               llm_backend=ScriptedBackend())) as c:
        s = c.post("/api/demo/reset", json={}).json()
        assert s["release_ids"] == show
