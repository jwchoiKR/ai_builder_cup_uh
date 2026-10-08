"""Fact correction notes (DEV_SPEC §8.5)."""
from __future__ import annotations

from collections.abc import Callable, Collection, Sequence

from ..models.agent_io import FactClaim
from ..models.session import Alert, Transcript

PURCHASE_FIELDS = frozenset({"price", "set_price", "promo", "volume", "ingredient_amount"})


def active_fact_alerts(alerts: Sequence[Alert]) -> list[Alert]:
    return [a for a in alerts if a.kind == "fact" and a.status == "active"]


def subject_key(product_id: str, field: str | None, passage_id: str | None, span: str | None = None) -> tuple:
    """D-117 B3: one note per subject (the passage names the ingredient, test or offer), not per field:
    "squalane is 3%" must not clear a panthenol note. D-376: a note with no evidence passage is keyed by the host's
    words, so two evidence-less notes of one field (panthenol and niacinamide amounts) stay separate."""
    return product_id, field, passage_id if passage_id is not None else ("span", (span or "").strip().casefold())


def _price_kind(field: str | None) -> str | None:
    return "price" if field in ("price", "promo") else field


def apply_fact_check(
    claims: Sequence[FactClaim], alerts: Sequence[Alert], t: Transcript, new_id: Callable[[str], str], now: int,
    protected: Collection[str] = (), order: Callable[[str], int] | None = None,
) -> tuple[list[Alert], list[Alert]]:
    """Returns (created, re-shown). One active note per subject (product, field, passage). D-363: corrections are
    the model's, by handle (`correct_notes`). D-374: `protected` (a merged utterance's own fragments) no longer holds
    back a re-show; the argument stays for callers. D-376: `order` (a line's position in the show): a note keeps its
    latest showing; a verdict from an older line that arrives late never moves it back (ordering, not a drop: the
    note stays shown)."""
    active = {subject_key(a.product_id, a.field, a.passage_id, a.span): a for a in active_fact_alerts(alerts)}
    created: list[Alert] = []
    reshown: list[Alert] = []
    corrected: list[Alert] = []
    for c in claims:
        if c.verdict != "contradicted":
            continue
        key = subject_key(c.product_id, c.field, c.passage_id, c.span)
        a = active.get(key)
        if a is not None and order is not None and order(a.transcript_id) > order(t.transcript_id):
            continue  # D-376: already shown by a later line; that showing stays the note's latest
        if a is not None:
            a.stated_value, a.correct_value = c.stated_value, c.correct_value or a.correct_value
            a.passage_id, a.quote, a.span = c.passage_id, c.quote, c.span  # D-365: the words of this showing
            a.say = c.say  # D-396
            a.shown_at, a.host_hidden_at, a.transcript_id = now, None, t.transcript_id
            reshown.append(a)
        else:
            a = Alert(alert_id=new_id("fx_"), kind="fact", status="active", transcript_id=t.transcript_id,
                      product_id=c.product_id, field=c.field, stated_value=c.stated_value,
                      correct_value=c.correct_value, passage_id=c.passage_id, quote=c.quote, say=c.say,
                      span=c.span, created_at=now, shown_at=now, unverified=getattr(c, "_unverified", False),
                      votes=getattr(c, "_votes", None), evidence_ids=list(getattr(c, "_evidence", [])),
                      heard_check=getattr(c, "_check", False),
                      unverified_reason=getattr(c, "_unverified_reason", None))
            active[key] = a
            created.append(a)
    return created, reshown


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
