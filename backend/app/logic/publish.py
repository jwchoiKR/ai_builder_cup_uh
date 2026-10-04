"""Host spoken answer -> publish decision (DEV_SPEC §8.6)."""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from ..models.agent_io import FactCheckOutput, UtteranceJudgeOutput
from ..models.session import Answer, QuestionGroup
from .corrections import _numbers
from .reflex import normalise

# D-110: the host sounds unsure or takes the answer back. A hedge never auto-posts, whatever the judge says.
UNSURE = re.compile(
    r"\b(i think|i guess|i believe|maybe|perhaps|probably|not (?:totally |really |entirely |100% )?sure"
    r"|don'?t quote me|let me (?:check|double-check|confirm)|double-check|wait,? no|sorry,? (?:no|wait))\b", re.I)

Action = Literal["post", "confirm_ai", "verbal_not_posted", "none"]


@dataclass(frozen=True)
class PublishDecision:
    action: Action
    group_id: str | None = None
    reason: str = ""


def spoken_numbers(text: str) -> set[str]:
    """Numbers as said or written: "fifty mils" -> {"50"}, "S$36.00" -> {"36"}, "4%" -> {"4"},
    "zero point two" -> {"0.2"}.
    A lone "one" is ignored ("after one use" is not a claimed number)."""
    tokens = [w for w in normalise(text).replace("$", " ").split() if w != "one"]
    words = _numbers(tokens)
    merged: list[str] = []  # D-116: spoken decimals, "five point five" -> "5.5"
    i = 0
    while i < len(words):
        if i + 2 < len(words) and words[i + 1] == "point" and words[i].isdigit() and words[i + 2].isdigit():
            merged.append(f"{words[i]}.{words[i + 2]}")
            i += 3
        else:
            merged.append(words[i])
            i += 1
    out = set()
    for w in merged:
        if re.fullmatch(r"\d+(\.\d+)?", w):
            out.add(w.rstrip("0").rstrip(".") if "." in w else w)
    return out


def verbal_check(utterance: str, draft: str, other_drafts: Iterable[str] = ()) -> str | None:
    """D-110: code checks on top of the judge before a host's spoken answer is auto-posted.
    The host may say less than the draft, but every number they say must be in the draft (or in
    another offered draft: two questions answered at once), and they must not sound unsure.
    Returns the reason to hold the post, or None."""
    if UNSURE.search(utterance):
        return "host sounded unsure or took it back"
    allowed = spoken_numbers(draft).union(*(spoken_numbers(d) for d in other_drafts))
    if not spoken_numbers(utterance) <= allowed:
        return "a number differs from the verified draft"
    return None


def decide(
    judge: UtteranceJudgeOutput,
    offered: Mapping[str, Answer | None],
    group: QuestionGroup | None,
    answer: Answer | None,
    *,
    high_alert_active: bool,
    facts: FactCheckOutput | None,
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
        utterance, answer.text, [x.text for g, x in offered.items() if g != gid and x is not None])
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
