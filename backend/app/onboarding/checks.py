"""What a person must check before approving a read record (D-236, VERIFY_MODE arm).

- `full` (today): every extracted value is shown for checking, plus conflicts and missing values.
- `risk`: only items whose error would reach the live show, in four groups:
  1. product: sizes and market prices (every conflict, every price or size dropped or missing);
  2. governance: the law pack in force (none, or one built from documents), test-result qualifiers with their evidence;
  3. safety: cautions only the caution pass found (one reader saw them), and unreviewed translated cautions;
  4. offers: terms the money computation cannot rest on (no percent or amount, no stated rounding for a price change).
  Plus 1-2 audit samples of values nobody flagged. Prose (how to use, key facts) and full ingredient lists are not
  checked here; the live draft verifier covers them when they are used.
"""
from __future__ import annotations

import hashlib
from typing import Literal

from .record import OnboardingResult

Mode = Literal["full", "risk"]


def _item(group: str, label: str, reason: str) -> dict:
    return {"group": group, "label": label, "reason": reason}


def _product_items(r) -> list[dict]:
    out = []
    for c in r.conflicts:
        out.append(_item("product", c.field, "the documents disagree: " + " vs ".join(c.values)))
    for m in r.missing:
        if m.startswith("variants") or "price" in m or "size" in m:
            out.append(_item("product", m, "missing or not a clear number in its quote"))
    for v in r.variants:
        if not v.prices:
            out.append(_item("product", f"{v.name} prices", "no price for this size"))
    return out


def _corrected_items(result) -> list[dict]:
    """D-243: values the code read from the quote instead of the model's number."""
    return [_item("product", n.split(": ", 2)[1], n.split(": ", 2)[2]) for n in result.notes
            if n.startswith("corrected: ") and n.count(": ") >= 2]


def check_items(result: OnboardingResult, mode: Mode, *, law: str | None = None, caution_pass_only: list[str] = (),
                translations: dict | None = None) -> list[dict]:
    r = result.record
    if mode == "full":
        out = _product_items(r) + _corrected_items(result)
        for v in r.variants:
            out += [_item("product", f"{v.name} · {m.kind} price", "check the value") for m in v.prices]
        out += [_item("offers", o.title, "check the terms") for o in r.offers]
        for key, group in (("approved_claims", "governance"), ("not_approved_claims", "governance"),
                           ("cautions", "safety"), ("how_to_use", "other"), ("key_facts", "other")):
            out += [_item(group, x.text, "check the wording") for x in getattr(r, key)]
        out += [_item("governance", q.statement, "check the qualifier") for q in r.qualified_results]
        out += [_item("other", i.name, "check the ingredient") for i in r.ingredients]
        out += [_item("other", m, "missing") for m in r.missing if not m.startswith("variants")]
        if law is not None and law.startswith("no law"):
            out.append(_item("governance", r.category, "no law pack covers this category: no compliance checks live"))
        return out
    out = _product_items(r) + _corrected_items(result)
    if law is not None and law.startswith("no law"):
        out.append(_item("governance", r.category, "no law pack covers this category: no compliance checks live"))
    out += [_item("governance", q.statement, f"say it with “{q.qualifier}”") for q in r.qualified_results]
    out += [_item("safety", c, "found only by the caution pass") for c in caution_pass_only]
    for lang, t in (translations or {}).items():
        for key, group in (("approved_claims", "governance"), ("cautions", "safety"), ("avoid_saying", "governance")):
            for x in t.get(key, []):
                if not (isinstance(x, dict) and x.get("reviewed")):
                    out.append(_item(group, f"[{lang}] {x.get('text') or x.get('say')}", "unreviewed translation"))
    for o in r.offers:
        if ((o.kind == "percent_off" and not o.percent)
                or (o.kind in ("amount_off", "fixed_price", "spend_threshold_gift") and o.amount is None)):
            out.append(_item("offers", o.title, "the terms give no amount to compute with"))
        elif o.kind in ("percent_off", "amount_off") and not o.rounding:
            out.append(_item("offers", o.title, "no rounding rule stated: 2 decimals, half up"))
        elif o.kind == "other":
            out.append(_item("offers", o.title, "an offer kind the show cannot compute"))
    # audit sample: up to 2 values nobody flagged, chosen by the record (stable for the same record)
    pool = [f"{v.name} · {m.kind} price" for v in r.variants for m in v.prices] + [c.text for c in r.cautions]
    flagged = {x["label"] for x in out}
    pool = [p for p in pool if p not in flagged]
    seed = int(hashlib.sha1(f"{r.brand}|{r.product_name}".encode()).hexdigest(), 16)
    for k in range(min(2, len(pool))):
        out.append(_item("audit", pool[(seed + k * 7) % len(pool)], "audit sample: confirm it matches the document"))
    return out


def summary(items: list[dict]) -> dict:
    groups: dict[str, int] = {}
    for x in items:
        groups[x["group"]] = groups.get(x["group"], 0) + 1
    return {"to_check": len(items), "by_group": groups}
