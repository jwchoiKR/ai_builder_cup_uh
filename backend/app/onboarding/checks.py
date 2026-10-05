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
import re
from typing import Literal

from pydantic import BaseModel

from .record import OnboardingResult

Mode = Literal["full", "risk", "lean"]


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


def _category_items(result) -> list[dict]:
    """D-256: a category the code mapped (to the list, or to a covered type) is checked with the law pack it selects."""
    return [_item("governance", n.split(": ", 1)[1], "the category selects the law pack: confirm it")
            for n in result.notes if n.startswith("category: ")]


def _corrected_items(result) -> list[dict]:
    """D-243: values the code read from the quote instead of the model's number."""
    return [_item("product", n.split(": ", 2)[1], n.split(": ", 2)[2]) for n in result.notes
            if n.startswith("corrected: ") and n.count(": ") >= 2]


def _dropped_items(result) -> list[dict]:
    """D-245 R5: every value the evidence check dropped (ingredient amounts, offer terms, sizes, prices), so a person
    sees it before approval instead of a note nobody reads."""
    out = []
    for n in result.notes:
        if n.endswith("is not a clear number in its evidence quote; dropped") and ": " in n:
            where, why = n.split(": ", 1)
            out.append(_item("offers" if where.startswith("offers") else "product", where, why))
    return out


def _coverage_items(result) -> list[dict]:
    """D-249: what the files state and the record lacks, with where it is; a quote code could not find in the file's
    text is said so."""
    out = []
    for x in result.uncovered:
        where = f"{x['file']} ({x['locator']}): “{x['quote']}”" if x.get("file") else ""
        why = "in the files, not in the record" + (f" (record has {x['record_has']})" if x.get("record_has") else "")
        if x.get("in_file_text") is False:
            why += "; this quote was not found in the file's text"
        out.append(_item("coverage", x["text"], f"{why}: {where}" if where else why))
    return out


def check_items(result: OnboardingResult, mode: Mode, *, law: str | None = None, caution_pass_only: list[str] = (),
                translations: dict | None = None) -> list[dict]:
    r = result.record
    if mode == "lean":
        mode = "risk"  # lean starts from the risk items (lean_items)
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
        return out + _category_items(result) + _coverage_items(result)
    out = _product_items(r) + _corrected_items(result)
    shown = {x["label"] for x in out}
    out += [x for x in _dropped_items(result) if x["label"] not in shown]
    out += _coverage_items(result)
    if law is not None and law.startswith("no law"):
        out.append(_item("governance", r.category, "no law pack covers this category: no compliance checks live"))
    out += _category_items(result)
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


# ---- D-254 lean: the risk items, at most LEAN_MAX to check ---------------------------------------------------------
LEAN_MAX = 10
_GROUP_ORDER = {"product": 0, "governance": 1, "offers": 2, "safety": 3, "coverage": 4, "audit": 5}
_LIVE_KIND = {"condition": 0, "test_result": 0, "certification": 1, "caution": 1, "claim": 2, "number": 3}


def _verified(quote: str, file: str, file_texts: dict[str, str]) -> bool:
    from ..logic.verify import quote_in_file

    text = file_texts.get(file)
    return bool(text and quote and quote_in_file(quote, text))


def _flat(t: str) -> str:
    from ..logic.verify import _flat as flat

    return flat(t or "")


def _coverage_lean(result) -> list[dict]:
    """Coverage items without duplicates and without what the record's own evidence already quotes, most live
    impact first (conditions and test results, then certifications and cautions, claims, numbers; an unfound quote
    last)."""
    held = [_flat(e.quote) for e in _all_evidence(result.record)]
    seen, out = [], []
    for x in result.uncovered:
        q = _flat(x.get("quote", ""))
        if not q:
            continue
        if not x.get("record_has") and any(q in h or (len(h) > 12 and h in q) for h in held):
            continue  # the record holds this source line already (a different value there stays a check)
        if any(q == s or q in s or s in q for s in seen):
            continue  # the same statement twice
        seen.append(q)
        out.append(x)
    out.sort(key=lambda x: (_LIVE_KIND.get(x.get("kind"), 4) + (x.get("in_file_text") is False)))
    return out


def _all_evidence(record):
    out = []

    def walk(o):
        if isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, BaseModel):
            if {"file", "locator", "quote"} <= set(type(o).model_fields):
                out.append(o)
                return
            for k in type(o).model_fields:
                walk(getattr(o, k))

    walk(record)
    return out


def _family(items: list[dict]) -> list[dict]:
    """Product items of the same field across variants become one: "variants[*].prices.list.SGD (12 variants)", or
    "12 variants: no price for this size" when only the variant name differs."""
    fam: dict[tuple, list[dict]] = {}
    for x in items:
        key = ((re.sub(r"\[[^\]]*\]", "[*]", x["label"]), x["reason"].split(":")[0]) if "[" in x["label"]
               else ("", x["reason"]))
        fam.setdefault(key, []).append(x)
    out = []
    for (label, reason), xs in fam.items():
        if len(xs) < 3:
            out += xs
            continue
        names = [re.findall(r"\[([^\]]*)\]", y["label"])[0] if label else y["label"] for y in xs]
        listed = ", ".join(names[:6]) + (", ..." if len(names) > 6 else "")
        out.append(_item(xs[0]["group"], f"{label} ({len(xs)} variants)" if label else f"{len(xs)} variants: {reason}",
                         f"{xs[0]['reason']} (same for {listed})" if label else f"{reason}: {listed}"))
    return out


def lean_items(result: OnboardingResult, risk: list[dict], file_texts: dict[str, str]) -> tuple[list, list, list]:
    """D-254 (sealed onboarding: 7-41 items per product read as a manual step): (to check, folded, accepted).
    A caution only the caution pass found is accepted when its quote is in the file text; coverage items lose
    duplicates and lines the record already quotes; product items of one field across variants become one; one audit
    sample. Then the first LEAN_MAX by group (product, governance, offers, safety, coverage, audit) are to check."""
    r = result.record
    auto, keep = [], []
    by_text = {c.text: c for c in r.cautions}
    for x in risk:
        if x["group"] == "safety" and x["reason"] == "found only by the caution pass":
            c = by_text.get(x["label"])
            ev = next((e for e in (c.evidence if c else []) if _verified(e.quote, e.file, file_texts)), None)
            if ev is not None:
                auto.append({"label": x["label"], "source": f"{ev.file} ({ev.locator}): “{ev.quote}”"})
                continue
        if x["group"] == "coverage":
            continue  # rebuilt below
        keep.append(x)
    keep += _coverage_items(result.model_copy(update={"uncovered": _coverage_lean(result)}))
    audits = [x for x in keep if x["group"] == "audit"]
    keep = [x for x in keep if x["group"] != "audit"] + audits[:1]
    keep = _family([x for x in keep if x["group"] == "product"]) + [x for x in keep if x["group"] != "product"]
    keep.sort(key=lambda x: _GROUP_ORDER.get(x["group"], 9))  # stable: the order inside a group stays
    return keep[:LEAN_MAX], keep[LEAN_MAX:], auto


def summary(items: list[dict]) -> dict:
    groups: dict[str, int] = {}
    for x in items:
        groups[x["group"]] = groups.get(x["group"], 0) + 1
    return {"to_check": len(items), "by_group": groups}
