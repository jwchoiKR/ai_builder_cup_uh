"""Structured outputs of the LLM agents (DEV_SPEC §7). These classes are also the JSON schemas
sent to the model, so field names and order follow the prompt files exactly."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, PrivateAttr

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


class FactCheckOutput(BaseModel):
    claims: list[FactClaim]
    reason: str
    # D-328-330: this line on the previous one's reported claims: [{product_id, field, span, stance}]
    _previous_line: list = PrivateAttr(default_factory=list)


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


class ReplyPhraseOutput(BaseModel):
    """ReplyPhraser: the wording of a record answer."""
    reply: str
    reason: str = ""


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


class DraftCheckOutput(BaseModel):
    """DraftVerifier (D-126): the LLM check of a composed answer against its cited passages."""
    # whether a viewer who reads only the reply got exactly what they asked for, stated by the source in so many
    # words; decided before the verdict, and anything but "direct" keeps the draft from being posted
    answers: Literal["direct", "partial", "no"] = "direct"
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
