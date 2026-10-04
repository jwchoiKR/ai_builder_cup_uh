"""Host top-N question slots (DEV_SPEC §8.11). Pure functions; the runtime applies the result."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from ..models.session import HostSlot, QuestionGroup

RECALL_BLOCK_MS = 60_000
_GONE = frozenset({"answered", "rejected", "closed"})


class HostQueueFull(Exception):
    """All slots are pinned (§8.11)."""


@dataclass(frozen=True)
class QueueParams:
    top_n: int
    min_dwell_ms: int
    repeat_threshold: int


def is_candidate(
    g: QuestionGroup, *, on_air: str | None, scope: str, now: int, repeat_threshold: int
) -> bool:
    if g.route == "HOST" and (g.status in ("ready", "composing")
                              or (g.status == "needs_review" and g.route_reason == "unresolved_product")):
        pass  # D-113: drafting and "which product?" questions wait in the host's list too
    elif g.status == "auto_answered" and len(g.unique_author_ids) >= repeat_threshold and not g.host_confirmed:
        pass
    else:
        return False
    if not (g.product_id == on_air or (g.product_id is None and scope == "multi")):
        return False
    if g.host_verbal_answer_transcript_id is not None:
        return False
    return not (g.recalled_at is not None and now - g.recalled_at < RECALL_BLOCK_MS)


def _pinned_still_valid(g: QuestionGroup | None, on_air: str | None, scope: str, segment_started_at: int | None) -> bool:
    if g is None or g.status in _GONE or g.host_verbal_answer_transcript_id or g.host_confirmed:
        return False
    if g.product_id == on_air or (g.product_id is None and scope == "multi"):
        return True
    # Another product's group stays only if it was pinned after the current segment started.
    pinned_at = g.pinned_by_operator_at or 0
    return segment_started_at is None or pinned_at >= segment_started_at


def compute_slots(
    slots: list[HostSlot],
    groups: Mapping[str, QuestionGroup],
    scores: Mapping[str, float],
    *,
    on_air: str | None,
    segment_started_at: int | None,
    now: int,
    params: QueueParams,
    scope_of: Callable[[str], str],
) -> list[HostSlot]:
    def cand(g: QuestionGroup) -> bool:
        return is_candidate(g, on_air=on_air, scope=scope_of(g.intent), now=now,
                            repeat_threshold=params.repeat_threshold)

    pinned = [s for s in slots if s.pinned
              and _pinned_still_valid(groups.get(s.group_id), on_air,
                                      scope_of(groups[s.group_id].intent) if s.group_id in groups else "single",
                                      segment_started_at)]
    autos = [s for s in slots if not s.pinned and s.group_id in groups and cand(groups[s.group_id])]
    keep = {s.group_id for s in autos if now - s.on_host_since < params.min_dwell_ms}
    dwell_over = [s for s in autos if s.group_id not in keep]
    on_host = {s.group_id for s in slots}
    outside = [g for g in groups.values() if g.group_id not in on_host and cand(g)]

    free = max(0, params.top_n - len(pinned) - len(keep))
    # Holders whose dwell is over compete with outside candidates; a tie keeps the holder.
    pool = [(scores.get(s.group_id, 0.0), 1, s.group_id) for s in dwell_over]
    pool += [(scores.get(g.group_id, 0.0), 0, g.group_id) for g in outside]
    pool.sort(key=lambda t: (t[0], t[1], -groups[t[2]].first_at), reverse=True)
    chosen = [gid for _, _, gid in pool[:free]]

    retained = keep | {gid for gid in chosen if gid in on_host}
    newcomers = [gid for gid in chosen if gid not in on_host]
    result = list(pinned)
    for s in autos:  # keep places stable: a newcomer takes the place of the item it replaces
        if s.group_id in retained:
            result.append(s)
        elif newcomers:
            result.append(HostSlot(group_id=newcomers.pop(0), pinned=False, on_host_since=now))
    result.extend(HostSlot(group_id=gid, pinned=False, on_host_since=now) for gid in newcomers)
    return result[: params.top_n]


def push_slot(
    slots: list[HostSlot], group_id: str, scores: Mapping[str, float], *, now: int, top_n: int
) -> list[HostSlot]:
    """Operator push: pin the group. When full, the lowest-scored auto item leaves even within
    its dwell; when every slot is pinned, raise HostQueueFull."""
    rest = [s for s in slots if s.group_id != group_id]
    if len(rest) >= top_n:
        autos = [s for s in rest if not s.pinned]
        if not autos:
            raise HostQueueFull("Host queue is full. Recall a question first.")
        lowest = min(autos, key=lambda s: scores.get(s.group_id, 0.0))
        rest = [s for s in rest if s.group_id != lowest.group_id]
    pinned = [s for s in rest if s.pinned]
    autos = [s for s in rest if not s.pinned]
    return pinned + [HostSlot(group_id=group_id, pinned=True, on_host_since=now)] + autos


def remove_slot(slots: list[HostSlot], group_id: str) -> list[HostSlot]:
    return [s for s in slots if s.group_id != group_id]
