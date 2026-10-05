"""Grouping of same-meaning questions (DEV_SPEC §8.9.1)."""
from __future__ import annotations

import re
from collections.abc import Iterable

from ..models.session import QuestionGroup

CLOSED_STATUSES = frozenset({"closed", "rejected"})


def is_open(g: QuestionGroup) -> bool:
    return g.status not in CLOSED_STATUSES


def slots_compatible(a: dict[str, str | None], b: dict[str, str | None]) -> bool:
    """Compatible when no slot key has two different non-null values."""
    return all(a.get(k) is None or b.get(k) is None or a[k] == b[k] for k in set(a) | set(b))


def slots_equal(a: dict[str, str | None], b: dict[str, str | None]) -> bool:
    """D-214: the same stated conditions; an empty condition is not "any" condition."""
    return {k: v for k, v in a.items() if v is not None} == {k: v for k, v in b.items() if v is not None}


def normalise_question(q: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s%$]", " ", q.lower())).strip()


SINGLE_QUESTION_INTENTS = frozenset({
    "price", "set_price", "volume", "fragrance", "texture", "shelf_life", "origin", "packaging",
    "skin_type_suitability", "pregnancy_breastfeeding", "age_suitability",
})

def find_group(
    groups: Iterable[QuestionGroup],
    *,
    product_id: str | None,
    intent: str,
    slots: dict[str, str | None],
    canonical_question: str,
    candidate_id: str | None,
) -> QuestionGroup | None:
    def target(g: QuestionGroup) -> bool:
        return is_open(g) and g.product_id == product_id and g.intent == intent

    targets = [g for g in groups if target(g)]
    if candidate_id is not None:
        # D-214 (full review P3): the model decides that two questions have the same answer; code only checks the
        # product, the intent and that no stated condition conflicts
        for g in targets:
            if g.group_id == candidate_id and slots_compatible(g.condition_slots, slots):
                return g
    # without the model's pick, code joins only the same question with the same conditions
    open_groups = [g for g in targets if slots_equal(g.condition_slots, slots)]
    norm = normalise_question(canonical_question)
    for g in sorted(open_groups, key=lambda g: g.last_at, reverse=True):
        if normalise_question(g.canonical_question) == norm:
            return g
    # D-135 (comment-flow recall 74-82%): for intents that hold one question per product and slots, the
    # only open group that fits is the same question, whatever the wording ("oily skin can use anot?")
    if intent in SINGLE_QUESTION_INTENTS and len(open_groups) == 1:
        return open_groups[0]
    return None


def join_group(g: QuestionGroup, comment_id: str, author_id: str, now: int) -> bool:
    """Add a member. Returns True when the author is a new unique asker."""
    if comment_id not in g.member_comment_ids:
        g.member_comment_ids.append(comment_id)
    new_author = author_id not in g.unique_author_ids
    if new_author:
        g.unique_author_ids.append(author_id)
    g.last_at = max(g.last_at, now)
    g.version += 1
    return new_author


def ttl_expired(g: QuestionGroup, now: int, ttl_sec: int) -> bool:
    return is_open(g) and g.host_slot != "on_host" and now - g.last_at >= ttl_sec * 1000
