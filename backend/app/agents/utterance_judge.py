"""UtteranceJudge agent (DEV_SPEC §7.3): compliance, correction, answer linking, prompter and switch
in one call (`JUDGE_MODE=split`). `JUDGE_MODE=single` adds the fact check to the same call
(judge_single.md). The default `split3` cuts the same jobs into two calls (split_judges.py, D-099);
the input values, checks and rule-based fallbacks here are shared with it."""
from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from ..logic.catalog import Catalog
from ..logic.grouping import normalise_question
from ..logic.reflex import Reflex
from ..models.agent_io import JudgeSingleOutput, UtteranceJudgeOutput, with_switch_naming
from ..models.data import Passage, Promo, PrompterPoint
from ..models.session import Alert, HostCue, QuestionGroup, SwitchState
from ..providers.llm import AgentResult, LLMClient, LLMRequest
from ..providers.prompts import PromptTemplate
from . import fact_checker, inputs

log = logging.getLogger(__name__)

GROUP_REF, ALERT_REF = "@group:", "@alert:"
STATIC_JUDGE_KEYS = frozenset({"current_product_json", "run_sheet_compact_json",
                             "approved_claims_of_current_product_json", "rules_compact_json",
                             "prompter_points_json", "passages_json"})


@dataclass
class JudgeInput:
    utterance: str
    on_air: str
    active_alerts: list[Alert] = field(default_factory=list)
    open_questions: list[tuple[QuestionGroup, str | None]] = field(default_factory=list)
    on_screen_group_id: str | None = None  # D-112: the question card the host sees now
    cue: HostCue | None = None
    previous: list[str] = field(default_factory=list)
    points_by_product: dict[str, list[PrompterPoint]] | None = None
    session_id: str | None = None
    scenario: str = "default"
    # single mode only
    switch: SwitchState = field(default_factory=SwitchState)
    promo: Promo | None = None
    passages: list[Passage] = field(default_factory=list)
    # D-351 SWITCH_MODE=immediate: each product's type word ("cream", "serum") for the run sheet the context judge gets
    run_sheet_types: dict[str, str] | None = None
    now: int | None = None  # D-403: when the input was built, for each active alert's age
    chain: list[str] = field(default_factory=list)  # D-406: the split lines a merged line joins (same_as is asked)


def spoken_claim(text: str) -> str:
    """The '*' of an approved claim marks the in-house-test qualifier; the host must say the
    qualifier, not read the asterisk (§8.4.3 rule, also applied to judge output, D-062)."""
    claim = text.strip()
    if "*" not in claim:
        return claim
    claim = claim.replace("*", "").rstrip()
    if "in-house test" in claim.lower():
        return claim
    if claim.endswith("."):
        claim = claim[:-1]
    return claim + " in our in-house test."


def say_instead_fallback(catalog: Catalog, product_id: str) -> str:
    """§8.4.3: the on-air product's first approved claim, with the in-house-test qualifier. D-273 (sealed pool 4: a
    release with no approved claim raised IndexError here, so a failed judge call lost the line's alert): the D-232
    line when there is none."""
    claims = catalog.approved_claims(product_id)
    return spoken_claim(claims[0]) if claims else f"(no approved wording in {catalog.pack.lang})"


def validate_compliance(o, catalog: Catalog, values: dict):
    """In place, on any output with `compliance` and `correction`. D-391 (user): the model's verdict is applied as
    given: its severity, its say_instead, its negation and quote flags. The only skips, logged, are verdicts that
    cannot be applied: a rule the line was not given (D-279: another category's), a product that is not in the show."""
    rules = catalog.pack.rules_by_id
    if "rules_compact_json" in values:  # D-279: a rule the line was not given (another category's) is no verdict
        offered = {r["rule_id"] for r in values["rules_compact_json"]}
        rules = {k: v for k, v in rules.items() if k in offered}
    scope = values.get("scope_product_ids")  # D-349: two products in scope right after a switch
    kept = []
    for v in o.compliance.violations:
        if v.rule_id not in rules:
            log.info("compliance verdict skipped (cannot apply): rule %r was not given to the judge | span=%r",
                     v.rule_id, v.span)
            continue
        if scope and getattr(v, "product_id", None) not in scope:
            if catalog.is_product(getattr(v, "product_id", None)):
                log.info("compliance verdict on %s, outside the line's scope %s: applied as given", v.product_id,
                         sorted(scope))
            else:
                log.info("compliance verdict skipped (cannot apply): product %r is not in the show | span=%r",
                         getattr(v, "product_id", None), v.span)
                continue
        kept.append(v)
    o.compliance.violations = kept
    return _check_correction_ids(o, values)


def _check_correction_ids(o, values: dict):
    """Only alerts the judge was shown can be corrected (provenance)."""
    alert_ids = {a["alert_id"] for a in values["active_alerts_json"]}
    dropped = [a for a in dict.fromkeys(o.correction.corrects_alert_ids) if a not in alert_ids]
    if dropped:  # D-356: never silently
        log.info("correction ids dropped: not in ACTIVE_ALERTS: %s (shown: %s)", dropped, sorted(alert_ids))
    o.correction.corrects_alert_ids = [a for a in dict.fromkeys(o.correction.corrects_alert_ids) if a in alert_ids]
    if hasattr(o.correction, "quotes"):  # D-187 arm B
        o.correction.quotes = [q for q in o.correction.quotes if q.alert_id in alert_ids]
    return o


def validate_original(o, catalog: Catalog, values: dict, originals):
    """D-358: a verdict cited from the regulation originals (no rule JSON). D-374 (user, 10/9): the model's verdict is
    applied as given: no check of the quote's wording or of the cited document (both are shown as the model wrote
    them, as its citation and summary); the alert's rule id is the document and the section, normalised, for
    duplicate suppression only. D-400: the severity comes from the citation type (a regulation document is HIGH),
    never from the model (D-427: TEST-QUALIFIER, the only MEDIUM, is gone). Only a verdict that cannot be applied is
    skipped and logged: a product id that is not in the show."""
    from .originals import cited_title, citation_rule_id

    by_name = {d.name.casefold(): d for d in originals}
    scope = values.get("scope_product_ids")  # D-349: two products in scope right after a switch
    kept = []
    for v in o.compliance.violations:
        if scope and getattr(v, "product_id", None) not in scope:
            if catalog.is_product(getattr(v, "product_id", None)):
                log.info("compliance verdict on %s, outside the line's scope %s: applied as given", v.product_id,
                         sorted(scope))
            else:
                log.info("compliance verdict skipped (cannot apply): product %r is not in the show | span=%r",
                         getattr(v, "product_id", None), v.span)
                continue
        cite = (v.citation or "").strip()
        # D-400 (user): the colour comes from what is cited: a regulation document is red (HIGH); the model does not
        # grade
        v.severity = "HIGH"
        doc, _, section = cite.partition("#")
        d = by_name.get(doc.strip().casefold())
        if d is None:
            log.info("compliance verdict cites a document the judge was not given (%r): applied as given", cite)
        v.rule_id = citation_rule_id(d.name if d is not None else doc.strip() or "regulation", section or "document")
        v.cited_title = cited_title(d, doc, section)  # D-433: what the host's red box says (never the slug)
        # D-361: the model's own say_instead (the prompt builds it from APPROVED_CLAIMS); no code word matching
        kept.append(v)
    o.compliance.violations = kept
    return _check_correction_ids(o, values)


def validate_context(o, catalog: Catalog, values: dict):
    """In place, on any output with `answer` and `prompter`: drop group, point and cue ids that were
    not in the input, and an unknown switch target."""
    group_ids = {q["group_id"] for q in values["open_questions_json"]}
    point_ids = {p["point_id"] for p in values["prompter_points_json"]}
    cue_ids = {c["cue_id"] for c in values["host_cues_json"]}
    unknown = ([o.answer.matched_group_id] if o.answer.matched_group_id not in group_ids | {None} else []) + [
        x for x in [*o.prompter.covered_point_ids, *o.prompter.covered_cue_ids] if x not in point_ids | cue_ids]
    if unknown or not (o.prompter.switch.target_product_id is None
                       or catalog.is_product(o.prompter.switch.target_product_id)):
        log.info("context ids skipped (cannot apply, not in the input): %s target=%r", unknown,  # D-374
                 o.prompter.switch.target_product_id)
    if o.answer.matched_group_id is not None and o.answer.matched_group_id not in group_ids:
        o.answer.matched_group_id = None
        o.answer.is_answer = o.answer.consistent_with_suggested = False
    o.answer.also_answered_group_ids = (
        [g for g in dict.fromkeys(o.answer.also_answered_group_ids) if g in group_ids and g != o.answer.matched_group_id]
        if o.answer.matched_group_id is not None and o.answer.is_answer else [])
    o.prompter.covered_point_ids = [p for p in dict.fromkeys(o.prompter.covered_point_ids) if p in point_ids]
    o.prompter.covered_cue_ids = [c for c in o.prompter.covered_cue_ids if c in cue_ids]
    if not catalog.is_product(o.prompter.switch.target_product_id):
        o.prompter.switch.target_product_id = None
    return o


def post_validate(out: UtteranceJudgeOutput, catalog: Catalog, values: dict) -> UtteranceJudgeOutput:
    """Drop unknown rules and any id that was not in the input lists; severity comes from the rule."""
    o = out.model_copy(deep=True)
    return validate_context(validate_compliance(o, catalog, values), catalog, values)


def judge_products(catalog: Catalog, inp: JudgeInput) -> set[str] | None:
    """D-279: in a multi-release show, the products whose rules apply (None: one-product rules as before). D-304/D-353:
    every show product (D-435: the code alias match that named the products in scope is gone)."""
    if catalog.pack.rule_products is None:
        return None
    return set(catalog.order)


def build_judge_values(catalog: Catalog, inp: JudgeInput, single: bool = False) -> dict:
    """Prompt values shared by the UtteranceJudge, judge_single and the split judges (D-099)."""
    values = {
        "current_product_json": inputs.current_product_json(catalog, inp.on_air),
        "run_sheet_compact_json": inputs.run_sheet_compact_json(catalog, inp.on_air, inp.run_sheet_types),
        "approved_claims_of_current_product_json": inputs.approved_claims_of_current_product_json(catalog, inp.on_air),
        "rules_compact_json": inputs.rules_compact_json(catalog, judge_products(catalog, inp)),
        "active_alerts_json": inputs.active_alerts_json(inp.active_alerts),
        "open_questions_json": inputs.open_questions_json(inp.open_questions, len(inp.open_questions),
                                                          inp.on_screen_group_id),
        "prompter_points_json": inputs.prompter_points_json(catalog, inp.on_air, inp.points_by_product),
        "host_cues_json": inputs.host_cues_json(inp.cue),
        "last_two_final_transcripts_json": inp.previous[-2:],
        "utterance_text": inputs.utterance_text(inp.utterance),
    }
    if single:
        values |= {
            "switch_context_json": inputs.switch_context_json(catalog, inp.switch, inp.on_air),
            "active_promo_json_or_null": inputs.active_promo_json_or_null(catalog, inp.promo),
            "set_offers_json": inputs.set_offers_json(catalog, inp.promo),
            "passages_json": inputs.passages_json(inp.passages),
        }
    return values


def symbolic_ids(values: dict) -> tuple[Callable[[dict], dict], Callable[[dict], dict]]:
    """Fixture encode/decode: group and alert ids are new in every session, so a recorded fixture
    names a group by its question and an alert by its span."""
    group_q = {q["group_id"]: normalise_question(q["canonical_question"]) for q in values["open_questions_json"]}
    alert_span = {a.get("alert_id", a.get("handle")): normalise_question(a["span"] or "")  # D-356: a handle
                  for a in values["active_alerts_json"]}
    q_group = {v: k for k, v in group_q.items()}
    span_alert = {v: k for k, v in alert_span.items()}

    def encode(data: dict) -> dict:
        ans = data.get("answer") or {}
        if ans.get("matched_group_id") in group_q:
            ans["matched_group_id"] = GROUP_REF + group_q[ans["matched_group_id"]]
        if ans.get("also_answered_group_ids"):
            ans["also_answered_group_ids"] = [GROUP_REF + group_q[g] if g in group_q else g
                                              for g in ans["also_answered_group_ids"]]
        corr = data.get("correction") or {}
        corr["corrects_alert_ids"] = [ALERT_REF + alert_span[a] if a in alert_span else a
                                      for a in corr.get("corrects_alert_ids", [])]
        return data

    def decode(data: dict) -> dict:
        ans = data.get("answer") or {}
        ref = ans.get("matched_group_id")
        if isinstance(ref, str) and ref.startswith(GROUP_REF):
            ans["matched_group_id"] = q_group.get(ref[len(GROUP_REF):])
        if ans.get("also_answered_group_ids"):
            ans["also_answered_group_ids"] = [
                g for g in (q_group.get(r[len(GROUP_REF):]) if isinstance(r, str) and r.startswith(GROUP_REF) else r
                            for r in ans["also_answered_group_ids"]) if g]
        corr = data.get("correction") or {}
        ids = []
        for a in corr.get("corrects_alert_ids", []):
            if isinstance(a, str) and a.startswith(ALERT_REF):
                a = span_alert.get(a[len(ALERT_REF):])
            if a:
                ids.append(a)
        corr["corrects_alert_ids"] = ids
        return data

    return encode, decode


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
        return build_judge_values(self.catalog, inp, self.single)

    async def run(self, inp: JudgeInput, *, deadline_ms: int) -> AgentResult:
        values = self.build_values(inp)
        encode, decode = symbolic_ids(values)
        # D-419: the switch verdict's decision field too (the immediate switch reads only it; D-415). These modes run only
        # on the mock provider and in the tests (D-361), whose answers fill it
        output_model = with_switch_naming(JudgeSingleOutput if self.single else UtteranceJudgeOutput)
        user, prefix = self.prompt.render_cached(values, STATIC_JUDGE_KEYS)
        res = await self.llm.call(LLMRequest(
            agent="judge_single" if self.single else self.name, model=self.llm.fast.model,
            thinking_level=self.llm.fast.thinking_level, prompt_version=self.prompt_version,
            system_instruction=self.prompt.system_instruction, user_message=user,
            cache_prefix=prefix, cache_ttl_sec=sum(i.planned_duration_sec for i in self.catalog.runsheet.items),
            output_model=output_model, deadline_ms=deadline_ms, session_id=inp.session_id,
            mock_primary_text=inp.utterance, mock_scenario=inp.scenario,
            mock_fallback=lambda _: rule_based_judge(inp, values, self.catalog, self.reflex, self.single),
            fixture_encode=encode, fixture_decode=decode, preview=inp.utterance,
        ))
        if res.output is not None:
            validated = post_validate(res.output, self.catalog, values)
            if self.single:
                validated.facts = fact_checker.as_given(res.output.facts, self.catalog)  # D-389
            res.output = validated
        return res


# ---- rule-based fallback for unit tests ----------------------------------------------------------

_CORRECTION = re.compile(r"\b(correct that|my mistake|sorry|let me correct)\b", re.IGNORECASE)


def rule_based_compliance(inp: JudgeInput, values: dict, catalog: Catalog, reflex: Reflex) -> dict:
    seen, violations = set(), []
    for h in reflex.scan(inp.utterance):
        if h.rule_id in seen:
            continue
        seen.add(h.rule_id)
        violations.append({"span": h.phrase, "rule_id": h.rule_id, "severity": h.severity, "is_negated": h.negated,
                           "is_quoted": h.quoted, "say_instead": say_instead_fallback(catalog, inp.on_air)})
    ids = [values.get("alert_handles", {}).get(a.get("handle"), a.get("alert_id")) for a in values["active_alerts_json"]]
    corrects = ids if _CORRECTION.search(inp.utterance) else []
    return {"compliance": {"violations": violations}, "correction": {"corrects_alert_ids": corrects}, "reason": "rule-based"}


def rule_based_context(inp: JudgeInput, catalog: Catalog) -> dict:
    nxt = catalog.next_product(inp.on_air)
    t = inp.utterance.lower()
    switch = {"is_transition": False, "is_quote": False, "target_product_id": None, "confidence": "low"}
    if nxt and catalog.product_by_alias(t) == nxt and re.search(r"\b(show you|next up|now let)\b", t):
        switch = {"is_transition": True, "is_quote": False, "target_product_id": nxt, "confidence": "high"}
    elif re.search(r"\bback to\b", t) and catalog.product_by_alias(t) == inp.on_air:
        switch = {"is_transition": True, "is_quote": False, "target_product_id": inp.on_air, "confidence": "high"}
    # D-415: the mock's answer fills the switch verdict's one decision field too (the immediate switch reads only it)
    switch["moving_to_next_named"] = switch["is_transition"] and switch["target_product_id"] == nxt
    return {
        "answer": {"utterance_type": "correction" if _CORRECTION.search(inp.utterance) else "product_talk",
                   "matched_group_id": None, "is_answer": False, "consistent_with_suggested": False},
        "prompter": {"covered_point_ids": [], "covered_cue_ids": [], "switch": switch},
        "reason": "rule-based",
    }


def rule_based_judge(inp: JudgeInput, values: dict, catalog: Catalog, reflex: Reflex, single: bool) -> dict:
    out = rule_based_compliance(inp, values, catalog, reflex) | rule_based_context(inp, catalog)
    if single:
        out["facts"] = {"claims": [], "reason": "rule-based"}
    return out
