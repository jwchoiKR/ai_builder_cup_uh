"""Placeholder builders for the prompt templates (DEV_SPEC §7.1, one function per placeholder).

Builders return plain Python values; `providers/prompts.py` renders `*_json` placeholders as
compact JSON and the others as text. The prompt loader fails at startup if a template uses a
placeholder that has no builder here.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from ..logic.catalog import Catalog
from ..models.data import Passage, Promo, PrompterPoint
from ..models.session import Alert, HostCue, QuestionGroup, SwitchState, Transcript

# ---- products and run-sheet ------------------------------------------------------------------


def current_product_json(catalog: Catalog, product_id: str) -> dict:
    p = catalog.get_product(product_id)
    out = {"product_id": p.product_id, "name": p.name, "short_name": p.short_name}
    if p.target_group:  # D-256: who the product is for (a vulnerable group's rules apply to promises to them)
        out["target_group"] = p.target_group
    return out


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
    } | ({"variants": [{"variant": v.label, "list_price": catalog.money(v.list_price),
                        "live_price": catalog.money(v.live_price)} for v in p.variants],
          "note": "volume and prices above are the first variant's"} if p.variants else {})  # D-281


current_product_compact_json = product_compact_json


def products_compact_json(catalog: Catalog) -> list[dict]:
    return [{"product_id": p.product_id, "name": p.name, "aliases": p.aliases} for p in catalog.products]


def run_sheet_compact_json(catalog: Catalog, on_air_product_id: str | None,
                           types: dict[str, str] | None = None) -> list[dict]:
    """The show's products in order with their status. D-351 (`types` given, SWITCH_MODE=immediate): also each
    product's short name and type word, so the context judge can tell when the host names the next product."""
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
                    "name": catalog.get_product(pid).name, "status": status}
                   | ({"short_name": catalog.get_product(pid).short_name, "type": types.get(pid) or None}
                      if types is not None else {}))
    return out


def approved_claims_of_current_product_json(catalog: Catalog, product_id: str) -> list[str]:
    return catalog.approved_claims(product_id)


def cautions_json(catalog: Catalog, product_id: str | None) -> list[str]:
    """D-212: every caution of the product's sheet (of every product for a multi question), for the draft verifier,
    independent of the passages the composer chose."""
    return [p.text for p in catalog.pack.passages
            if p.section == "Cautions" and (product_id is None or p.product_id == product_id)]


def viewer_comments_json(texts: Sequence[str], max_chars: int = 300) -> list[str]:
    """D-212: the askers' own comments (at most 5), not only the canonical question."""
    return [t[:max_chars] for t in list(texts)[:5]]


def asked_questions_json(rows: Sequence[dict], max_chars: int = 200) -> list[dict]:
    """CommentInsights: every question of the broadcast as {key, question, comments (at most 2), product}."""
    return [{"key": r["key"], "question": r["question"][:max_chars],
             "comments": [c[:max_chars] for c in r.get("comments", [])[:2]], "product": r.get("product")} for r in rows]


def avoid_saying_json(catalog: Catalog, product_id: str | None) -> list[dict]:
    """D-190: the sheet's "avoid saying -> say instead" pairs (approved wording, verbatim) for the composer."""
    if product_id is None:
        return []
    return [{"say_not": a.say_not, "say": a.say} for a in catalog.get_product(product_id).avoid_saying]


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
        # D-148: the terms the host may say, checkable like any fact
        "discount_pct_off_live_price": promo.discount_pct_off_live_price,
        "duration_min": round(promo.duration_sec / 60),
    }


def active_offers_json(catalog: Catalog, offers: Sequence[Promo]) -> list[dict]:
    """D-149: running offers that change no price (a gift over a spend), with their checkable terms."""
    return [{"promo_id": o.promo_id, "title": o.title,
             "min_spend": catalog.money(o.min_spend) if o.min_spend is not None else None,
             "duration_min": round(o.duration_sec / 60)}
            for o in offers if not o.changes_prices]


def switch_context_json(catalog: Catalog, switch: SwitchState, on_air_product_id: str | None) -> dict:
    nxt = catalog.next_product(on_air_product_id)
    prev = switch.previous_product_id
    return {
        "next_product": {"product_id": nxt, "name": catalog.get_product(nxt).name} if nxt else None,
    } | ({"previous_product": {  # D-349: only inside the few seconds after a switch
        "product_id": prev, "name": catalog.get_product(prev).name,
        "note": "was on air until a few seconds ago; the current product is now on air"}} if prev else {})


# ---- policy ----------------------------------------------------------------------------------


def rules_compact_json(catalog: Catalog, product_ids=None) -> list[dict]:
    """D-279: with `product_ids`, only those products' rules (a multi-release show)."""
    rules = catalog.pack.rules.rules if product_ids is None else catalog.rules_for(product_ids)
    return [
        {"rule_id": r.rule_id, "title": r.title, "description": r.description,
         "severity": r.severity, "unacceptable_examples": r.unacceptable_examples}
        for r in rules
    ]


def intent_names_json(catalog: Catalog) -> list[str]:
    return [i.intent for i in catalog.pack.intents.intents]


def condition_slots_json(slots: dict[str, Any]) -> dict[str, Any]:
    """Triage: the `condition_slots` object of intents.json. Composer: the group's slots."""
    return dict(slots)


# ---- live session state ----------------------------------------------------------------------


def active_alerts_json(alerts: Sequence[Alert]) -> list[dict]:
    """D-395 (was D-355's 3 newest): every active compliance alert, newest first, so a correction can
    reach each one (since D-387 one claim said four times is four alerts). Each carries its product, so the model can
    tell an earlier product's similar claim from the on-air one; D-098: say_instead is what the host was shown."""
    live = [a for a in alerts if a.kind == "compliance" and a.status == "active"]  # D-410: no provisional state
    live.sort(key=lambda a: a.created_at, reverse=True)
    return [{"alert_id": a.alert_id, "product_id": a.product_id, "span": a.span, "rule_id": a.rule_id,
             "say_instead": a.say_instead} for a in live]


def open_questions_json(items: Sequence[tuple[QuestionGroup, str | None]], limit: int,
                        on_screen: str | None = None) -> list[dict]:
    """`items` are already selected and ordered by the caller (§7.3): (group, verified answer text).
    D-112: the question whose card the host sees now is marked `on_screen` (a tie-breaker only)."""
    return [
        {"group_id": g.group_id, "product_id": g.product_id,
         "canonical_question": g.canonical_question, "suggested_answer": answer}
        | ({"on_screen": True} if g.group_id == on_screen else {})
        for g, answer in items[:limit]
    ]


def host_cues_json(cue: HostCue | None) -> list[dict]:
    return [{"cue_id": cue.cue_id, "text": cue.text}] if cue is not None and cue.status == "active" else []


def last_two_final_transcripts_json(previous: Sequence[Transcript]) -> list[str]:
    finals = [t for t in previous if t.is_final]
    return [t.text for t in finals[-2:]]


def passages_json(passages: Sequence[Passage]) -> list[dict]:
    return [{"passage_id": p.passage_id, "product_id": p.product_id, "section": p.section, "text": p.text}
            for p in passages]


def all_passages(catalog: Catalog, product_id: str | None = None) -> list[Passage]:
    """D-191 arms D and E: the whole product sheet (every passage) of one product, or of every product."""
    return [p for p in catalog.pack.passages if product_id is None or p.product_id == product_id]


def data_block(name: str, value: Any) -> str:
    """D-191: a data block a design arm adds after the rendered user message."""
    return "\n" + f'<data name="{name}">{json.dumps(value, ensure_ascii=False)}</data>'


def summary_stats_json(stats: dict[str, Any]) -> dict[str, Any]:
    return stats


# ---- plain-text placeholders -----------------------------------------------------------------


def utterance_text(text: str) -> str:
    return text


def comment_text(text: str, max_chars: int) -> str:
    return text[:max_chars]  # §5 MAX_COMMENT_CHARS: truncated for analysis, stored in full


def comments_json(items: Sequence[tuple[str, str | None, str | None]], max_chars: int) -> list[dict]:
    """Micro-batch triage: (text, context product, recent host line) per comment, indexed in order."""
    return [{"i": i, "context_product_id": pid, "recent_host_line": line, "comment": comment_text(text, max_chars)}
            for i, (text, pid, line) in enumerate(items)]


def recent_host_line_json_or_null(line: str | None) -> str | None:
    return line  # D-157: the host's last final before a short comment, else null


def canonical_question(text: str) -> str:
    return text


def merge_group_json(question: str, comments: Sequence[str], conditions: dict) -> dict:
    return {"question": question, "comments": [c[:300] for c in list(comments)[:3]], "conditions": conditions}


def merge_new_json(question: str, comment: str, conditions: dict) -> dict:
    return {"question": question, "comment": comment[:300], "conditions": conditions}


def target_language_json(language: str) -> str:
    return language


def draft_answer_json(text: str) -> str:
    return text  # JSON-encoded on render: the draft is untrusted model output


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
        run_sheet_compact_json, approved_claims_of_current_product_json, avoid_saying_json, prompter_points_json,
        cautions_json, viewer_comments_json, asked_questions_json,
        set_offers_json, active_promo_json_or_null, active_offers_json, switch_context_json, rules_compact_json,
        intent_names_json, condition_slots_json, active_alerts_json, open_questions_json,
        host_cues_json, last_two_final_transcripts_json, passages_json,
        summary_stats_json, draft_answer_json, utterance_text, comment_text, comments_json, canonical_question, product_id,
        product_id_at_comment_time_minus_grace, full_document_text_with_section_headings, recent_host_line_json_or_null,
        target_language_json, merge_group_json, merge_new_json,
    )
}
BUILDERS["current_product_compact_json"] = current_product_compact_json
