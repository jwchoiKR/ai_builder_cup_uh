"""Placeholder builders for the prompt templates (DEV_SPEC §7.1, one function per placeholder).

Builders return plain Python values; `providers/prompts.py` renders `*_json` placeholders as
compact JSON and the others as text. The prompt loader fails at startup if a template uses a
placeholder that has no builder here.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..logic.catalog import Catalog
from ..models.data import Passage, Promo, PrompterPoint
from ..models.session import Alert, HostCue, QuestionGroup, SwitchState, Transcript

# ---- products and run-sheet ------------------------------------------------------------------


def current_product_json(catalog: Catalog, product_id: str) -> dict:
    p = catalog.get_product(product_id)
    return {"product_id": p.product_id, "name": p.name, "short_name": p.short_name}


def product_compact_json(catalog: Catalog, product_id: str | None) -> dict | None:
    if product_id is None:  # product_scope=multi (§7.6)
        return None
    p = catalog.get_product(product_id)
    return {
        "product_id": p.product_id,
        "name": p.name,
        "code": p.code,
        "volume": p.volume,
        "list_price": catalog.money(p.list_price),
        "live_price": catalog.money(p.live_price),
    }


current_product_compact_json = product_compact_json


def products_compact_json(catalog: Catalog) -> list[dict]:
    return [{"product_id": p.product_id, "name": p.name, "aliases": p.aliases} for p in catalog.products]


def run_sheet_compact_json(catalog: Catalog, on_air_product_id: str | None) -> list[dict]:
    on_air = catalog.order.index(on_air_product_id) if on_air_product_id else -1
    out = []
    for i, pid in enumerate(catalog.order):
        if i < on_air:
            status = "done"
        elif i == on_air:
            status = "on_air"
        elif i == on_air + 1:
            status = "next"
        else:
            status = "later"
        out.append({"order": catalog.runsheet_item(pid).order, "product_id": pid,
                    "name": catalog.get_product(pid).name, "status": status})
    return out


def approved_claims_of_current_product_json(catalog: Catalog, product_id: str) -> list[str]:
    return catalog.approved_claims(product_id)


def prompter_points_json(
    catalog: Catalog,
    on_air_product_id: str,
    points_by_product: dict[str, list[PrompterPoint]] | None = None,
) -> list[dict]:
    """Points of the on-air and the next product. `points_by_product` carries Setup overrides."""
    out = []
    for pid in (on_air_product_id, catalog.next_product(on_air_product_id)):
        if pid is None:
            continue
        points = (points_by_product or {}).get(pid) or catalog.get_product(pid).prompter_points
        out.extend({"point_id": pt.point_id, "product_id": pid, "text": pt.text} for pt in points)
    return out


def set_offers_json(catalog: Catalog, promo: Promo | None) -> list[dict]:
    price_promo = promo if promo is not None and promo.changes_prices else None
    return [
        {
            "set_id": s.set_id,
            "name": s.name,
            "product_ids": s.product_ids,
            "live_price": catalog.money(s.live_price),
            "promo_price": catalog.price_display(s.set_id, price_promo)
            if price_promo is not None and s.set_id in price_promo.promo_prices
            else None,
        }
        for s in catalog.set_offers
    ]


def active_promo_json_or_null(catalog: Catalog, promo: Promo | None) -> dict | None:
    if promo is None or not promo.changes_prices:
        return None
    return {
        "promo_id": promo.promo_id,
        "title": promo.title,
        "promo_prices": dict(promo.promo_prices),
        "promo_prices_display": {k: catalog.money(v) for k, v in promo.promo_prices.items()},
    }


def switch_context_json(catalog: Catalog, switch: SwitchState, on_air_product_id: str | None) -> dict:
    nxt = switch.target_product_id or catalog.next_product(on_air_product_id)
    return {
        "in_progress": switch.status in ("counting", "pending"),
        "next_product": {"product_id": nxt, "name": catalog.get_product(nxt).name} if nxt else None,
    }


# ---- policy ----------------------------------------------------------------------------------


def rules_compact_json(catalog: Catalog) -> list[dict]:
    return [
        {"rule_id": r.rule_id, "title": r.title, "description": r.description,
         "severity": r.severity, "unacceptable_examples": r.unacceptable_examples}
        for r in catalog.pack.rules.rules
    ]


def intent_names_json(catalog: Catalog) -> list[str]:
    return [i.intent for i in catalog.pack.intents.intents]


def condition_slots_json(slots: dict[str, Any]) -> dict[str, Any]:
    """Triage: the `condition_slots` object of intents.json. Composer: the group's slots."""
    return dict(slots)


# ---- live session state ----------------------------------------------------------------------


def active_alerts_json(alerts: Sequence[Alert]) -> list[dict]:
    live = [a for a in alerts if a.kind == "compliance" and a.status in ("active", "provisional")]
    live.sort(key=lambda a: a.created_at, reverse=True)
    return [{"alert_id": a.alert_id, "span": a.span, "rule_id": a.rule_id} for a in live[:3]]


def open_questions_json(items: Sequence[tuple[QuestionGroup, str | None]], limit: int) -> list[dict]:
    """`items` are already selected and ordered by the caller (§7.3): (group, verified answer text)."""
    return [
        {"group_id": g.group_id, "product_id": g.product_id,
         "canonical_question": g.canonical_question, "suggested_answer": answer}
        for g, answer in items[:limit]
    ]


def open_groups_json(groups: Sequence[QuestionGroup], limit: int) -> list[dict]:
    live = [g for g in groups if g.status not in ("closed", "rejected")]
    live.sort(key=lambda g: g.last_at, reverse=True)
    return [
        {"group_id": g.group_id, "product_id": g.product_id, "intent": g.intent,
         "condition_slots": g.condition_slots, "canonical_question": g.canonical_question}
        for g in live[:limit]
    ]


def host_cues_json(cue: HostCue | None) -> list[dict]:
    return [{"cue_id": cue.cue_id, "text": cue.text}] if cue is not None and cue.status == "active" else []


def last_two_final_transcripts_json(previous: Sequence[Transcript]) -> list[str]:
    finals = [t for t in previous if t.is_final]
    return [t.text for t in finals[-2:]]


def passages_json(passages: Sequence[Passage]) -> list[dict]:
    return [{"passage_id": p.passage_id, "product_id": p.product_id, "section": p.section, "text": p.text}
            for p in passages]


def summary_stats_json(stats: dict[str, Any]) -> dict[str, Any]:
    return stats


# ---- plain-text placeholders -----------------------------------------------------------------


def utterance_text(text: str) -> str:
    return text


def comment_text(text: str, max_chars: int) -> str:
    return text[:max_chars]  # §5 MAX_COMMENT_CHARS: truncated for analysis, stored in full


def canonical_question(text: str) -> str:
    return text


def product_id(pid: str) -> str:
    return pid


def product_id_at_comment_time_minus_grace(pid: str | None) -> str | None:
    return pid  # rendered as "null" before the broadcast starts


def full_document_text_with_section_headings(text: str) -> str:
    return text


BUILDERS = {
    f.__name__: f
    for f in (
        current_product_json, product_compact_json, products_compact_json,
        run_sheet_compact_json, approved_claims_of_current_product_json, prompter_points_json,
        set_offers_json, active_promo_json_or_null, switch_context_json, rules_compact_json,
        intent_names_json, condition_slots_json, active_alerts_json, open_questions_json,
        open_groups_json, host_cues_json, last_two_final_transcripts_json, passages_json,
        summary_stats_json, utterance_text, comment_text, canonical_question, product_id,
        product_id_at_comment_time_minus_grace, full_document_text_with_section_headings,
    )
}
BUILDERS["current_product_compact_json"] = current_product_compact_json
