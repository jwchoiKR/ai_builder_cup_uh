"""Structured outputs of the LLM agents (DEV_SPEC §7). These classes are also the JSON schemas
sent to the model, so field names and order follow the prompt files exactly."""
from __future__ import annotations

import functools
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, create_model

# ---- UtteranceJudge (§7.3) -------------------------------------------------------------------


class Violation(BaseModel):
    span: str
    rule_id: str
    severity: Literal["HIGH", "MEDIUM"]
    is_negated: bool
    is_quoted: bool
    say_instead: str
    # D-300: set by the verifier (never in the schema): its severity, and "kept without a verdict" (timeout)
    _severity: str | None = PrivateAttr(default=None)
    _unverified: bool = PrivateAttr(default=False)
    _votes: int | None = PrivateAttr(default=None)  # D-302: the runs (of 3) that agree
    _unverified_reason: str | None = PrivateAttr(default=None)  # D-306: the verifier's failure type


class Compliance(BaseModel):
    violations: list[Violation]


class Correction(BaseModel):
    corrects_alert_ids: list[str]


UtteranceType = Literal["product_talk", "answer", "question_readout", "correction", "transition", "chit_chat", "other"]


class AnswerLink(BaseModel):
    utterance_type: UtteranceType
    matched_group_id: str | None
    is_answer: bool
    consistent_with_suggested: bool
    # D-196: other open questions the same sentence also answers, consistently with their suggested answers
    also_answered_group_ids: list[str] = []


class SwitchCue(BaseModel):
    is_transition: bool
    is_quote: bool
    target_product_id: str | None
    confidence: Literal["low", "medium", "high"]


class PrompterJudgement(BaseModel):
    covered_point_ids: list[str]
    covered_cue_ids: list[str]
    switch: SwitchCue


class UtteranceJudgeOutput(BaseModel):
    compliance: Compliance
    correction: Correction
    answer: AnswerLink
    prompter: PrompterJudgement
    reason: str


# ---- the UtteranceJudge's jobs split in two parallel calls (JUDGE_MODE=split3, D-099) ----------


class ComplianceOutput(BaseModel):
    compliance: Compliance
    correction: Correction
    reason: str


class ContextOutput(BaseModel):
    answer: AnswerLink
    prompter: PrompterJudgement
    reason: str


# ---- D-187 design arm B: the meaning the model returns, which code only checks ------------------------------
# Subclasses of the arm-A outputs, used only under DESIGN_ARM B or C. Their extra fields have defaults so a mock
# reply still validates, but the schema sent to the model lists every field as required.


def _all_required(schema: dict) -> None:
    schema["required"] = list(schema.get("properties", {}))


class _ArmB(BaseModel):
    model_config = ConfigDict(json_schema_extra=_all_required)


class AlertCheck(_ArmB):
    """D-356 CORRECTION_HANDLES: the verdict on one ACTIVE_ALERTS entry, named by its per-call handle (A1, A2 ...)."""
    handle: str
    fixed_by_this_line: bool


@functools.cache
def with_alert_checks(model: type[BaseModel]) -> type[BaseModel]:
    """D-356: the compliance output with `alert_checks` FIRST (one entry per listed alert, by handle) in place of
    recalling alert ids; `correction` leaves the schema the model sees and is filled by code from the handles."""
    correction = model.model_fields["correction"].annotation

    def schema(s: dict) -> None:
        props = dict(s.get("properties", {}))
        props.pop("correction", None)
        s["properties"] = {"alert_checks": props.pop("alert_checks"), **props}
        s["required"] = list(s["properties"])

    return type(f"{model.__name__}H", (model,), {
        "__module__": __name__,
        "__annotations__": {"alert_checks": list[AlertCheck], "correction": correction},
        "alert_checks": Field(default_factory=list),
        "correction": Field(default_factory=lambda: correction(corrects_alert_ids=[])),
        "model_config": ConfigDict(json_schema_extra=schema),
    })


class NoteCheck(_ArmB):
    """D-363: the verdict on one ACTIVE_FACT_NOTES entry, named by its per-call handle (F1, F2 ...)."""
    handle: str
    fixed_by_this_line: bool


@functools.cache
def with_note_checks(model: type[BaseModel]) -> type[BaseModel]:
    """D-363: the fact checker's output with `note_checks` FIRST, asked for only when notes are active."""
    def schema(s: dict) -> None:
        props = dict(s.get("properties", {}))
        s["properties"] = {"note_checks": props.pop("note_checks"), **props}
        s["required"] = list(s["properties"])

    return type(f"{model.__name__}N", (model,), {
        "__module__": __name__,
        "__annotations__": {"note_checks": list[NoteCheck]},
        "note_checks": Field(default_factory=list),
        "model_config": ConfigDict(json_schema_extra=schema),
    })


class SwitchCueN(_ArmB):
    """D-351 SWITCH_MODE=immediate: the switch verdict with the one decision field, `moving_to_next_named` (the host
    moves on now to the next product and names it: name, short name or type word); it comes before the target, as
    the model writes in order. `confidence` stays in the schema but decides nothing."""
    is_transition: bool
    is_quote: bool
    moving_to_next_named: bool = False
    target_product_id: str | None
    confidence: Literal["low", "medium", "high"]


@functools.cache
def with_switch_naming(model: type[BaseModel]) -> type[BaseModel]:
    """D-351: the context output with `SwitchCueN` in place of `SwitchCue` (immediate switch mode only)."""
    prompter = model.model_fields["prompter"].annotation
    p = create_model(f"{prompter.__name__}N", __base__=prompter, switch=(SwitchCueN, ...))
    return create_model(f"{model.__name__}N", __base__=model, prompter=(p, ...))


@functools.cache
def with_product(model: type[BaseModel]) -> type[BaseModel]:
    """D-349 SWITCH_MODE=immediate: the same compliance output with a `product_id` per violation, asked for only in
    the seconds after a switch when two products are in scope (the model says which one each claim is about)."""
    comp = model.model_fields["compliance"].annotation
    viol = comp.model_fields["violations"].annotation.__args__[0]
    base = viol if issubclass(viol, _ArmB) else (viol, _ArmB)
    v = create_model(f"{viol.__name__}P", __base__=base, product_id=(str | None, None))
    c = create_model(f"{comp.__name__}P", __base__=comp, violations=(list[v], ...))
    return create_model(f"{model.__name__}P", __base__=model, compliance=(c, ...))


class CorrectionQuote(_ArmB):
    alert_id: str
    quote: str  # the exact words of the utterance that make the correction


class CorrectionB(Correction, _ArmB):
    quotes: list[CorrectionQuote] = []


class ViolationB(Violation, _ArmB):
    qualified_result_id: str | None = None  # TEST-QUALIFIER: the result the host stated


class ComplianceB(Compliance, _ArmB):
    violations: list[ViolationB]


class ComplianceOutputB(ComplianceOutput, _ArmB):
    compliance: ComplianceB
    correction: CorrectionB


ClaimKind = Literal["safety_promise", "disease_treatment", "medical_or_physiological_effect", "permanence",
                    "comparative_or_superlative", "usage_instruction", "composition_fact", "other"]


class ViolationR(Violation, _ArmB):
    # D-297: for a HIGH rule only, what kind of claim the line makes and the group it names (code checks the fit)
    claim_kind: ClaimKind | None = None
    group: str | None = None
    qualified_result_id: str | None = None  # D-299: TEST-QUALIFIER: the QUALIFIED_RESULTS entry the line states


class ComplianceR(Compliance, _ArmB):
    violations: list[ViolationR]


class ComplianceOutputR(ComplianceOutput, _ArmB):
    compliance: ComplianceR


def _cited_schema(s: dict) -> None:
    """D-358: the model writes the citation and its quote first; `rule_id` is code's (from the citation)."""
    props = dict(s.get("properties", {}))
    props.pop("rule_id", None)
    first = ["citation", "quote", "span", "severity", "is_negated", "is_quoted"]
    s["properties"] = {**{k: props.pop(k) for k in first if k in props}, **props}
    s["required"] = list(s["properties"])


class ViolationO(Violation, _ArmB):
    """D-358: a violation cited from a regulation original (no rule JSON): the document and section as written in the
    original ("<document>#<section>", or "TEST-QUALIFIER" for a test result said without who tested it), a short quote
    from it, and the severity the model chose by the prompt's criteria. Code sets `rule_id` from the citation."""
    model_config = ConfigDict(json_schema_extra=_cited_schema)
    citation: str
    quote: str
    rule_id: str = ""
    qualified_result_id: str | None = None  # the QUALIFIED_RESULTS entry a TEST-QUALIFIER verdict states


class ComplianceO(Compliance, _ArmB):
    violations: list[ViolationO]


class ComplianceOutputO(ComplianceOutput, _ArmB):
    compliance: ComplianceO


class ViolationRC(ViolationR):
    confidence: float | None = None  # D-302 VOTE_CONFIDENCE=self: a log field only


class ComplianceRC(ComplianceR):
    violations: list[ViolationRC]


class ComplianceOutputRC(ComplianceOutputR):
    compliance: ComplianceRC


class AnswerLinkB(AnswerLink, _ArmB):
    numbers_said: list[str] = []  # every number the host said, as digits, in the suggested answer's unit
    hedged: bool = False  # the host sounded unsure or took it back


class ContextOutputQ(BaseModel):
    """D-335 QUESTION_HOLD: the context verdict, first saying whether the next line is expected to resolve this one."""
    expects_resolution: bool
    answer: AnswerLink
    prompter: PrompterJudgement
    reason: str


class ContextOutputB(ContextOutput, _ArmB):
    answer: AnswerLinkB


# ---- FactChecker (§7.4) ----------------------------------------------------------------------

FactField = Literal[
    "price", "set_price", "promo", "volume", "ingredient", "ingredient_amount", "test_result",
    "usage", "texture", "fragrance", "packaging", "origin", "shelf_life", "ph", "caution", "availability", "other",
]


class FactClaim(BaseModel):
    span: str
    field: FactField
    product_id: str
    stated_value: str
    verdict: Literal["supported", "contradicted", "not_in_sources"]
    correct_value: str | None
    passage_id: str | None
    quote: str | None
    _unverified: bool = PrivateAttr(default=False)  # D-300: kept without the verifier's verdict (timeout)
    _votes: int | None = PrivateAttr(default=None)  # D-302
    _evidence: list[str] = PrivateAttr(default_factory=list)  # D-302: the relation arm's evidence sentence ids
    _check: bool = PrivateAttr(default=False)  # D-303: "check what was said" (one misheard number), not a correction
    _unverified_reason: str | None = PrivateAttr(default=None)  # D-306: the verifier's failure type
    _attributed: str = PrivateAttr(default="host")  # D-328: "other" = someone else's words or a question to someone
    _cited: list = PrivateAttr(default_factory=list)  # D-372: every passage the relation verdict cites


class FactCheckOutput(BaseModel):
    claims: list[FactClaim]
    reason: str
    # D-328-330: this line on the previous one's reported claims: [{product_id, field, span, stance}]
    _previous_line: list = PrivateAttr(default_factory=list)
    # D-363: the ids of the active fact notes this line fixes, by the model's handles (code maps handle -> id)
    _corrects: list = PrivateAttr(default_factory=list)


# ---- D-296 FACT_RELATION: the evidence by sentence id, then the relation; code builds the quote ------------------

FactRelation = Literal["contradicts", "consistent", "not_in_documents", "uncertain"]


class FactRelationClaim(BaseModel):
    span: str
    product_id: str
    field: FactField
    stated_value: str
    evidence: list[str]  # SOURCE sentence ids ("S12"), "promo", or an offer's promo_id
    relation: FactRelation
    correct_value: str | None


class FactRelationOutput(BaseModel):
    claims: list[FactRelationClaim]


class FactRelationClaimC(FactRelationClaim):
    confidence: float  # D-302 VOTE_CONFIDENCE=self: how sure the model is (0-1); a log field only


class FactRelationOutputC(FactRelationOutput):
    claims: list[FactRelationClaimC]


class FactRelationClaimV2(BaseModel):
    """D-312 FACT_PROMPT=v2: the documents' value is written before the relation is decided."""
    span: str
    product_id: str
    field: FactField
    stated_value: str
    evidence: list[str]
    source_value: str | None  # the value the evidence gives, in its words
    relation: FactRelation
    correct_value: str | None


class FactRelationOutputV2(BaseModel):
    claims: list[FactRelationClaimV2]


class FactRelationClaimV5(BaseModel):
    """D-331 FACT_PROMPT=v5: whose fact it is, decided right after the span; only the host's own (asserted or
    endorsed) facts are compared with the documents."""
    span: str
    stance: Literal["HOST_ASSERTS", "HOST_ENDORSES", "REPORTS_OR_ASKS"]
    product_id: str
    field: FactField
    stated_value: str
    evidence: list[str]
    source_value: str | None
    relation: Literal["contradicts", "consistent", "not_in_documents", "uncertain", "not_checked"]
    correct_value: str | None


class FactRelationOutputV5(BaseModel):
    claims: list[FactRelationClaimV5]


class FactRelationClaimV7(BaseModel):
    """D-345 FACT_PROMPT=v7: v5 plus the stated value re-read with number-word homophones as digits, before the
    relation."""
    span: str
    stance: Literal["HOST_ASSERTS", "HOST_ENDORSES", "REPORTS_OR_ASKS"]
    product_id: str
    field: FactField
    stated_value: str
    evidence: list[str]
    source_value: str | None
    stated_as_heard: str
    relation: Literal["contradicts", "consistent", "not_in_documents", "uncertain", "not_checked"]
    correct_value: str | None


class FactRelationOutputV7(BaseModel):
    claims: list[FactRelationClaimV7]


class FactRelationClaimH(BaseModel):
    """D-328 REPORTED_HOLD: v2's claim, and whose words it is, decided before the rest."""
    span: str
    attributed: Literal["host", "other"]
    product_id: str
    field: FactField
    stated_value: str
    evidence: list[str]
    source_value: str | None
    relation: FactRelation
    correct_value: str | None


class PreviousLineStance(BaseModel):
    """D-329: one fact the last line reported or asked, and what this line does with it."""
    product_id: str
    field: FactField
    span: str  # D-330: the last line's words that state that fact
    stance: Literal["endorses", "rejects"]


class FactRelationOutputH(BaseModel):
    previous_line: list[PreviousLineStance]  # empty: this line neither endorses nor rejects any of them
    claims: list[FactRelationClaimH]


class VerifyOutput(BaseModel):
    """D-300: the verifier's verdict on one candidate alert."""
    evidence: str | None  # the SOURCE sentence id that settles it
    reason: str
    decision: Literal["keep", "reject"]
    severity: Literal["HIGH", "MEDIUM"] | None  # compliance: the final severity; a fact: null


class VerifyOutputC(VerifyOutput):
    """D-303 NUMBER_CHECK: "check" when the only mismatch is one number speech-to-text may have misheard."""
    decision: Literal["keep", "reject", "check"]


class JudgeSingleOutput(UtteranceJudgeOutput):
    facts: FactCheckOutput


# ---- CommentTriage (§7.5) --------------------------------------------------------------------

SLOT_KEYS = ("person_type", "life_stage", "condition", "combined_with", "time_of_day", "variant")


class ConditionSlots(BaseModel):
    """The five slot keys of intents.json, so the model sees them in the schema (D-011)."""

    person_type: str | None
    life_stage: str | None
    condition: str | None
    combined_with: str | None
    time_of_day: str | None
    variant: str | None = None  # D-281: the size or variant the viewer names, matched to the product's variants


class CommentTriageOutput(BaseModel):
    kind: Literal["question", "reaction", "hide"]
    hide_category: Literal["profanity", "harassment", "spam", "link", "personal_info"] | None
    product_id: str | None
    product_basis: Literal["explicit", "context", "content", "unknown"]
    intent: str | None
    condition_slots: ConditionSlots
    canonical_question: str
    group_candidate_id: str | None
    reason: str


class CommentTriageBatchItem(CommentTriageOutput):
    i: int  # index into COMMENTS


class CommentTriageBatchOutput(BaseModel):  # micro-batch triage (PLANNING 5.1.2)
    items: list[CommentTriageBatchItem]


class CommentTriageOutputB(CommentTriageOutput, _ArmB):  # D-187 arm B: a shout-out is a label, not a regex
    shoutout: Literal["purchase", "first_time", "compliment"] | None = None


class CommentTriageBatchItemB(CommentTriageOutputB):
    i: int


class CommentTriageBatchOutputB(BaseModel):
    items: list[CommentTriageBatchItemB]


# ---- AnswerComposer (§7.6) -------------------------------------------------------------------


class Citation(BaseModel):
    passage_id: str
    quote: str


class ComposerOutput(BaseModel):
    answer: str
    citations: list[Citation]
    grounded: bool
    needs_human: bool
    reason: str


class DraftCheckOutput(BaseModel):
    """DraftVerifier (D-126): the LLM check of a composed answer against its cited passages."""
    verdict: Literal["pass", "fail"]
    problems: list[str] = []
    reason: str


# ---- BriefAgent (§7.7) -----------------------------------------------------------------------


class GlossaryTerm(BaseModel):
    term: str
    kind: Literal["brand", "product", "ingredient", "technical", "value"]
    spoken_forms: list[str]
    source_section: str


class PointDraft(BaseModel):
    text: str
    required: bool
    source_section: str


class CautionSlot(BaseModel):
    """D-276: one record caution or direction, by its id, as the BriefAgent would say it."""
    id: str
    kind: Literal["safety", "limit", "direction"]
    say: str


class BriefOutput(BaseModel):
    product_id: str
    glossary: list[GlossaryTerm]
    prompter_points: list[PointDraft]
    reason: str
    document_notes: list[str] = []  # D-272: offer terms that only describe the document (BRIEF_OFFERS=code)
    cautions: list[CautionSlot] = []  # D-276: BRIEF_CAUTIONS=code


# ---- BroadcastSummary (§7.8) -----------------------------------------------------------------


class SummaryOutput(BaseModel):
    headline: str
    highlights: list[str]
    watch_outs: list[str]
    follow_ups: list[str]
