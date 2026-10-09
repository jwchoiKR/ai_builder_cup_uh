"""Fact correction notes (DEV_SPEC §8.5)."""
from __future__ import annotations

from collections.abc import Callable, Collection, Sequence

from ..models.agent_io import FactClaim
from ..models.session import Alert, Transcript

PURCHASE_FIELDS = frozenset({"price", "set_price", "promo", "volume", "ingredient_amount"})


def active_fact_alerts(alerts: Sequence[Alert]) -> list[Alert]:
    return [a for a in alerts if a.kind == "fact" and a.status == "active"]


def _price_kind(field: str | None) -> str | None:
    return "price" if field in ("price", "promo") else field


def apply_fact_check(claims: Sequence[FactClaim], t: Transcript, new_id: Callable[[str], str],
                     now: int) -> list[Alert]:
    """D-398 (user): each contradicted claim is its own fact note, with its own handle; no subject key, no re-show,
    no carried-over correction. A merged line's verdict replaces its chain's notes (pipelines/utterances.py)."""
    created: list[Alert] = []
    for c in claims:
        if c.verdict != "contradicted":
            continue
        created.append(Alert(alert_id=new_id("fx_"), kind="fact", status="active", transcript_id=t.transcript_id,
                             product_id=c.product_id, field=c.field, stated_value=c.stated_value,
                             correct_value=c.correct_value, passage_id=c.passage_id, quote=c.quote, say=c.say,
                             span=c.span, created_at=now, shown_at=now,
                             evidence_ids=list(getattr(c, "_evidence", []))))
    return created


def correct_notes(note_ids, alerts: Sequence[Alert], t: Transcript, now: int,
                  fresh: Collection[str] = ()) -> list[Alert]:
    """D-363: the active fact notes the model marked fixed by this line (by handle, mapped to ids). D-374: as given,
    also a note this same line raised or re-showed (`fresh` stays for callers)."""
    corrected = []
    for a in alerts:
        if a.kind == "fact" and a.status == "active" and a.alert_id in note_ids:
            a.status, a.resolved_at = "corrected", now
            a.corrected_by_transcript_id, a.corrected_text = t.transcript_id, t.text
            corrected.append(a)
    return corrected
