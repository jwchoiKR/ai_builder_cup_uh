"""Compliance alert lifecycle (DEV_SPEC §8.4): active -> corrected | dismissed | cleared. D-410: no provisional state
(the regex pre-scan is gone; only the judge raises an alert).

Functions change the given Alert objects in place and return the ones they created or changed;
the pipeline stores them and emits events.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence

from ..models.agent_io import UtteranceJudgeOutput
from ..models.session import Alert, Transcript

NewId = Callable[[str], str]


def high_alert_active(alerts: Sequence[Alert]) -> bool:
    return any(a.kind == "compliance" and a.status == "active" and a.severity == "HIGH" for a in alerts)


def apply_judge_compliance(
    judge: UtteranceJudgeOutput, t: Transcript, product_id: str,
    new_id: NewId, now: int, listed: dict[str, Alert] | None = None,
) -> tuple[list[Alert], list[Alert], list[str]]:
    """§8.4.1. Returns (changed, created, closed).

    D-387 (user): each violation the model returns is its own alert, also two claims under one rule or section. D-397:
    no text dedupe; a merged line's verdict replaces its chain's alerts (pipelines/utterances.py). D-403 (user, option
    A; D-406: only a merged line's, `listed` is its chain): a violation the model marks as repeating a listed alert
    (`same_as`, an id of `listed`) raises nothing new: an
    active one is kept (its span and wording take the new verdict; it is in `changed`), a closed one stays closed (its
    id is in `closed`). Code never decides that two claims are one."""
    changed: list[Alert] = []
    created: list[Alert] = []
    closed: list[str] = []
    for v in judge.compliance.violations:
        if v.is_negated or v.is_quoted:
            continue
        same = (listed or {}).get(getattr(v, "same_as", None) or "")
        if same is not None:
            if same.status == "active":
                same.span, same.say_instead = v.span, v.say_instead or same.say_instead
                same.quote, same.citation = getattr(v, "quote", None) or same.quote, getattr(v, "citation", None) or same.citation
                same.cited_title = getattr(v, "cited_title", None) or same.cited_title  # D-433
                changed.append(same)
            else:
                closed.append(same.alert_id)
            continue
        created.append(Alert(alert_id=new_id("al_"), kind="compliance", status="active", transcript_id=t.transcript_id,
                             product_id=getattr(v, "product_id", None) or product_id,  # D-349
                             rule_id=v.rule_id, severity=v.severity, span=v.span,
                             say_instead=v.say_instead or None, created_at=now, shown_at=now,
                             quote=getattr(v, "quote", None), citation=getattr(v, "citation", None),
                             cited_title=getattr(v, "cited_title", None) or None))
    return changed, created, closed


def apply_corrections(alerts: Sequence[Alert], corrects_ids: Sequence[str], t: Transcript, now: int) -> list[Alert]:
    """The listed alerts, each already checked (D-089, D-098), become corrected. D-117: no longer every
    other alert of the same transcript (§8.4.5): retracting one claim must not clear another one."""
    listed = set(corrects_ids)
    out: list[Alert] = []
    for a in alerts:
        if a.kind == "compliance" and a.status == "active" and a.alert_id in listed:
            a.status, a.resolved_at = "corrected", now
            a.corrected_by_transcript_id, a.corrected_text = t.transcript_id, t.text
            out.append(a)
    return out


def dismiss(a: Alert, now: int, reason: str = "false_alarm") -> bool:
    if a.status != "active":
        return False
    a.status, a.resolved_at, a.dismissed_reason = "dismissed", now, reason
    return True
