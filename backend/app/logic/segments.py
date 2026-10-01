"""Segments and the product switch state machine (DEV_SPEC §8.1, §8.7.2)."""
from __future__ import annotations

from collections.abc import Sequence

from ..models.session import Segment


def segment_at(segments: Sequence[Segment], t: int) -> Segment | None:
    """The segment whose [started_at, ended_at) contains t; None before the first segment; the last
    segment after the session ended."""
    ordered = sorted(segments, key=lambda s: s.started_at)
    if not ordered or t < ordered[0].started_at:
        return None
    for s in ordered:
        if s.started_at <= t and (s.ended_at is None or t < s.ended_at):
            return s
    return ordered[-1]


def open_segment(segments: Sequence[Segment]) -> Segment | None:
    live = [s for s in segments if s.ended_at is None]
    return max(live, key=lambda s: s.started_at) if live else None
