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


class ContextPrompter(BaseModel):
    """D-450: the context judge's prompter part: cues and the switch (the prompter judge ticks the points)."""
    covered_cue_ids: list[str]
    switch: SwitchCue


class ContextOutput(BaseModel):
    answer: AnswerLink
    prompter: ContextPrompter
    reason: str


# ---- D-187 design arm B: the meaning the model returns, which code only checks ------------------------------
# Subclasses of the arm-A outputs, used only under DESIGN_ARM B or C. Their extra fields have defaults so a mock
# reply still validates, but the schema sent to the model lists every field as required.


def _all_required(schema: dict) -> None:
    schema["required"] = list(schema.get("properties", {}))


class _ArmB(BaseModel):
    model_config = ConfigDict(json_schema_extra=_all_required)


class AlertCheck(_ArmB):
    """D-356: the verdict on one ACTIVE_ALERTS entry, named by its per-call handle (A1, A2 ...)."""
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
@functools.cache
def with_switch_naming(model: type[BaseModel]) -> type[BaseModel]:
    """D-351: the context output with `SwitchCueN` in place of `SwitchCue` (D-415: the only switch)."""
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


def with_same_as(model: type[BaseModel], list_field: str) -> type[BaseModel]:
    """D-403/D-406: the same output with `same_as` per violation (compliance) or per claim (facts), asked for only on a
    merged line's re-judgment (a line speech-to-text split): the handle of the listed alert or note it repeats."""
    if list_field == "violations":
        comp = model.model_fields["compliance"].annotation
        item = comp.model_fields["violations"].annotation.__args__[0]
        base = item if issubclass(item, _ArmB) else (item, _ArmB)
        v = create_model(f"{item.__name__}S", __base__=base, same_as=(str | None, None))
        c = create_model(f"{comp.__name__}S", __base__=comp, violations=(list[v], ...))
        return create_model(f"{model.__name__}S", __base__=model, compliance=(c, ...))
    item = model.model_fields["claims"].annotation.__args__[0]
    v = create_model(f"{item.__name__}S", __base__=item, same_as=(str | None, None))
    return create_model(f"{model.__name__}S", __base__=model, claims=(list[v], ...))


class CorrectionQuote(_ArmB):
    alert_id: str
    quote: str  # the exact words of the utterance that make the correction


class CorrectionB(Correction, _ArmB):
    quotes: list[CorrectionQuote] = []


class ViolationB(Violation, _ArmB):
    pass


class ComplianceB(Compliance, _ArmB):
    violations: list[ViolationB]


class ComplianceOutputB(ComplianceOutput, _ArmB):
    compliance: ComplianceB
    correction: CorrectionB


def _cited_schema(s: dict) -> None:
    """D-358: the model writes the citation and its quote first; `rule_id` is code's (from the citation). D-400:
    `severity` is code's too (from the citation type), so it is not asked for."""
    props = dict(s.get("properties", {}))
    props.pop("rule_id", None)
    props.pop("severity", None)
    props.pop("cited_title", None)  # D-433: code's, not asked
    first = ["citation", "quote", "span", "is_negated", "is_quoted"]
    s["properties"] = {**{k: props.pop(k) for k in first if k in props}, **props}
    s["required"] = list(s["properties"])


class ViolationO(Violation, _ArmB):
    """D-358: a violation cited from a regulation original (no rule JSON): the document and section as written in the
    original ("<document>#<section>"), a short quote from it, and the severity the model chose by the prompt's
    criteria. Code sets `rule_id` from the citation."""
    model_config = ConfigDict(json_schema_extra=_cited_schema)
    citation: str
    quote: str
    rule_id: str = ""
    severity: Literal["HIGH", "MEDIUM"] = "HIGH"  # D-400: set by code from the citation type, never asked
    cited_title: str = ""  # D-433: set by code: the cited document's readable name and the section


class ComplianceO(Compliance, _ArmB):
    violations: list[ViolationO]


class ComplianceOutputO(ComplianceOutput, _ArmB):
    compliance: ComplianceO


class AnswerLinkB(AnswerLink, _ArmB):
    numbers_said: list[str] = []  # every number the host said, as digits, in the suggested answer's unit
    hedged: bool = False  # the host sounded unsure or took it back


class ContextOutputQ(BaseModel):
    """D-335: the context verdict, first saying whether the next line is expected to resolve this one."""
    expects_resolution: bool
    answer: AnswerLink
    prompter: ContextPrompter
    reason: str


class CoveredPoint(BaseModel):
    """D-450: the host's words first, then the point they say (host_words is for the log; code reads point_id)."""
    host_words: str
    point_id: str


class PrompterJudgeOutput(BaseModel):
    covered: list[CoveredPoint]


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
    say: str | None = None  # D-396: the model's say line for a contradiction (relation arm v5)
    same_as: str | None = None  # D-403/D-406: a merged line's: the note this claim repeats (an id once mapped)
    _evidence: list[str] = PrivateAttr(default_factory=list)  # D-302: the relation arm's evidence sentence ids
    _cited: list = PrivateAttr(default_factory=list)  # D-372: every passage the relation verdict cites


class FactCheckOutput(BaseModel):
    claims: list[FactClaim]
    reason: str
    # D-363: the ids of the active fact notes this line fixes, by the model's handles (code maps handle -> id)
    _corrects: list = PrivateAttr(default_factory=list)


# ---- D-296: the evidence by sentence id, then the relation; code builds the quote ------------------

class FactRelationClaimV5(BaseModel):
    """D-331 FACT_PROMPT=v5: whose fact it is, decided right after the span; only the host's own (asserted or
    endorsed) facts are compared with the documents."""
    span: str
    stance: Literal["HOST_ASSERTS", "HOST_ENDORSES", "REPORTS_OR_ASKS"]
    product_id: str
    field: FactField
    stated_value: str
    evidence: list[str]  # SOURCE sentence ids ("S12"), "promo", or an offer's promo_id
    source_value: str | None
    relation: Literal["contradicts", "consistent", "not_in_documents", "uncertain", "not_checked"]
    correct_value: str | None
    say: str | None = None  # D-396: the line the host says to fix it (contradicts only)


class FactRelationOutputV5(BaseModel):
    claims: list[FactRelationClaimV5]


class FactRelationClaimV5Cot(BaseModel):
    """D-456 FACT_PROMPT=v5_cot (a probe arm): v5 with a short `reasoning` FIRST (Vertex writes the schema's properties
    in order), the line's net meaning against the evidence. Code decides nothing from it; the agent-call log keeps it."""
    reasoning: str
    span: str
    stance: Literal["HOST_ASSERTS", "HOST_ENDORSES", "REPORTS_OR_ASKS"]
    product_id: str
    field: FactField
    stated_value: str
    evidence: list[str]
    source_value: str | None
    relation: Literal["contradicts", "consistent", "not_in_documents", "uncertain", "not_checked"]
    correct_value: str | None
    say: str | None = None


class FactRelationOutputV5Cot(BaseModel):
    claims: list[FactRelationClaimV5Cot]


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
    group_candidate_id: str | None = None  # unused: questions are not grouped by meaning (older recordings carry it)
    language: str | None = None  # ISO 639-1 of the comment ("zh-Hant" for Traditional Chinese)
    translation_en: str | None = None  # a comment in another language, in English (the team reads it)
    # stream_issue: the viewer reports a problem with the stream; injection: the comment gives the system orders
    signal: Literal["stream_issue", "injection"] | None = None
    second_question: str | None = None  # the other question of a comment that asks two different things, in English
    # must a person approve the reply before viewers see it, and why (None: triage did not say)
    needs_approval: bool | None = None
    approval_reason: Literal["health", "claim", "test_results", "certification", "personal", "outside",
                             "host_line", "unclear"] | None = None
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


class ReplyTranslationOutput(BaseModel):
    """ReplyTranslator: a posted reply in an asker's language."""
    translation: str
    reason: str = ""


class InsightTopic(BaseModel):
    label: str
    buying: bool = False  # questions a viewer asks when deciding to buy, or how to buy
    keys: list[str] = []


class CommentInsightsOutput(BaseModel):
    """CommentInsights: the questions of a broadcast sorted into topics. No numbers: code counts."""
    topics: list[InsightTopic] = []
    notes: list[str] = []


# ---- BroadcastSummary (§7.8) -----------------------------------------------------------------


class SummaryOutput(BaseModel):
    headline: str
    highlights: list[str]
    watch_outs: list[str]
    follow_ups: list[str]
