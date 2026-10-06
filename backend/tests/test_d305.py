"""D-305: the shipped defaults are model-only (verify arm, relation facts, STT-aware prompts, rolling context, no code
meaning rules). The older tests pin the code paths (conftest LEGACY); these run the shipped defaults (SHIPPED) end to
end on the demo pack, with the model's answers scripted (the verifier's mock keeps a candidate)."""
from __future__ import annotations

from .conftest import SHIPPED
from .helpers import say
from .judge_fakes import close_env, events, make_env, speak, violation
from .test_relation import _RelationBackend


async def test_d305_a_compliance_alert_goes_through_the_verifier():
    rt, llm = await make_env(**SHIPPED)
    try:
        line = "This cream cures eczema, honestly."
        llm.judge(line, violations=[violation("ASEAN-2D-DISEASE", "cures eczema")])
        await speak(rt, line)
        await rt.utterances.drain()
        [a] = [a for a in await rt.alerts() if a.kind == "compliance"]
        assert (a.status, a.severity, a.unverified) == ("active", "HIGH", False)
        assert ("verifier", f"{line}|cures eczema") in llm.calls
        # D-308: the regex chip is back by default; it is only the grey chip, the HIGH shows once confirmed
        assert all(e.payload["status"] == "provisional" for e in await events(rt, "alert.created"))
    finally:
        await close_env(rt)


async def test_d305_a_fact_alert_from_the_relation_arm():
    from .helpers import live_runtime, make_ctx

    rt = await live_runtime(make_ctx(backend=_RelationBackend("contradicts"), **SHIPPED))
    try:
        await speak(rt, "It's only thirty-two dollars today.")
        await rt.utterances.drain()
        [a] = [a for a in await rt.alerts() if a.kind == "fact"]
        assert a.correct_value == "S$36.00" and a.evidence_ids and not a.heard_check
    finally:
        await close_env(rt)


async def test_d305_a_failed_compliance_call_gives_the_check_card_without_the_regex():
    rt, llm = await make_env(**(SHIPPED | {"REFLEX_SCAN": False}))  # D-308: an option, not the default
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
    rt, _ = await make_env(**SHIPPED)
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
    with TestClient(create_app(make_settings(DATA_DIR=str(data), ONBOARDING_DIR=str(onb), DEMO_TOOLS_ENABLED=True,
                                             **SHIPPED), llm_backend=ScriptedBackend())) as c:
        s = c.post("/api/demo/reset", json={}).json()
        assert s["release_ids"] == show
