"""D-187 design arms. Arm B: the model returns the meaning (correction quotes, numbers said, hedges, qualifier ids,
shout-out labels) and code only checks it. Arm A stays as it is (every other test runs arm A)."""
from __future__ import annotations

import pytest

from app.agents import arms
from app.config import get_settings
from app.logic.publish import decide
from app.logic.verify import verify_answer
from app.models.agent_io import AnswerLinkB, ComplianceOutputB, ComposerOutput, UtteranceJudgeOutput

from .helpers import say
from .judge_fakes import CREAM, ScriptedBackend, close_env, judge_output, make_env, speak, violation
from .test_publish import ANSWER, LEX, OFFERED, ans, grp, messages, oily_on_host

PROMPTS = get_settings().prompts_path


def test_arm_b_adds_its_prompt_lines_and_requires_its_fields():
    assert arms.system_instruction("BASE", "compliance_judge", "A", PROMPTS) == "BASE"
    b = arms.system_instruction("BASE", "compliance_judge", "B", PROMPTS)
    assert b.startswith("BASE\n\n") and "correction.quotes" in b and "qualified_result_id" in b
    assert arms.system_instruction("BASE", "compliance_judge", "C", PROMPTS) == b  # C is B's family
    assert "numbers_said" in arms.system_instruction("BASE", "context_judge", "B", PROMPTS)
    assert "shoutout" in arms.system_instruction("BASE", "comment_triage_batch", "B", PROMPTS)
    schema = ComplianceOutputB.model_json_schema()["$defs"]
    assert "quotes" in schema["CorrectionB"]["required"] and "qualified_result_id" in schema["ViolationB"]["required"]


def _jo(**link) -> UtteranceJudgeOutput:
    out = UtteranceJudgeOutput.model_validate(judge_output(utterance_type="answer", matched="g1", is_answer=True,
                                                           consistent=True))
    out.answer = AnswerLinkB(**out.answer.model_dump(), **link)
    return out


@pytest.mark.parametrize("link, action", [
    ({"numbers_said": [], "hedged": False}, "post"),
    ({"numbers_said": ["4"], "hedged": False}, "verbal_not_posted"),  # the draft "Yes." has no number
    ({"numbers_said": [], "hedged": True}, "verbal_not_posted"),
])
def test_arm_b_posting_compares_the_judges_numbers_and_hedge(link, action):
    d = decide(_jo(**link), OFFERED, grp(), ans(), lex=LEX, high_alert_active=False, facts=None, by_judge=True,
               utterance="I think maybe four")  # the wording itself is not parsed in arm B
    assert d.action == action


async def test_arm_b_a_correction_counts_only_with_a_quote_from_the_line():
    rt, llm = await make_env(DESIGN_ARM="B")
    try:
        line = "This cream cures eczema."
        llm.judge(line, violations=[violation("ASEAN-2D-DISEASE", "cures eczema")])
        await speak(rt, line)
        [a] = [x for x in await rt.alerts() if x.status == "active"]

        def correction(text: str, quote: str) -> None:
            llm.outputs[("compliance_judge", text)] = {
                "compliance": {"violations": []},
                "correction": {"corrects_alert_ids": [a.alert_id], "quotes": [{"alert_id": a.alert_id, "quote": quote}]},
                "reason": "scripted"}

        wrong = "Let me say that again more carefully."
        correction(wrong, "it does not cure eczema")  # not in the line
        await speak(rt, wrong)
        assert (await rt.get_alert(a.alert_id)).status == "active"
        fix = "Sorry, it does not cure eczema, it helps relieve the feeling of dryness."
        correction(fix, "it does not cure eczema")
        await speak(rt, fix)
        assert (await rt.get_alert(a.alert_id)).status == "corrected"
    finally:
        await close_env(rt)


@pytest.mark.parametrize("arm, status", [("A", "corrected"), ("B", "active")])
async def test_arm_b_saying_the_replacement_corrects_only_through_the_judge(arm, status):
    """Arm A corrects an alert whose replacement wording the host says even if the judge lists nothing (D-098);
    arm B leaves that to the judge."""
    rt, llm = await make_env(DESIGN_ARM=arm)
    try:
        line = "This cream cures eczema."
        llm.judge(line, violations=[violation("ASEAN-2D-DISEASE", "cures eczema",
                                              say="Helps relieve the feeling of dryness.")])
        await speak(rt, line)
        [a] = [x for x in await rt.alerts() if x.status == "active"]
        await speak(rt, "It helps relieve the feeling of dryness.")
        assert (await rt.get_alert(a.alert_id)).status == status
    finally:
        await close_env(rt)


@pytest.mark.parametrize("rid, say", [("cr-t1", "In our in-house test, skin hydration went up 38% right after one "
                                                  "application."), ("nope", None)])
async def test_arm_b_the_qualifier_replacement_is_the_result_the_judge_picked(rid, say):
    rt, llm = await make_env(DESIGN_ARM="B")
    try:
        line = "Skin hydration goes up thirty-eight percent right away."
        v = violation("TEST-QUALIFIER", "goes up thirty-eight percent", severity="MEDIUM") | {
            "qualified_result_id": rid}
        llm.outputs[("compliance_judge", line)] = {"compliance": {"violations": [v]},
                                                   "correction": {"corrects_alert_ids": [], "quotes": []},
                                                   "reason": "scripted"}
        await speak(rt, line)
        alerts = [x for x in await rt.alerts() if x.rule_id == "TEST-QUALIFIER" and x.status == "active"]
        assert [x.say_instead for x in alerts] == ([say] if say else [])
    finally:
        await close_env(rt)


class _SecondCallLinks(ScriptedBackend):
    """The context judge links the line to nothing at first and to the group when asked again."""

    def __init__(self, line: str) -> None:
        super().__init__()
        self.line, self.link, self.n = line, None, 0

    async def generate(self, req, timeout_ms):
        if req.agent == "context_judge" and req.mock_primary_text == self.line and self.link:
            self.n += 1
            data = judge_output(**(dict(utterance_type="answer", matched=self.link, is_answer=True, consistent=True)
                                   if self.n > 1 else {}))
            data = {"answer": data["answer"] | {"numbers_said": [], "hedged": False}, "prompter": data["prompter"],
                    "reason": "scripted"}
            import json

            from app.providers.llm import RawReply
            self.calls.append((req.agent, req.mock_primary_text))
            return RawReply(json.dumps(data), model_version="scripted")
        return await super().generate(req, timeout_ms)


async def test_arm_b_an_unlinked_line_is_asked_about_again_with_every_offered_draft():
    from .helpers import live_runtime, make_ctx

    backend = _SecondCallLinks(ANSWER)
    ctx = make_ctx(backend=backend, DESIGN_ARM="B")
    rt = await live_runtime(ctx)
    try:
        g = await oily_on_host(rt)
        backend.link = g.group_id
        await speak(rt, ANSWER)
        assert backend.n == 2  # asked again, with no code guess of which draft it answers
        await rt.ctx.scheduler.advance(2000)
        assert [m.state for m in await messages(rt, "host_answer")] == ["published"]
    finally:
        await close_env(rt)


@pytest.mark.parametrize("label", ["purchase", None])
async def test_arm_b_a_shout_out_is_triages_label(label):
    rt, llm = await make_env(DESIGN_ARM="B")
    try:
        text = "Just bought two, so excited!!"
        llm.outputs[("comment_triage", text)] = {
            "kind": "reaction", "hide_category": None, "product_id": None, "product_basis": "unknown", "intent": None,
            "condition_slots": {k: None for k in ("person_type", "age_group", "life_stage", "condition", "combined_with",
                                                  "time_of_day")},
            "canonical_question": "", "group_candidate_id": None, "reason": "scripted", "shoutout": label}
        await say(rt, "Mei", text)
        assert [s.kind for s in rt.shoutouts] == ([label] if label else [])
    finally:
        await close_env(rt)


def test_arm_b_verify_keeps_digits_restricted_phrases_and_citations_only(pack, catalog):
    from app.logic.reflex import Reflex

    quote = "Skin hydration immediately after one application: +38% versus before application."
    pid = "DL-CR-01#in-house-test-results#skin-hydration-immediately-after-one-application"
    passages = [p for p in pack.passages if p.product_id == CREAM]
    out = ComposerOutput(answer="It works. Hydration goes up. It rose 38% right after one use.",
                         citations=[{"passage_id": pid, "quote": quote}], grounded=True, needs_human=False, reason="")
    kw = dict(multi=False, reflex=Reflex(pack.rules, pack.lexicon), not_approved_claims=[])
    assert not verify_answer(out, passages, CREAM, **kw)[0]  # arm A: 3 sentences, no "in-house"
    assert verify_answer(out, passages, CREAM, minimal=True, **kw) == (True, [])
    wrong = out.model_copy(update={"answer": "It rose 40% right after one use."})
    assert verify_answer(wrong, passages, CREAM, minimal=True, **kw)[1] == ["number 40 not in a cited quote"]


@pytest.mark.parametrize("arm, provisional, fallback", [("B", True, True), ("C", False, False), ("D", False, False)])
async def test_arm_c_has_no_reflex_pre_scan(arm, provisional, fallback):
    """D-189: arm C is arm B without the reflex chip and without the reflex fallback alert when the judge fails."""
    from .judge_fakes import events

    rt, llm = await make_env(DESIGN_ARM=arm, REFLEX_ON_FAIL="alert")  # D-293: the fallback alert path
    try:
        line = "This cream cures eczema, honestly."
        llm.fail("utterance_judge", line)  # both split judges fail
        await speak(rt, line)
        created = [e.payload for e in await events(rt, "alert.created")]
        assert any(p["status"] == "provisional" for p in created) is provisional
        assert any(a.status == "active" and a.unverified for a in await rt.alerts()) is fallback
    finally:
        await close_env(rt)


def test_arm_d_layers_b_and_d_prompt_lines_and_gives_the_whole_sheet(catalog):
    d = arms.system_instruction("BASE", "context_judge", "D", PROMPTS)
    assert "numbers_said" in d and "PRODUCT_FACTS" in d
    assert arms.system_instruction("BASE", "answer_composer", "E", PROMPTS) == arms.system_instruction(
        "BASE", "answer_composer", "D", PROMPTS) != "BASE"
    assert arms.system_instruction("BASE", "answer_composer", "B", PROMPTS) == "BASE"
    from app.agents import inputs
    assert {p.product_id for p in inputs.all_passages(catalog)} == {p.product_id for p in catalog.products}
    assert inputs.all_passages(catalog, CREAM) and all(p.product_id == CREAM for p in inputs.all_passages(catalog, CREAM))


def test_arm_d_posting_has_no_code_number_gate():
    from app.models.agent_io import FactCheckOutput

    kw = dict(lex=LEX, high_alert_active=False, facts=FactCheckOutput(claims=[], reason=""), by_judge=True)
    d = decide(_jo(numbers_said=["4"], hedged=False), OFFERED, grp(), ans(), numbers_gate=False, **kw)
    assert d.action == "post"
    d = decide(_jo(numbers_said=[], hedged=True), OFFERED, grp(), ans(), numbers_gate=False, **kw)
    assert d.action == "verbal_not_posted"  # the judge's own "unsure" still holds it


async def test_arm_d_a_listed_correction_counts_without_a_quote():
    rt, llm = await make_env(DESIGN_ARM="D")
    try:
        line = "This cream cures eczema."
        llm.judge(line, violations=[violation("ASEAN-2D-DISEASE", "cures eczema")])
        await speak(rt, line)
        [a] = [x for x in await rt.alerts() if x.status == "active"]
        fix = "Let me say that again more carefully."
        llm.outputs[("compliance_judge", fix)] = {
            "compliance": {"violations": []},
            "correction": {"corrects_alert_ids": [a.alert_id], "quotes": []}, "reason": "scripted"}
        await speak(rt, fix)
        assert (await rt.get_alert(a.alert_id)).status == "corrected"
    finally:
        await close_env(rt)


@pytest.mark.parametrize("arm, kind", [("A", "reaction"), ("D", "pending")])
async def test_arm_d_has_no_comment_prefilter(arm, kind):
    rt, _ = await make_env(DESIGN_ARM=arm)
    try:
        c = await say(rt, "Mei", "lol", wait=False)  # arm A settles it at once; arm D leaves it to triage
        assert c.kind == kind
        await rt.ctx.scheduler.idle()
    finally:
        await close_env(rt)


def test_arm_f_document_store_serves_whole_files(catalog):
    from app.providers.docstore import LocalDocStore

    store = LocalDocStore(catalog)
    market, category = store.market
    paths = [d["path"] for d in store.list_documents()]
    assert f"products/{CREAM}.md" in paths and f"rules/{market}/{category}.md" in paths
    doc = store.get_product(CREAM)
    assert doc.startswith("# ") and "\n## Key facts\n" in doc and store.get_product("nope") is None
    rules = store.get_rules(market, category)
    assert all(r.rule_id in rules for r in catalog.pack.rules.rules) and store.get_rules("XX", category) is None


async def test_arm_f2_preloads_the_on_air_file_in_the_cached_prefix():
    rt, llm = await make_env(DESIGN_ARM="F2")
    seen = []
    original = llm.generate

    async def capture(req, timeout_ms):
        seen.append(req)
        return await original(req, timeout_ms)

    llm.generate = capture
    try:
        await speak(rt, "This cream feels so light.")
        judges = [r for r in seen if r.agent in ("compliance_judge", "context_judge")]
        assert judges and all(r.cache_prefix.startswith('<data name="PRODUCT_FILE">')
                              and r.user_message.startswith(r.cache_prefix) for r in judges)
        assert all("PRODUCT_FACTS" not in r.user_message for r in judges)
    finally:
        await close_env(rt)


async def test_arm_f_composer_does_no_search(catalog):
    from app.agents.answer_composer import gather_passages

    class NoSearch:
        async def search(self, *a, **k):
            raise AssertionError("searched")

        async def prefetch(self, pid):
            raise AssertionError("prefetched")

    assert await gather_passages(NoSearch(), catalog, {}, product_id=CREAM, intent="price", canonical_question="How much?",
                                 promo=None, top_k=4, search=False) == []


async def test_arm_f1_composer_answers_from_the_files_its_tool_step_asked_for():
    rt, llm = await make_env(DESIGN_ARM="F1")
    seen = []
    original = llm.generate

    async def capture(req, timeout_ms):
        seen.append(req)
        return await original(req, timeout_ms)

    llm.generate = capture
    text = "How do I use the cream?"
    llm.outputs[("comment_triage", text)] = {
        "kind": "question", "hide_category": None, "product_id": CREAM, "product_basis": "explicit",
        "intent": "how_to_use", "condition_slots": {k: None for k in ("person_type", "age_group", "life_stage", "condition",
                                                                     "combined_with", "time_of_day")},
        "canonical_question": text, "group_candidate_id": None, "reason": "scripted", "shoutout": None}
    try:
        await say(rt, "Mei", text)
        agents = [r.agent for r in seen]
        assert "file_tools" in agents and "answer_composer" in agents
        assert agents.index("file_tools") < agents.index("answer_composer")
        composer = next(r for r in seen if r.agent == "answer_composer")
        assert "Key facts" in composer.user_message and '<data name="RULES">' not in composer.user_message
    finally:
        await close_env(rt)


@pytest.mark.parametrize("ids, kept", [(["ASEAN-2D-DISEASE", "NOPE", "BRAND-SUPERLATIVE"], 2), (None, None)])
async def test_arm_e_the_judge_reads_only_the_rules_the_search_picked(monkeypatch, ids, kept):
    from app.providers import rule_search

    class Search:
        async def warm_up(self):
            pass

        async def search(self, text, market, **_):
            return ids

    monkeypatch.setattr(rule_search, "for_settings", lambda _s: Search())
    rt, llm = await make_env(DESIGN_ARM="E")
    seen = []
    original = llm.generate

    async def capture(req, timeout_ms):
        seen.append(req)
        return await original(req, timeout_ms)

    llm.generate = capture
    try:
        await speak(rt, "This cream feels so light.")
        [req] = [r for r in seen if r.agent == "compliance_judge"]
        rules = req.user_message.split('<data name="RULES">', 1)[1].split("</data>", 1)[0]
        assert rules.count('"rule_id"') == (kept or len(rt.catalog.pack.rules.rules))
        assert '<data name="RULES">' not in req.cache_prefix
    finally:
        await close_env(rt)


@pytest.mark.parametrize("arm, ok", [("A", False), ("B", False), ("D", True), ("F2", True)])
def test_d201_the_draft_code_gate_per_arm(pack, catalog, arm, ok):
    """A wrong number: arms A to C block it in code; arms D to F2 leave it to the LLM draft verifier."""
    from app.logic.reflex import Reflex
    from app.pipelines.comments import draft_code_gate

    quote = "Live broadcast price: S$36.00"
    out = ComposerOutput(answer="It is S$30.00 today.", citations=[{"passage_id": "DL-CR-01#key-facts#live-broadcast-price",
                                                                     "quote": quote}],
                         grounded=True, needs_human=False, reason="")
    got, _ = draft_code_gate(out, pack.passages, CREAM, arm=arm, reflex=Reflex(pack.rules, pack.lexicon),
                             not_approved=[])
    assert got is ok
    refused = out.model_copy(update={"grounded": False, "answer": ""})
    assert draft_code_gate(refused, pack.passages, CREAM, arm=arm, reflex=Reflex(pack.rules, pack.lexicon),
                           not_approved=[])[0] is False
