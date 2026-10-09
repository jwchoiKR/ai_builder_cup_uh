"""D-304: each code rule that judges meaning, switchable against the model's own judgment. Defaults keep today's
behaviour; each test shows the switch changing the one thing it names. Made-up lines."""
from __future__ import annotations

import pytest

from .helpers import say
from .judge_fakes import AMPOULE, CREAM, close_env, events, make_env, speak, violation

QUALIFIED_LINE = "Skin hydration went up 45% right after one use."


async def test_d304_correction_by_the_judge_alone():
    rt, llm = await make_env(REFLEX_ON_FAIL="alert")  # D-390: the judge's listed correction is the only path
    try:
        line = "It kills the bacteria on your skin."
        llm.judge(line, violations=[violation("ASEAN-3-SKIN-ANTIMICROBIAL")])
        await speak(rt, line)
        [a] = await rt.alerts()
        llm.judge("Sorry.", corrects=[a.alert_id], utterance_type="correction")  # D-089: words alone say no
        await speak(rt, "Sorry.")
        [a] = await rt.alerts()
        assert a.status == "corrected"
    finally:
        await close_env(rt)


async def test_d304_verbal_check_by_the_context_judge():
    from app.agents.split_judges import ContextJudge
    from app.models.agent_io import ContextOutput, ContextOutputB

    for check, model in (("code", ContextOutput), ("judge", ContextOutputB)):
        rt, _ = await make_env(VERBAL_CHECK=check)
        try:
            j = ContextJudge(rt.ctx.llm, rt.ctx.prompts, rt.catalog, rt.reflex)
            assert issubclass(j.output_model_b if j.b else j.output_model, model)  # D-415: with the switch naming
            assert ("`answer.hedged`" in j.system_instruction) is (check == "judge")
            assert rt.utterances._by_judge() is (check == "judge")
        finally:
            await close_env(rt)


@pytest.mark.parametrize("line", ["This cream cures eczema.", "It feels light and soft."])
async def test_d304_d410_a_failed_line_gets_the_card_and_no_alert(line):
    rt, llm = await make_env()
    try:
        llm.fail("utterance_judge", line)
        await speak(rt, line)
        await rt.utterances.drain()
        assert await events(rt, "alert.created") == []  # D-410: no regex pre-scan, no provisional alert
        assert len(await events(rt, "line.check")) == 1
    finally:
        await close_env(rt)


async def test_d304_every_show_product_for_the_judges(catalog):
    from app.agents.fact_checker import gather_fact_passages
    from app.models.session import SwitchState

    class R:  # no local sheets: the catalog's passages
        pass

    for every, has_ampoule in ((False, False), (True, True)):
        ps = await gather_fact_passages(R(), catalog, {}, utterance="It feels light.", on_air=CREAM,
                                        switch=SwitchState(), search_timeout_ms=600, all_products=every)
        assert any(p.product_id == AMPOULE for p in ps) is has_ampoule


def test_d304_comment_product_from_triage(catalog, pack):
    from app.logic.product_mapping import attribute_product

    from .test_mapping_grouping_routing import triage

    intent = pack.intents_by_name["price"]
    line = "How much is the ampoule?"
    assert attribute_product(line, triage(CREAM, "context"), CREAM, catalog, intent) == (AMPOULE, "explicit")
    assert attribute_product(line, triage(CREAM, "context"), CREAM, catalog, intent, by_triage=True) == (CREAM, "context")
    assert attribute_product("price?", triage(None, "unknown"), CREAM, catalog, intent, by_triage=True) == (CREAM, "context")


def test_d304_draft_gate_provenance_only(pack):
    from app.logic.reflex import Reflex
    from app.models.agent_io import ComposerOutput
    from app.pipelines.comments import draft_code_gate

    quote = "Skin hydration immediately after one application: +38% versus before application."
    pid = "DL-CR-01#in-house-test-results#skin-hydration-immediately-after-one-application"
    passages = [p for p in pack.passages if p.product_id == CREAM]
    out = ComposerOutput(answer="It does not cure eczema. It rose 38% right after one use, in our in-house test.",
                         citations=[{"passage_id": pid, "quote": quote}], grounded=True, needs_human=False, reason="")
    kw = dict(arm="A", reflex=Reflex(pack.rules, pack.lexicon), not_approved=[])
    ok, errors = draft_code_gate(out, passages, CREAM, **kw)
    assert not ok and any("restricted phrase" in e for e in errors)  # today: a negated mention blocks it
    assert draft_code_gate(out, passages, CREAM, provenance=True, **kw) == (True, [])
    wrong = out.model_copy(update={"answer": "It rose 40% right after one use."})
    assert draft_code_gate(wrong, passages, CREAM, provenance=True, **kw)[1] == ["number 40 not in a cited quote"]


@pytest.mark.parametrize("mode, label, kinds", [
    ("regex", "purchase", ["purchase"]),  # today: the regex reads "bought"
    ("judge", "purchase", ["purchase"]),
    ("judge", None, []),  # triage's label decides, the regex is not consulted
])
async def test_d304_shout_outs_by_triage(mode, label, kinds):
    rt, llm = await make_env(SHOUTOUT=mode)
    try:
        text = "Just bought two, so excited!!"
        llm.outputs[("comment_triage", text)] = {
            "kind": "reaction", "hide_category": None, "product_id": None, "product_basis": "unknown", "intent": None,
            "condition_slots": {k: None for k in ("person_type", "life_stage", "condition", "combined_with",
                                                  "time_of_day")},
            "canonical_question": "", "group_candidate_id": None, "reason": "scripted"}
        if mode == "judge":
            llm.outputs[("comment_triage", text)]["shoutout"] = label
        await say(rt, "Mei", text)
        assert [s.kind for s in rt.shoutouts] == kinds
    finally:
        await close_env(rt)
