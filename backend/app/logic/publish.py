"""Host spoken answer -> publish decision (DEV_SPEC §8.6)."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from ..models.agent_io import FactCheckOutput, UtteranceJudgeOutput
from ..models.session import Answer, QuestionGroup
from .lexicon import Lexicon

Action = Literal["post", "confirm_ai", "verbal_not_posted", "none"]


@dataclass(frozen=True)
class PublishDecision:
    action: Action
    group_id: str | None = None
    reason: str = ""


def verbal_check(utterance: str, draft: str, other_drafts: Iterable[str], lex: Lexicon) -> str | None:
    """D-110: code checks on top of the judge before a host's spoken answer is auto-posted.
    The host may say less than the draft, but every number they say must be in the draft (or in
    another offered draft: two questions answered at once), and they must not sound unsure.
    Returns the reason to hold the post, or None."""
    if lex.is_unsure(utterance):
        return "host sounded unsure or took it back"
    allowed = lex.spoken_numbers(draft).union(*(lex.spoken_numbers(d) for d in other_drafts))
    said = lex.spoken_numbers(utterance)
    # D-174: the same duration in other units ("a week later" for "after 7 days") is the same number
    hours = {h for d in (draft, *other_drafts) for _, h in lex.durations(d)}
    said -= {n for n, h in lex.durations(utterance) if n is not None and h in hours}
    if not said <= allowed:
        return "a number differs from the verified draft"
    return None


RELINK_MIN_COVERAGE = 0.5  # D-175: share of a draft's claim words the line must say to be asked about again


def relink_candidate(utterance: str, drafts: Mapping[str, str], lex: Lexicon) -> str | None:
    """D-175 (sealed verbal set: ~1 in 150 spoken answers linked to nothing): the one offered draft the line seems
    to answer, so the context judge is asked once more about that question alone. Every number the line says is
    in the draft, the host does not sound unsure, and the line says at least RELINK_MIN_COVERAGE of the draft's
    claim words. None when no draft or more than one qualifies. Never a post by itself."""
    heard = lex.content_words(utterance)
    fits = [gid for gid, text in drafts.items()
            if text and verbal_check(utterance, text, [], lex) is None
            and lex.coverage(lex.claim_words(text), heard) >= RELINK_MIN_COVERAGE]
    return fits[0] if len(fits) == 1 else None


def decide(
    judge: UtteranceJudgeOutput,
    offered: Mapping[str, Answer | None],
    group: QuestionGroup | None,
    answer: Answer | None,
    *,
    high_alert_active: bool,
    facts: FactCheckOutput | None,
    lex: Lexicon,
    utterance: str = "",
    current_key: str | None = None,
) -> PublishDecision:
    """`offered` maps each question shown to the judge to the verified answer shown with it."""
    a = judge.answer
    # 1. the host answered a question that was offered to the judge
    if not (a.is_answer and a.matched_group_id in offered and group is not None):
        return PublishDecision("none", reason="not an answer to an offered question")
    gid = group.group_id
    if a.utterance_type != "answer":  # D-110: a read-out, quote or question back is never a post
        return PublishDecision("verbal_not_posted", gid, f"utterance type {a.utterance_type}")
    shown = offered.get(gid)
    # D-110: bound to the answer the host saw, and to the current promo and document state
    stale = (answer is None or shown is None or shown.answer_id != answer.answer_id
             or (current_key is not None and answer.cache_key is not None and answer.cache_key != current_key))
    held = None if answer is None else verbal_check(
        utterance, answer.text, [x.text for g, x in offered.items() if g != gid and x is not None], lex)
    consistent = a.consistent_with_suggested and not stale and held is None  # 2.
    if a.consistent_with_suggested and group.status == "auto_answered":  # a mark only: nothing is posted
        return PublishDecision("confirm_ai", gid, "already answered by AI")
    verified = answer is not None and answer.verified and group.route != "OPERATOR"  # 3.
    violation = any(not v.is_negated and not v.is_quoted for v in judge.compliance.violations)  # 4.
    contradicted = facts is not None and any(c.verdict == "contradicted" for c in facts.claims)  # 5.
    unpublished = group.published_message_id is None and group.status not in ("answered", "auto_answered")  # 6.
    if consistent and verified and unpublished and not high_alert_active and not violation and not contradicted:
        return PublishDecision("post", gid)
    if not consistent or not verified or not unpublished:
        reason = ("stale answer" if stale else held or "inconsistent") if not consistent else (
            "no verified answer" if not verified else "already answered")
        return PublishDecision("verbal_not_posted", gid, reason)
    return PublishDecision("none", gid, "compliance alert or contradicted fact")
