"""Fact correction notes (DEV_SPEC §8.5)."""
from __future__ import annotations

from collections.abc import Callable, Collection, Sequence

from ..models.agent_io import FactClaim
from ..models.session import Alert, Transcript
from .lexicon import Lexicon

PURCHASE_FIELDS = frozenset({"price", "set_price", "promo", "volume", "ingredient_amount"})


def active_fact_alerts(alerts: Sequence[Alert]) -> list[Alert]:
    return [a for a in alerts if a.kind == "fact" and a.status == "active"]


def subject_key(product_id: str, field: str | None, passage_id: str | None) -> tuple:
    """D-117 B3: one note per subject (the passage names the ingredient, test or offer), not per field:
    "squalane is 3%" must not clear a panthenol note."""
    return product_id, field, passage_id


def _corrected_note(c: FactClaim, notes: Sequence[Alert], lex: Lexicon) -> Alert | None:
    """The active note a supported claim corrects: the same passage, or without a passage the note
    whose right value the host now states (or the only note of that field when no number is said)."""
    same = [a for a in notes if (a.product_id, a.field) == (c.product_id, c.field)]
    if c.passage_id is not None:
        return next((a for a in same if a.passage_id == c.passage_id), None)
    said = lex.spoken_numbers(c.stated_value or "")
    if said:
        return next((a for a in same if lex.spoken_numbers(a.correct_value or "") == said), None)
    return same[0] if len(same) == 1 else None


def apply_fact_check(
    claims: Sequence[FactClaim], alerts: Sequence[Alert], t: Transcript, new_id: Callable[[str], str], now: int,
    protected: Collection[str] = (),
    *,
    lex: Lexicon,
) -> tuple[list[Alert], list[Alert], list[Alert]]:
    """Returns (created, re-shown, corrected). One active note per subject (product, field, passage).

    `protected`: transcript ids whose words are part of this (merged) utterance (D-088). Their
    active notes are the same claim heard again, so they are neither re-shown nor corrected."""
    active = {subject_key(a.product_id, a.field, a.passage_id): a for a in active_fact_alerts(alerts)}
    created: list[Alert] = []
    reshown: list[Alert] = []
    corrected: list[Alert] = []
    for c in claims:
        if c.verdict != "contradicted":
            continue
        key = subject_key(c.product_id, c.field, c.passage_id)
        a = active.get(key)
        if a is not None and a.transcript_id in protected:
            continue
        if a is not None:
            a.stated_value, a.correct_value = c.stated_value, c.correct_value or a.correct_value
            a.passage_id, a.quote = c.passage_id, c.quote
            a.shown_at, a.host_hidden_at, a.transcript_id = now, None, t.transcript_id
            reshown.append(a)
        else:
            a = Alert(alert_id=new_id("fx_"), kind="fact", status="active", transcript_id=t.transcript_id,
                      product_id=c.product_id, field=c.field, stated_value=c.stated_value,
                      correct_value=c.correct_value, passage_id=c.passage_id, quote=c.quote,
                      span=c.span, created_at=now, shown_at=now)
            active[key] = a
            created.append(a)
    fresh = {a.alert_id for a in created + reshown}
    for c in claims:
        if c.verdict != "supported":
            continue
        a = _corrected_note(c, [x for x in active.values() if x.status == "active"], lex)
        if a is not None and a.alert_id not in fresh and a.transcript_id not in protected:
            a.status, a.resolved_at = "corrected", now
            a.corrected_by_transcript_id, a.corrected_text = t.transcript_id, t.text
            corrected.append(a)
    return created, reshown, corrected
