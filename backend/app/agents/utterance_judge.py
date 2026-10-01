"""UtteranceJudge agent (DEV_SPEC §7.3): compliance, correction, answer linking, prompter and switch
in one call. `JUDGE_MODE=single` adds the fact check to the same call (judge_single.md)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..logic.catalog import Catalog
from ..logic.grouping import normalise_question
from ..logic.reflex import Reflex
from ..models.agent_io import JudgeSingleOutput, UtteranceJudgeOutput
from ..models.data import Passage, Promo, PrompterPoint
from ..models.session import Alert, HostCue, QuestionGroup, SwitchState
from ..providers.llm import AgentResult, LLMClient, LLMRequest
from ..providers.prompts import PromptTemplate
from . import fact_checker, inputs

GROUP_REF, ALERT_REF = "@group:", "@alert:"


@dataclass
class JudgeInput:
    utterance: str
    on_air: str
    active_alerts: list[Alert] = field(default_factory=list)
    open_questions: list[tuple[QuestionGroup, str | None]] = field(default_factory=list)
    cue: HostCue | None = None
    previous: list[str] = field(default_factory=list)
    points_by_product: dict[str, list[PrompterPoint]] | None = None
    session_id: str | None = None
    scenario: str = "default"
    # single mode only
    switch: SwitchState = field(default_factory=SwitchState)
    promo: Promo | None = None
    passages: list[Passage] = field(default_factory=list)


def say_instead_fallback(catalog: Catalog, product_id: str) -> str:
    """§8.4.3: the on-air product's first approved claim; a trailing '*' becomes the in-house-test
    qualifier."""
    claim = catalog.approved_claims(product_id)[0].strip()
    if claim.endswith("*"):
        claim = claim[:-1].rstrip()
        if claim.endswith("."):
            claim = claim[:-1]
        claim += " in our in-house test."
    return claim


def post_validate(out: UtteranceJudgeOutput, catalog: Catalog, values: dict) -> UtteranceJudgeOutput:
    """Drop unknown rules and any id that was not in the input lists; severity comes from the rule."""
    o = out.model_copy(deep=True)
    rules = catalog.pack.rules_by_id
    o.compliance.violations = [v for v in o.compliance.violations if v.rule_id in rules]
    for v in o.compliance.violations:
        v.severity = rules[v.rule_id].severity
    alert_ids = {a["alert_id"] for a in values["active_alerts_json"]}
    o.correction.corrects_alert_ids = [a for a in dict.fromkeys(o.correction.corrects_alert_ids) if a in alert_ids]
    group_ids = {q["group_id"] for q in values["open_questions_json"]}
    if o.answer.matched_group_id is not None and o.answer.matched_group_id not in group_ids:
        o.answer.matched_group_id = None
        o.answer.is_answer = o.answer.consistent_with_suggested = False
    point_ids = {p["point_id"] for p in values["prompter_points_json"]}
    o.prompter.covered_point_ids = [p for p in dict.fromkeys(o.prompter.covered_point_ids) if p in point_ids]
    cue_ids = {c["cue_id"] for c in values["host_cues_json"]}
    o.prompter.covered_cue_ids = [c for c in o.prompter.covered_cue_ids if c in cue_ids]
    if not catalog.is_product(o.prompter.switch.target_product_id):
        o.prompter.switch.target_product_id = None
    return o


class UtteranceJudge:
    name = "utterance_judge"

    def __init__(self, llm: LLMClient, prompts: dict[str, PromptTemplate], catalog: Catalog, reflex: Reflex,
                 *, single: bool = False) -> None:
        self.llm = llm
        self.single = single
        self.prompt = prompts["judge_single" if single else "utterance_judge"]
        self.prompt_version = self.prompt.version
        self.model = llm.fast.model
        self.catalog = catalog
        self.reflex = reflex

    def build_values(self, inp: JudgeInput) -> dict:
        values = {
            "current_product_json": inputs.current_product_json(self.catalog, inp.on_air),
            "run_sheet_compact_json": inputs.run_sheet_compact_json(self.catalog, inp.on_air),
            "approved_claims_of_current_product_json": inputs.approved_claims_of_current_product_json(self.catalog, inp.on_air),
            "rules_compact_json": inputs.rules_compact_json(self.catalog),
            "active_alerts_json": inputs.active_alerts_json(inp.active_alerts),
            "open_questions_json": inputs.open_questions_json(inp.open_questions, len(inp.open_questions)),
            "prompter_points_json": inputs.prompter_points_json(self.catalog, inp.on_air, inp.points_by_product),
            "host_cues_json": inputs.host_cues_json(inp.cue),
            "last_two_final_transcripts_json": inp.previous[-2:],
            "utterance_text": inputs.utterance_text(inp.utterance),
        }
        if self.single:
            values |= {
                "switch_context_json": inputs.switch_context_json(self.catalog, inp.switch, inp.on_air),
                "active_promo_json_or_null": inputs.active_promo_json_or_null(self.catalog, inp.promo),
                "set_offers_json": inputs.set_offers_json(self.catalog, inp.promo),
                "passages_json": inputs.passages_json(inp.passages),
            }
        return values

    async def run(self, inp: JudgeInput, *, deadline_ms: int) -> AgentResult:
        values = self.build_values(inp)
        group_q = {q["group_id"]: normalise_question(q["canonical_question"]) for q in values["open_questions_json"]}
        alert_span = {a["alert_id"]: normalise_question(a["span"] or "") for a in values["active_alerts_json"]}
        q_group = {v: k for k, v in group_q.items()}
        span_alert = {v: k for k, v in alert_span.items()}

        def encode(data: dict) -> dict:
            ans = data.get("answer") or {}
            if ans.get("matched_group_id") in group_q:
                ans["matched_group_id"] = GROUP_REF + group_q[ans["matched_group_id"]]
            corr = data.get("correction") or {}
            corr["corrects_alert_ids"] = [ALERT_REF + alert_span[a] if a in alert_span else a
                                          for a in corr.get("corrects_alert_ids", [])]
            return data

        def decode(data: dict) -> dict:
            ans = data.get("answer") or {}
            ref = ans.get("matched_group_id")
            if isinstance(ref, str) and ref.startswith(GROUP_REF):
                ans["matched_group_id"] = q_group.get(ref[len(GROUP_REF):])
            corr = data.get("correction") or {}
            ids = []
            for a in corr.get("corrects_alert_ids", []):
                if isinstance(a, str) and a.startswith(ALERT_REF):
                    a = span_alert.get(a[len(ALERT_REF):])
                if a:
                    ids.append(a)
            corr["corrects_alert_ids"] = ids
            return data

        output_model = JudgeSingleOutput if self.single else UtteranceJudgeOutput
        res = await self.llm.call(LLMRequest(
            agent="judge_single" if self.single else self.name, model=self.llm.fast.model,
            thinking_level=self.llm.fast.thinking_level, prompt_version=self.prompt_version,
            system_instruction=self.prompt.system_instruction, user_message=self.prompt.render(values),
            output_model=output_model, deadline_ms=deadline_ms, session_id=inp.session_id,
            mock_primary_text=inp.utterance, mock_scenario=inp.scenario,
            mock_fallback=lambda _: rule_based_judge(inp, values, self.catalog, self.reflex, self.single),
            fixture_encode=encode, fixture_decode=decode, preview=inp.utterance,
        ))
        if res.output is not None:
            validated = post_validate(res.output, self.catalog, values)
            if self.single:
                validated.facts = fact_checker.post_validate(res.output.facts, inp.passages, self.catalog, inp.promo)
            res.output = validated
        return res


# ---- rule-based fallback for unit tests ----------------------------------------------------------

_CORRECTION = re.compile(r"\b(correct that|my mistake|sorry|let me correct)\b", re.IGNORECASE)


def rule_based_judge(inp: JudgeInput, values: dict, catalog: Catalog, reflex: Reflex, single: bool) -> dict:
    seen, violations = set(), []
    for h in reflex.scan(inp.utterance):
        if h.rule_id in seen:
            continue
        seen.add(h.rule_id)
        violations.append({"span": h.phrase, "rule_id": h.rule_id, "severity": h.severity, "is_negated": h.negated,
                           "is_quoted": h.quoted, "say_instead": say_instead_fallback(catalog, inp.on_air)})
    corrects = [a["alert_id"] for a in values["active_alerts_json"]] if _CORRECTION.search(inp.utterance) else []
    nxt = catalog.next_product(inp.on_air)
    t = inp.utterance.lower()
    switch = {"is_transition": False, "is_quote": False, "target_product_id": None, "confidence": "low"}
    if nxt and catalog.product_by_alias(t) == nxt and re.search(r"\b(show you|next up|now let)\b", t):
        switch = {"is_transition": True, "is_quote": False, "target_product_id": nxt, "confidence": "high"}
    elif re.search(r"\bback to\b", t) and catalog.product_by_alias(t) == inp.on_air:
        switch = {"is_transition": True, "is_quote": False, "target_product_id": inp.on_air, "confidence": "high"}
    out = {
        "compliance": {"violations": violations},
        "correction": {"corrects_alert_ids": corrects},
        "answer": {"utterance_type": "correction" if corrects else "product_talk", "matched_group_id": None,
                   "is_answer": False, "consistent_with_suggested": False},
        "prompter": {"covered_point_ids": [], "covered_cue_ids": [], "switch": switch},
        "reason": "rule-based",
    }
    if single:
        out["facts"] = {"claims": [], "reason": "rule-based"}
    return out
