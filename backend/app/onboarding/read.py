"""Onboarding steps 2-3 (P0): Gemini reads every file whole and returns a ProductRecord with evidence
(EXTRACT_METHOD `gemini_whole`); code then normalises currencies, units and identities and drops any value that came
without evidence."""
from __future__ import annotations

import re
import time
from decimal import Decimal
from pathlib import Path

from ..providers.llm import LLMClient, LLMRequest
from .files import ModelPart
from .record import Money, OnboardingResult, ProductRecord

PROMPT = (Path(__file__).with_name("read_prompt.md")).read_text(encoding="utf-8")
PROMPT_VERSION = "onboarding_read-1"
READ_MODEL = "gemini-3.8-flash"  # P0 answers 10/5: the extractor; offline, so more thinking than the live path
READ_THINKING = "HIGH"
READ_DEADLINE_MS = 600_000

_CURRENCY = {"s$": "SGD", "sgd": "SGD", "rm": "MYR", "myr": "MYR", "us$": "USD", "usd": "USD", "$": "USD",
             "₩": "KRW", "krw": "KRW", "€": "EUR", "eur": "EUR", "£": "GBP", "gbp": "GBP", "¥": "JPY", "jpy": "JPY"}
_UNIT = {"ml": "ml", "mls": "ml", "milliliter": "ml", "milliliters": "ml", "millilitre": "ml", "millilitres": "ml",
         "l": "l", "g": "g", "gram": "g", "grams": "g", "kg": "kg", "mg": "mg", "oz": "oz", "fl oz": "fl oz",
         "pcs": "pcs", "pc": "pcs", "pieces": "pcs", "tablets": "tablets", "capsules": "capsules", "%": "%"}


def _money_ok(m: Money, notes: list[str], where: str) -> bool:
    code = _CURRENCY.get(m.currency.strip().lower(), m.currency.strip().upper())
    if not re.fullmatch(r"[A-Z]{3}", code):
        notes.append(f"{where}: dropped a price with an unknown currency {m.currency!r}")
        return False
    m.currency = code
    if m.market:
        m.market = m.market.strip().upper()
    return True


# D-225: languages that write a decimal comma ("0,5 %"); elsewhere a comma separates thousands ("5,000 mg")
DECIMAL_COMMA = frozenset({"de", "fr", "es", "it", "pt", "nl", "id", "ru", "tr", "vi", "pl", "cs", "sv", "da", "fi",
                           "nb", "no", "ro", "hu", "el", "uk", "bg", "hr", "sk", "sl", "lt", "lv", "et"})
_NUM = re.compile(r"\d[\d.,]*\d|\d")


def _plain(raw: str, comma_decimal: bool) -> str | None:
    if not comma_decimal and "," in raw and not re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", raw):
        return None  # "0,50" outside a decimal-comma language is ambiguous: never guessed
    n = raw.replace(".", "").replace(",", ".") if comma_decimal else raw.replace(",", "")
    if n.count(".") > 1:
        return None
    return n.rstrip("0").rstrip(".") if "." in n else n.lstrip("0") or "0"


def _decimal(v: str | None, comma_decimal: bool = False) -> str | None:
    """A number as written ("30", "5,000 mg", "0,2" in a decimal-comma language) as a plain decimal string
    ("30", "5000", "0.2"), or None."""
    if v is None:
        return None
    m = _NUM.search(v)
    return _plain(m.group(), comma_decimal) if m else None


def _numbers_in(evidence, comma_decimal: bool) -> set[str]:
    """Every number in the evidence quotes, normalised like the extracted values."""
    return {n for e in evidence for m in _NUM.finditer(e.quote) if (n := _plain(m.group(), comma_decimal))}


def _unit(u: str | None) -> str | None:
    if u is None:
        return None
    return _UNIT.get(u.strip().lower(), u.strip().lower())


def normalise(rec: ProductRecord) -> tuple[ProductRecord, list[str]]:
    """Step 3, in code: ISO currencies, unit names, unique variant ids, and no value without evidence.
    D-225: every number must appear as written in its own evidence quote; one that does not is dropped and listed in
    `missing` (0 wrong numbers beats a complete record)."""
    notes: list[str] = []
    r = rec.model_copy(deep=True)
    comma = r.language.split("-")[0].lower() in DECIMAL_COMMA

    def checked(written: str | None, evidence, where: str) -> str | None:
        if written is None or not written.strip():
            return None
        value = _decimal(written, comma)
        if value is not None and value in _numbers_in(evidence, comma):
            return value
        notes.append(f"{where}: {written!r} is not a clear number in its evidence quote; dropped")
        r.missing.append(where)
        return None
    seen: set[str] = set()
    kept = []
    for i, v in enumerate(r.variants):
        if not v.evidence:
            notes.append(f"variants[{i}]: dropped, no evidence")
            continue
        vid = v.variant_id.strip() or f"v{i + 1}"
        while vid in seen:
            vid += "_2"
        v.variant_id, v.size_unit = vid, _unit(v.size_unit)
        v.size_value = checked(v.size_value, v.evidence, f"variants[{vid}].size_value")
        if v.market:
            v.market = v.market.strip().upper()
        v.prices = [m for m in v.prices if m.evidence and _money_ok(m, notes, f"variants[{i}].prices")
                    and checked(str(Decimal(m.minor) / 100), m.evidence,
                                f"variants[{vid}].prices.{m.kind}.{m.currency}") is not None]
        seen.add(vid)
        kept.append(v)
    r.variants = kept
    for o in r.offers:
        if o.amount is not None and not (o.amount.evidence and _money_ok(o.amount, notes, f"offer {o.offer_id}")):
            o.amount = None
        o.variant_ids = [x for x in o.variant_ids if x in seen]
    r.offers = [o for o in r.offers if o.evidence]
    for ing in r.ingredients:
        ing.amount_unit = _unit(ing.amount_unit)
        ing.amount_value = checked(ing.amount_value, ing.evidence, f"ingredients[{ing.name}].amount")
    for o in r.offers:
        o.percent = checked(o.percent, o.evidence, f"offers[{o.offer_id}].percent")
    for name in ("approved_claims", "not_approved_claims", "cautions", "how_to_use", "key_facts", "ingredients",
                 "avoid_saying", "qualified_results"):
        items = getattr(r, name)
        good = [x for x in items if x.evidence]
        if len(good) < len(items):
            notes.append(f"{name}: dropped {len(items) - len(good)} without evidence")
        setattr(r, name, good)
    if r.generic_word:
        r.generic_word = r.generic_word.strip().lower()
        r.short_names = [s for s in r.short_names if s.strip().lower() != r.generic_word]
    r.category = r.category.strip().lower().replace(" ", "_")
    return r, notes


async def read_product(llm: LLMClient, parts: list[ModelPart], *, hints: str = "", session_id: str | None = None,
                       model: str = READ_MODEL, thinking: str = READ_THINKING) -> OnboardingResult:
    t0 = time.perf_counter()
    payload: list[tuple[bytes, str]] = []
    for p in parts:
        payload.append((f"FILE {p.name}".encode(), "text/plain"))
        payload.append((p.data, p.mime))
    user = (f'<data name="HINTS">{hints}</data>\n' if hints else "") + "Return the product record JSON."
    res = await llm.call(LLMRequest(
        agent="onboarding_read", model=model, thinking_level=thinking, prompt_version=PROMPT_VERSION,
        system_instruction=PROMPT, user_message=user, output_model=ProductRecord, deadline_ms=READ_DEADLINE_MS,
        session_id=session_id, mock_primary_text="|".join(p.name for p in parts), parts=tuple(payload),
        preview=", ".join(p.name for p in parts),
    ))
    if res.status != "ok" or res.output is None:
        raise RuntimeError(f"onboarding read {res.status}: {res.error}")
    record, notes = normalise(res.output)
    return OnboardingResult(record=record, method="gemini_whole", models={"read": f"{model} ({thinking})"},
                            seconds=round(time.perf_counter() - t0, 1), notes=notes)
