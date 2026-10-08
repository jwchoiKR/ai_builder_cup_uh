"""Question groups: open or closed, members, time to live. Questions are not grouped by meaning (a question joins
a group only when a viewer repeats the same words: pipelines/comments._same_words_group)."""
from __future__ import annotations

import re

from ..models.session import QuestionGroup

CLOSED_STATUSES = frozenset({"closed", "rejected"})


def is_open(g: QuestionGroup) -> bool:
    return g.status not in CLOSED_STATUSES


def normalise_question(q: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s%$]", " ", q.lower())).strip()


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
