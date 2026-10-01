"""Segments and the product switch state machine (DEV_SPEC §8.1, §8.7.2)."""
from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Literal

from ..models.agent_io import UtteranceJudgeOutput
from ..models.session import Segment, SwitchState
from .reflex import normalise

CueKind = Literal["cue", "cancel", "neutral"]
SwitchEvent = Literal["counting", "pending", "cancelled", "reset", None]


def classify_switch(
    judge: UtteranceJudgeOutput, state: SwitchState, *, on_air: str, next_product: str | None,
    on_air_points: Collection[str], next_points: Collection[str], high_alert_became_active: bool,
    next_named: bool = True,
) -> CueKind:
    """D-090: two steps instead of any two cues.
    - Arm (idle): a transition to the next product, not a quote or an answer, confidence medium or
      high, and the next product's name actually heard (`next_named`).
    - Confirm (counting): a later utterance that states the next product's information (covers at
      least one of its points), not a quote or an answer. A second bare transition does not confirm.
    `state` must already have an expired counting window reset (see `expire`)."""
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
    talk = not sw.is_quote and judge.answer.utterance_type != "answer"
    if state.status == "idle":
        if (talk and next_named and sw.is_transition and sw.target_product_id == next_product
                and sw.confidence in ("medium", "high")):
            return "cue"
        return "neutral"
    if state.status == "counting" and talk and any(p in next_points for p in covered):
        return "cue"
    return "neutral"


def expire(state: SwitchState, now: int, window_sec: int) -> SwitchState:
    """A counting state whose window is over is idle again (nothing shown on the host)."""
    if state.status == "counting" and state.first_cue_at is not None and now - state.first_cue_at > window_sec * 1000:
        return SwitchState(last_commit=state.last_commit)
    return state


def names_product(text: str, names: Collection[str]) -> bool:
    """True when one of the product's names is heard as whole words (case and punctuation ignored)."""
    norm = f" {normalise(text)} "
    return any(f" {normalise(n)} " in norm for n in names if normalise(n))


def step_switch(
    state: SwitchState, kind: CueKind, *, transcript_id: str, next_product: str | None, now: int,
    cues_needed: int, window_sec: int, cancel_window_sec: int,
) -> tuple[SwitchState, SwitchEvent]:
    """Apply one judge result to the switch state. Returns the new state and the event to emit."""
    s = expire(state, now, window_sec).model_copy(deep=True)  # window over: back to idle, nothing on the host
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


def replace_cue(state: SwitchState, old_id: str, new_id: str) -> SwitchState:
    """D-088: a merged judgment confirms the cue its first fragment already counted. Same cue,
    new transcript id, no new count."""
    s = state.model_copy(deep=True)
    s.cue_transcript_ids = [new_id if x == old_id else x for x in s.cue_transcript_ids]
    return s


def withdraw_cue(state: SwitchState, transcript_id: str) -> tuple[SwitchState, SwitchEvent]:
    """D-088: a merged judgment replaces its first fragment's cue and is not a cue itself, so the
    fragment's cue no longer counts. Returns ("cancelled" when a pending switch or the whole count
    is withdrawn, else "counting")."""
    if transcript_id not in state.cue_transcript_ids:
        return state, None
    s = state.model_copy(deep=True)
    s.cue_transcript_ids.remove(transcript_id)
    s.cue_count = max(0, s.cue_count - 1)
    if s.cue_count == 0:
        return SwitchState(last_commit=s.last_commit), "cancelled"
    was_pending = s.status == "pending"
    s.status, s.commit_at = "counting", None
    return s, "cancelled" if was_pending else "counting"


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
