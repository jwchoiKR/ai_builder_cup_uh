"""Host spoken answer -> publish decision (DEV_SPEC §8.6)."""
from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Literal

from ..models.agent_io import FactCheckOutput, UtteranceJudgeOutput
from ..models.session import Answer, QuestionGroup

Action = Literal["post", "confirm_ai", "verbal_not_posted", "none"]


@dataclass(frozen=True)
class PublishDecision:
    action: Action
    group_id: str | None = None
    reason: str = ""


def decide(
    judge: UtteranceJudgeOutput,
    offered_group_ids: Collection[str],
    group: QuestionGroup | None,
    answer: Answer | None,
    *,
    high_alert_active: bool,
    facts: FactCheckOutput | None,
) -> PublishDecision:
    a = judge.answer
    # 1. the host answered a question that was offered to the judge
    if not (a.is_answer and a.matched_group_id in offered_group_ids and group is not None):
        return PublishDecision("none", reason="not an answer to an offered question")
    gid = group.group_id
    consistent = a.consistent_with_suggested  # 2.
    if consistent and group.status == "auto_answered":
        return PublishDecision("confirm_ai", gid, "already answered by AI")
    verified = answer is not None and answer.verified and group.route != "OPERATOR"  # 3.
    violation = any(not v.is_negated and not v.is_quoted for v in judge.compliance.violations)  # 4.
    contradicted = facts is not None and any(c.verdict == "contradicted" for c in facts.claims)  # 5.
    unpublished = group.published_message_id is None and group.status not in ("answered", "auto_answered")  # 6.
    if consistent and verified and unpublished and not high_alert_active and not violation and not contradicted:
        return PublishDecision("post", gid)
    if not consistent or not verified or not unpublished:
        return PublishDecision("verbal_not_posted", gid,
                               "inconsistent" if not consistent else "no verified answer" if not verified else "already answered")
    return PublishDecision("none", gid, "compliance alert or contradicted fact")
