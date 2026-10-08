"""What an asker is told about their question while it has no posted reply.

Derived by code from the question's group; no model output is read. The value is the only thing about a group
that reaches a viewer: no group id, intent, route reason or draft.
"""
from __future__ import annotations

from typing import Literal

from ..models.session import QuestionGroup

ReplyStatus = Literal["checking", "host", "team", "answered"]

# the message kinds that reply to comments; a published one makes its comments "answered"
REPLY_KINDS = frozenset({"ai_answer", "host_answer", "brand_answer"})


def waiting_status(g: QuestionGroup) -> ReplyStatus | None:
    """The status of a member no published reply addresses yet ("answered" comes from the reply itself)."""
    if g.status in ("rejected", "closed"):
        return None  # nothing is promised any more, so the line under the question goes away
    if g.status in ("new", "composing", "auto_answered", "answered"):
        # a reply is being prepared, or was posted before this asker joined and theirs follows
        return "checking"
    if g.host_slot == "on_host" or (g.route == "HOST" and g.status == "ready"):
        return "host"
    return "team"  # the operator's queue, also when the product information has no verified answer
