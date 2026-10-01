"""Segments and the product switch state machine (DEV_SPEC §8.1, §8.7.2)."""
from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Literal

from ..models.agent_io import UtteranceJudgeOutput
from ..models.session import Segment, SwitchState

CueKind = Literal["cue", "cancel", "neutral"]
SwitchEvent = Literal["counting", "pending", "cancelled", "reset", None]


def classify_switch(
    judge: UtteranceJudgeOutput, state: SwitchState, *, on_air: str, next_product: str | None,
    on_air_points: Collection[str], next_points: Collection[str], high_alert_became_active: bool,
) -> CueKind:
    sw = judge.prompter.switch
    covered = judge.prompter.covered_point_ids
    if high_alert_became_active:
        return "cancel"
    if sw.is_transition and sw.target_product_id == on_air:
        return "cancel"  # the host goes back to the on-air product
    if covered and all(p in on_air_points for p in covered):
        return "cancel"
    if next_product is None:
        return "neutral"  # no automatic switch after the last product
    if (sw.is_transition and not sw.is_quote and sw.target_product_id == next_product
            and sw.confidence in ("medium", "high") and judge.answer.utterance_type != "answer"):
        return "cue"
    if state.status == "counting" and not sw.is_quote and any(p in next_points for p in covered):
        return "cue"  # continuation about the new product
    return "neutral"


def step_switch(
    state: SwitchState, kind: CueKind, *, transcript_id: str, next_product: str | None, now: int,
    cues_needed: int, window_sec: int, cancel_window_sec: int,
) -> tuple[SwitchState, SwitchEvent]:
    """Apply one judge result to the switch state. Returns the new state and the event to emit."""
    s = state.model_copy(deep=True)
    if s.status == "counting" and s.first_cue_at is not None and now - s.first_cue_at > window_sec * 1000:
        s = SwitchState(last_commit=s.last_commit)  # window expired: back to idle, nothing on the host
    if kind == "cancel":
        if s.status == "pending":
            return SwitchState(last_commit=s.last_commit), "cancelled"
        if s.status == "counting":
            return SwitchState(last_commit=s.last_commit), "reset"
        return s, None
    if kind != "cue" or s.status == "pending":
        return s, None
    if s.status == "idle":
        s = SwitchState(status="counting", target_product_id=next_product, cue_count=1,
                        cue_transcript_ids=[transcript_id], first_cue_at=now, last_commit=s.last_commit)
    else:
        s.cue_count += 1
        s.cue_transcript_ids.append(transcript_id)
    if s.cue_count >= cues_needed:
        s.status, s.commit_at = "pending", now + cancel_window_sec * 1000
        return s, "pending"
    return s, "counting"


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
