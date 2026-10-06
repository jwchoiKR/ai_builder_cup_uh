"""D-302 (JUDGE_ARM=vote): two more runs on a line with a candidate; 3/3 keeps the rule severity, 2/3 caps at MEDIUM,
1/3 drops ("vote: 1/3"); a failed extra run is no vote, and two failed runs keep the candidate unverified. Made-up
lines; the model's runs are scripted."""
from __future__ import annotations

import json

import pytest

from app.agents import vote
from app.agents.fact_checker import DROPS
from app.models.agent_io import ComplianceOutput, FactCheckOutput
from app.providers.llm import AgentResult, LLMError, RawReply

from .judge_fakes import CREAM, ScriptedBackend, close_env, speak, split_part, judge_output, violation
from .test_q_fixes import _law_rule, _with_law_rules

V = "ASEAN-2D-VULNERABLE"


def _comp(*vs) -> ComplianceOutput:
    return ComplianceOutput.model_validate({"compliance": {"violations": list(vs)},
                                            "correction": {"corrects_alert_ids": []}, "reason": "t"})


def _ok(out) -> AgentResult:
    return AgentResult(status="ok", output=out, latency_ms=1, call_id="c")


FAIL = AgentResult(status="timeout", output=None, latency_ms=3000, call_id="c")


@pytest.mark.parametrize("extras, votes, severity, kept", [
    ([_comp(violation(V, "safe for babies")), _comp(violation(V, "Safe for babies!"))], 3, None, True),
    ([_comp(violation(V, "safe for babies")), _comp()], 2, "MEDIUM", True),  # 2/3: capped
    ([_comp(), _comp(violation(V, "safe for babies", negated=True))], 1, None, False),  # a negated run is no vote
    ([_comp(violation(V, "smells nice")), FAIL], 1, None, False),  # no overlapping span; a timeout is no vote
    ([FAIL, FAIL], 1, None, True),  # both extra runs failed: kept, unverified
])
def test_d302_compliance_votes(catalog, extras, votes, severity, kept):
    first = _comp(violation(V, "safe for babies"))
    sink: list = []
    token = DROPS.set(sink)
    try:
        out = vote.compliance_votes(first, [e if isinstance(e, AgentResult) else _ok(e) for e in extras], catalog)
    finally:
        DROPS.reset(token)
    v = first.compliance.violations[0] if kept else None
    assert bool(out.compliance.violations) is kept
    if kept:
        assert (v._votes, v._severity, v._unverified) == (votes, severity, all(e is FAIL for e in extras))
    else:
        assert [d["reason"] for d in sink] == ["compliance: vote: 1/3"]


def test_d302_a_rule_of_the_same_category_is_a_vote(catalog, pack):
    from app.onboarding.lawpack import to_rules

    rules = [to_rules("law_x_v1", _law_rule(rid, "vulnerable_groups")[1], pack.lang_pack.categories)[0]
             for rid in ("HS-A", "HS-B")]
    cat = _with_law_rules(catalog, *rules)
    first = _comp(violation("HS-A", "safe for kids"))
    out = vote.compliance_votes(first, [_ok(_comp(violation("HS-B", "safe for kids"))), _ok(_comp())], cat)
    assert out.compliance.violations[0]._votes == 2


def _facts(*claims) -> FactCheckOutput:
    return FactCheckOutput.model_validate({"claims": [
        {"span": "s", "field": f, "product_id": CREAM, "stated_value": "x", "verdict": v, "correct_value": c,
         "passage_id": None, "quote": None} for f, v, c in claims], "reason": "t"})


@pytest.mark.parametrize("extras, votes, kept", [
    ([_facts(("price", "contradicted", "36 dollars")), _facts(("price", "contradicted", "S$36"))], 3, True),
    ([_facts(("price", "contradicted", "S$34.00")), _facts(("price", "contradicted", "S$36.00"))], 2, True),
    ([_facts(("price", "supported", None)), _facts(("volume", "contradicted", "S$36.00"))], 1, False),
    ([_facts(("caution", "contradicted", "Stop use if irritation occurs"))] * 2, 1, False),  # another field
])
def test_d302_fact_votes(catalog, extras, votes, kept):
    first = _facts(("price", "contradicted", "S$36.00"))
    out = vote.fact_votes(first, [_ok(e) for e in extras], catalog)
    c = out.claims[0]
    assert c._votes == votes and (c.verdict == "contradicted") is kept


def test_d302_word_corrections_vote_by_their_words(catalog):
    first = _facts(("caution", "contradicted", "Stop use if irritation occurs"))
    out = vote.fact_votes(first, [_ok(_facts(("caution", "contradicted", "stop using it if irritation occurs"))),
                                  _ok(_facts(("caution", "contradicted", "Keep away from eyes")))], catalog)
    assert out.claims[0]._votes == 2


class _Runs(ScriptedBackend):
    """The compliance judge answers per call: a list of violation lists, one per run; records each request."""

    def __init__(self, line: str, runs: list[list[dict]]) -> None:
        super().__init__()
        self.line, self.runs, self.reqs = line, runs, []

    async def generate(self, req, timeout_ms):
        if req.agent == "compliance_judge" and req.mock_primary_text == self.line:
            self.reqs.append(req)
            run = self.runs[min(len(self.reqs), len(self.runs)) - 1]
            if run is None:
                raise LLMError("scripted failure")
            return RawReply(json.dumps(split_part("compliance_judge", judge_output(violations=run))),
                            model_version="scripted")
        return await super().generate(req, timeout_ms)


LINE = "Totally safe for babies, mums love it."


@pytest.mark.parametrize("runs, alerts, severity, votes", [
    ([[violation(V, "safe for babies")]] * 3, 1, "HIGH", 3),
    ([[violation(V, "safe for babies")], [violation(V, "safe for babies")], []], 1, "MEDIUM", 2),
    ([[violation(V, "safe for babies")], [], []], 0, None, None),
])
async def test_d302_the_vote_arm_end_to_end(runs, alerts, severity, votes):
    from .helpers import live_runtime, make_ctx

    llm = _Runs(LINE, runs)
    rt = await live_runtime(make_ctx(backend=llm, JUDGE_ARM="vote", VOTE_TEMPERATURE="0.7"))
    try:
        await speak(rt, LINE)
        await rt.utterances.drain()
        active = [a for a in await rt.alerts() if a.kind == "compliance" and a.status == "active"]
        assert [(a.severity, a.votes) for a in active] == ([(severity, votes)] if alerts else [])
        first, *extra = llm.reqs
        assert len(extra) == 2 and all(r.temperature == 0.7 and not r.hedge for r in extra)
        assert first.temperature is None and first.hedge
    finally:
        await close_env(rt)


async def test_d302_a_line_without_a_candidate_is_not_run_again():
    from .helpers import live_runtime, make_ctx

    llm = _Runs("It feels light and soft.", [[]])
    rt = await live_runtime(make_ctx(backend=llm, JUDGE_ARM="vote"))
    try:
        await speak(rt, "It feels light and soft.")
        await rt.utterances.drain()
        assert len(llm.reqs) == 1
    finally:
        await close_env(rt)


async def test_d302_fact_votes_end_to_end():
    from .helpers import live_runtime, make_ctx
    from .test_relation import _RelationBackend

    class Vary(_RelationBackend):
        n = 0

        async def generate(self, req, timeout_ms):
            if req.agent == "fact_checker":
                Vary.n += 1
                self.relation = "consistent" if Vary.n == 3 else "contradicts"
            return await super().generate(req, timeout_ms)

    llm = Vary("contradicts")
    rt = await live_runtime(make_ctx(backend=llm, FACT_RELATION=True, FACT_GUARDS="off", JUDGE_ARM="vote"))
    try:
        await speak(rt, "It's only thirty-two dollars today.")
        await rt.utterances.drain()
        [a] = [a for a in await rt.alerts() if a.kind == "fact"]
        assert a.votes == 2 and a.evidence_ids and a.correct_value == "S$36.00"
    finally:
        await close_env(rt)


async def test_d302_self_confidence_is_asked_only_when_set():
    from app.agents.split_judges import ComplianceJudge
    from app.models.agent_io import ComplianceOutputR, ComplianceOutputRC, FactRelationOutput, FactRelationOutputC

    from .helpers import live_runtime, make_ctx

    for conf, comp, fact in (("off", ComplianceOutputR, FactRelationOutput), ("self", ComplianceOutputRC,
                                                                              FactRelationOutputC)):
        rt = await live_runtime(make_ctx(backend=ScriptedBackend(), FACT_RELATION=True, VOTE_CONFIDENCE=conf))
        try:
            j = ComplianceJudge(rt.ctx.llm, rt.ctx.prompts, rt.catalog, rt.reflex)
            f = rt.utterances.facts
            assert j.output_model is comp and f.relation_model is fact
            assert ("`confidence`" in j.system_instruction) is (conf == "self")
            assert ("`confidence`" in f.system_instruction) is (conf == "self")
        finally:
            await close_env(rt)


def test_d302_the_temperature_reaches_the_request_config():
    from app.models.agent_io import VerifyOutput
    from app.providers.llm import LLMRequest, vertex_config

    base = dict(agent="a", model="m", thinking_level="LOW", prompt_version="v", system_instruction="s",
                user_message="u", output_model=VerifyOutput, deadline_ms=1000)
    assert vertex_config(LLMRequest(**base, temperature=0.7), 1000, {}).temperature == 0.7
    assert vertex_config(LLMRequest(**base), 1000, {}).temperature is None
