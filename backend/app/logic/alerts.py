"""Compliance alert lifecycle (DEV_SPEC §8.4):
provisional -> active -> corrected | dismissed, or provisional -> cleared.

Functions change the given Alert objects in place and return the ones they created or changed;
the pipeline stores them and emits events.
"""
from __future__ import annotations

from collections.abc import Callable, Collection, Sequence

from ..models.agent_io import UtteranceJudgeOutput
from ..models.data import Rule
from ..models.session import Alert, Transcript
from .reflex import ReflexHit

NewId = Callable[[str], str]


def is_live(a: Alert) -> bool:
    return a.status in ("provisional", "active")


def high_alert_active(alerts: Sequence[Alert]) -> bool:
    return any(a.kind == "compliance" and a.status == "active" and a.severity == "HIGH" for a in alerts)


def provisional_from_reflex(
    hits: Sequence[ReflexHit], t: Transcript, product_id: str, alerts: Sequence[Alert], new_id: NewId, now: int,
) -> list[Alert]:
    """§8.2 step 2: one provisional alert per rule hit, unless an active alert already covers the rule."""
    covered = {a.rule_id for a in alerts if a.kind == "compliance" and a.status == "active"}
    out: list[Alert] = []
    for h in hits:
        if h.rule_id in covered or any(a.rule_id == h.rule_id for a in out):
            continue
        out.append(Alert(alert_id=new_id("al_"), kind="compliance", status="provisional", transcript_id=t.transcript_id,
                         product_id=product_id, rule_id=h.rule_id, severity=h.severity, span=h.phrase,
                         created_at=now, provisional_at=now))
    return out


def apply_judge_compliance(
    judge: UtteranceJudgeOutput, t: Transcript, product_id: str, provisional: Sequence[Alert],
    rules: dict[str, Rule], new_id: NewId, now: int, active_rule_ids: Collection[str] = (),
) -> tuple[list[Alert], list[Alert]]:
    """§8.4.1. Returns (changed, created).

    D-088 dedupe: `active_rule_ids` are rules already active from the fragments of a merged
    utterance. Their violations create no second alert; the active one stays until it is corrected
    or dismissed."""
    changed: list[Alert] = []
    created: list[Alert] = []
    pending = {a.rule_id: a for a in provisional if a.status == "provisional" and a.transcript_id == t.transcript_id}
    handled: set[str] = set()
    for v in judge.compliance.violations:
        if v.rule_id in handled:
            continue
        if v.is_negated or v.is_quoted:
            a = pending.get(v.rule_id)
            if a is not None and a.status == "provisional":
                a.status = "cleared"
                changed.append(a)
            continue
        handled.add(v.rule_id)
        if v.rule_id in active_rule_ids:
            continue  # already active: no duplicate (a provisional of this rule is cleared below)
        severity = getattr(v, "_severity", None) or rules[v.rule_id].severity  # D-300: the verifier's
        a = pending.get(v.rule_id)
        if a is not None:
            a.status, a.span, a.say_instead, a.severity, a.shown_at = "active", v.span, v.say_instead or None, severity, now
            a.product_id = getattr(v, "product_id", None) or a.product_id  # D-349: the product the judge picked
            a.unverified = a.unverified or getattr(v, "_unverified", False)
            a.unverified_reason = getattr(v, "_unverified_reason", None) or a.unverified_reason  # D-306
            a.votes = getattr(v, "_votes", None)  # D-302
            changed.append(a)
        else:
            created.append(Alert(alert_id=new_id("al_"), kind="compliance", status="active", transcript_id=t.transcript_id,
                                 product_id=getattr(v, "product_id", None) or product_id,  # D-349
                                 rule_id=v.rule_id, severity=severity, span=v.span,
                                 say_instead=v.say_instead or None, created_at=now, shown_at=now,
                                 unverified=getattr(v, "_unverified", False), votes=getattr(v, "_votes", None),
                                 unverified_reason=getattr(v, "_unverified_reason", None)))
    for a in pending.values():
        if a.status == "provisional":  # not confirmed by the judge
            a.status = "cleared"
            changed.append(a)
    return changed, created


def apply_judge_failure(
    provisional: Sequence[Alert], hits: Sequence[ReflexHit], say_instead: str, now: int,
) -> list[Alert]:
    """§8.4.3: fail toward warning. A HIGH reflex hit that is neither negated nor quoted becomes an
    unverified active alert; everything else is cleared."""
    out: list[Alert] = []
    for a in provisional:
        if a.status != "provisional":
            continue
        rule_hits = [h for h in hits if h.rule_id == a.rule_id]
        if a.severity == "HIGH" and any(not h.negated and not h.quoted for h in rule_hits):
            a.status, a.shown_at, a.unverified, a.say_instead = "active", now, True, say_instead
        else:
            a.status = "cleared"
        out.append(a)
    return out


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
    if a.status not in ("active", "provisional"):
        return False
    a.status, a.resolved_at, a.dismissed_reason = "dismissed", now, reason
    return True
