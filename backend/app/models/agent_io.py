"""Structured outputs of the LLM agents (DEV_SPEC §7). These classes are also the JSON schemas
sent to the model, so field names and order follow the prompt files exactly."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

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


# ---- FactChecker (§7.4) ----------------------------------------------------------------------

FactField = Literal[
    "price", "set_price", "promo", "volume", "ingredient", "ingredient_amount", "test_result",
    "usage", "texture", "fragrance", "packaging", "origin", "shelf_life", "other",
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


class FactCheckOutput(BaseModel):
    claims: list[FactClaim]
    reason: str


class JudgeSingleOutput(UtteranceJudgeOutput):
    facts: FactCheckOutput


# ---- CommentTriage (§7.5) --------------------------------------------------------------------

SLOT_KEYS = ("skin_type", "life_stage", "condition", "combined_with", "time_of_day")


class ConditionSlots(BaseModel):
    """The five slot keys of intents.json, so the model sees them in the schema (D-011)."""

    skin_type: str | None
    life_stage: str | None
    condition: str | None
    combined_with: str | None
    time_of_day: str | None


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


class BriefOutput(BaseModel):
    product_id: str
    glossary: list[GlossaryTerm]
    prompter_points: list[PointDraft]
    reason: str


# ---- BroadcastSummary (§7.8) -----------------------------------------------------------------


class SummaryOutput(BaseModel):
    headline: str
    highlights: list[str]
    watch_outs: list[str]
    follow_ups: list[str]
