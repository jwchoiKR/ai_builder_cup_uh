"""The BriefAgent on an approved release (D-265): an STT glossary and prompter points for an onboarded product.

Before this, a release's show had the approved claims as prompter points (the first one required) and a glossary of
only its brand, product and four ingredient names, so new names had few phrase hints for speech-to-text. At approval
the BriefAgent now reads the release's record and its source files' readable text (any language) and writes
briefs/<release_id>.json, write-once like the release. A session from the release uses its glossary as phrase hints
and its points on the prompter; without a brief (a failure, or a release made before) nothing changes.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

from ..agents.brief import BriefAgent, BriefInput
from ..models.agent_io import BriefOutput, PointDraft
from ..providers.llm import LLMRequest
from .record import ProductRecord, money_value
from .release import record_facts
from .storage import persisted

log = logging.getLogger(__name__)

MAX_POINTS = 10
MAX_POINT_CHARS = 140

ADDENDUM = """This is an onboarded product. DOCUMENT holds its approved record and the readable text of its source files,
in any language. The show's language is {lang}. These rules replace the counts and lengths above.
A. Glossary: every brand, product and short name, ingredient and key technical term as the files write it (original
spelling, any script), with `spoken_forms`: how a host says it in {lang}, and sound-alikes a speech recogniser may hear
instead. Up to 40 terms.
B. Prompter points, written in {lang}: the must-say items: the key approved claims with their qualifiers and test
conditions, the cautions the host must say, and the offers with their conditions. `required=true` for the cautions
and the qualified claims that must be said. At most {max_points} points, each at most {max_chars} characters. Never a
claim the record lists as not approved, and never a value the DOCUMENT does not state."""
# D-269 arm "terms" (blind brief grading: 0 of 17 offer points kept all their conditions)
OFFER_POINT_CHARS = 240
OFFER_RULE = """
D. Offers: one point per line under "Offers", with `source_section` "Offer <id>" (the id in brackets on that
line) and `required=true`. The point states every term on its line: the amount or price, any code, the dates or
duration, where and to whom it applies, whether it combines with other offers, and any limit. An offer point may be
up to {offer_chars} characters."""
# D-272 arm "code" (blind grading: model-written offer points widened or narrowed offers and pushed out cautions)
OFFER_CODE_RULE = """
D. Offers: write no point about an offer. The offer points are added from the record after yours."""
_SYMBOL = {"SGD": "S$", "MYR": "RM", "USD": "US$", "HKD": "HK$", "AUD": "A$", "GBP": "£", "EUR": "€", "JPY": "¥"}
_COMPARE = {"gt": "above {}", "ge": "{} or more", "lt": "below {}", "le": "up to {}"}


def _sentences(items: list[str], head: str, limit: int = MAX_POINT_CHARS) -> list[str]:
    """`items` as few sentences of at most `limit` characters, cut only between items."""
    out, cur = [], head
    for x in items:
        x = x.strip().rstrip(".;")
        nxt = f"{cur}{'; ' if cur != head else ''}{x}"
        if cur != head and len(nxt) + 1 > limit:
            out.append(cur + ".")
            nxt = head + x
        cur = nxt
    return out + ([cur + "."] if cur != head else [])


def _money(m) -> str:
    """As a host says it: "S$4", "S$7.50", "RM119"; another currency by its code."""
    v = money_value(m.currency, m.minor)
    num = f"{v:,.0f}" if v == v.to_integral_value() else f"{v:,.2f}"
    return f"{_SYMBOL[m.currency]}{num}" if m.currency in _SYMBOL else f"{num} {m.currency}"


def _date(value: str):
    import datetime as dt

    try:
        return dt.date.fromisoformat(value[:10])
    except (TypeError, ValueError):
        return None


def _when(starts: str | None, ends: str | None) -> str | None:
    """Dates once, as said ("from 1 to 31 October 2026"); no times. A value that is not an ISO date stays as written."""
    a, b = _date(starts or ""), _date(ends or "")
    day = lambda d, month=True, year=True: f"{d.day}" + (f" {d.strftime('%B')}" if month else "") + (  # noqa: E731
        f" {d.year}" if year else "")
    if a and b:
        return (f"from {day(a, a.month != b.month, a.year != b.year)} to {day(b)}"
                if a != b else f"on {day(a)}")
    if starts or ends:
        return (f"from {day(a) if a else starts}" if starts else "") + (" " if starts and ends else "") + (
            f"until {day(b) if b else ends}" if ends else "")
    return None


def _said(d, text: str) -> bool:
    """The text already gives this date (its day number and its month's name or first three letters)."""
    low = text.lower()
    return (str(d.day) in re.findall(r"\d+", text)
            and (d.strftime("%B").lower() in low or d.strftime("%b").lower() in low or f"{d.month:02d}" in text))


def _threshold(o, lexicon) -> str:
    """The spend threshold as the terms word it ("above S$40", "S$40 or more"); never a comparison of our own."""
    amount = _money(o.amount)
    num = str(money_value(o.amount.currency, o.amount.minor)).split(".")[0]
    for q in (e.quote or "" for e in o.evidence):
        for m in re.finditer(re.escape(num), q):
            kind = lexicon.comparison_kind(q[max(0, m.start() - 20):m.end() + 15]) if lexicon is not None else None
            if kind in _COMPARE:
                return _COMPARE[kind].format(amount)
    return f"the {amount} spend in the terms"


def _norm(s: str) -> str:
    return " ".join(re.findall(r"\w+", s.lower()))


def offer_lines(record: ProductRecord, lexicon=None) -> list[tuple[str, list[str]]]:
    """D-272: (offer_id, sentences) per offer, from the record's own fields, in a fixed order: what the viewer gets;
    when; the terms as written. Patch 1 (blind grading: the combinable yes/no widened offers, a gift with purchase
    read as "buy 1, get 1", "minimum spend" for "above S$40", timestamps and key: value phrases): the combinable
    field is never printed (a condition that names what it combines with is printed as written); the offer's kind
    decides the wording, so only a multibuy says "buy N, get M"; a spend threshold keeps the comparison its terms
    use; dates are said once, without times; money as "S$4". A value the title or a condition already says is not
    repeated. A code (capitals with a digit) the evidence quotes hold and the fields do not is added."""
    out = []
    for o in record.offers:
        own = " ".join([o.title, *o.conditions])
        nums = set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", own))  # not the 10 of a code SAVE10
        new = lambda m: str(money_value(m.currency, m.minor)).split(".")[0] not in nums  # noqa: E731
        got = []
        if o.kind == "percent_off" and o.percent and o.percent not in nums:
            got.append(f"{o.percent}% off")
        elif o.kind == "amount_off" and o.amount is not None and new(o.amount):
            got.append(f"{_money(o.amount)} off")
        elif o.kind in ("fixed_price", "bundle") and o.amount is not None and new(o.amount):
            got.append(f"for {_money(o.amount)}" + (f" for {o.buy}" if o.kind == "bundle" and o.buy else ""))
        elif o.kind == "buy_x_get_y" and o.buy and o.get and not {str(o.buy), str(o.get)} <= nums:
            got.append(f"buy {o.buy}, get {o.get}")
        if o.gift and o.gift.lower() not in own.lower():
            got.append(f"get a free {o.gift}")
        if o.kind == "spend_threshold_gift" and o.amount is not None and new(o.amount):
            got.append(f"when you spend {_threshold(o, lexicon)}")
        got += [f"with code {c}" for c in dict.fromkeys(_CODE.findall(" ".join(e.quote or "" for e in o.evidence)))
                if c not in own]
        lines = [o.title.strip().rstrip(".") + (": " + ", ".join(got) if got else "") + "."]
        dates = [d for d in (_date(o.starts or ""), _date(o.ends or "")) if d]
        when = None if dates and all(_said(d, own) for d in dates) else _when(o.starts, o.ends)
        when = ", ".join(x for x in (when, f"for {o.duration_min} minutes" if o.duration_min else None) if x)
        if when:
            lines.append(f"Valid {when}.")
        lines += _sentences([c for c in o.conditions if _norm(c) not in _norm(o.title)], "Terms: ")
        out.append((o.offer_id, lines))
    return out


_CODE = re.compile(r"\b[A-Z][A-Z0-9]*\d[A-Z0-9]*\b")  # an offer code such as SAVE10
_KEEP = re.compile(r"\d+(?:[.,]\d+)?|\b[A-Z][A-Z0-9]*\d[A-Z0-9]*\b")  # numbers and codes such as SAVE10


async def offer_points(llm, record: ProductRecord, lang: str, session_id: str | None = None,
                       lexicon=None) -> list[PointDraft]:
    """D-272: the offer points in the show's language. The sentences are built in English from the record; another
    show language, or a record in another language, gets them translated (the D-232 prompt), and a translated line
    keeps its place only if every number and code survived, else the English line stays (logged)."""
    from .read import READ_DEADLINE_MS, READ_MODEL
    from .record import _Model
    from .translate import PROMPT

    built = offer_lines(record, lexicon)
    flat = [x for _, xs in built for x in xs]
    if flat and (lang.split("-")[0].lower() != "en" or record.language.split("-")[0].lower() != "en"):
        class Lines(_Model):
            lines: list[str]

        res = await llm.call(LLMRequest(
            agent="brief_offers_translate", model=READ_MODEL, thinking_level="LOW",
            prompt_version="brief_offers_translate-1", system_instruction=PROMPT, output_model=Lines,
            deadline_ms=READ_DEADLINE_MS, session_id=session_id,
            user_message=f'<data name="TARGET">{lang}</data>\n<data name="LINES">'
                         + json.dumps({"lines": flat}, ensure_ascii=False) + "</data>",
            mock_primary_text=f"{lang}|offers|{record.product_name}", mock_fallback=lambda _: None))
        got = res.output.lines if res.status == "ok" and res.output is not None else []
        if len(got) == len(flat):
            keep = lambda s: sorted(_KEEP.findall(s.replace(",", "")))  # noqa: E731
            for i, (a, b) in enumerate(zip(flat, got)):
                if keep(a) == keep(b):
                    flat[i] = b
                else:
                    log.info("brief offer line kept in English: a number or code changed | %r -> %r", a, b)
        else:
            log.info("brief offer lines kept in English: translation %s", res.status)
    it = iter(flat)
    return [PointDraft(text=next(it), required=False, source_section=f"Offer {oid}") for oid, xs in built for _ in xs]


def release_document(record: ProductRecord, file_texts: list[tuple[str, str]] = (), offers: str = "sheet") -> str:
    """The record as a sheet with section headings, then each source file's readable text. D-269 `offers="terms"`:
    each offer line carries every term the fact checker gets (percent, dates, combinability, conditions, the terms as
    written) and its id."""
    lines = [f"# {record.product_name}", f"Brand: {record.brand}"]
    if record.short_names:
        lines.append("Also called: " + ", ".join(record.short_names))
    lines.append(f"Category: {record.category}")
    if record.ingredients:
        lines += ["", "## Key ingredients", "| Ingredient | Amount |", "|---|---|"]
        lines += [f"| {i.name} | {(i.amount_value or '') + ' ' + (i.amount_unit or '')} |".replace("  ", " ")
                  for i in record.ingredients]
    sections = (("Approved on-air claims", [c.text for c in record.approved_claims]),
                ("Test results", [f"{q.statement}{', ' + q.conditions if q.conditions else ''} ({q.qualifier})"
                                  for q in record.qualified_results]),
                ("Cautions", [c.text for c in record.cautions]),
                ("Offers", [f"[{k.removeprefix('offer-')}] {x.removeprefix('Offer: ')}" for k, x in record_facts(
                    record, lambda m: f"{money_value(m.currency, m.minor)} {m.currency}") if k.startswith("offer-")]
                 if offers == "terms" else
                 [o.title + "".join(f"; {c}" for c in o.conditions)
                  + (f"; {money_value(o.amount.currency, o.amount.minor)} {o.amount.currency}" if o.amount
                     else "") for o in record.offers]),
                ("How to use", [h.text for h in record.how_to_use]),
                ("Key facts", [k.text for k in record.key_facts]),
                ("Claims not approved", [c.text for c in record.not_approved_claims]))
    for title, items in sections:
        if items:
            lines += ["", f"## {title}", *(f"- {x}" for x in items)]
    for name, text in file_texts:
        if text.strip():
            lines += ["", f"## Source file {name}", text.strip()]
    return "\n".join(lines)


async def brief_release(llm, prompt, reflex, root: Path, release_id: str, record: ProductRecord, lang: str, *,
                        model: str | None = None, thinking: str | None = None, deadline_ms: int = 60_000,
                        offers: str = "sheet"):
    """(AgentResult, seconds) of the BriefAgent on a release. `model`/`thinking` override BRIEF_MODEL/BRIEF_THINKING
    (scripts/eval_brief.py); `offers` is BRIEF_OFFERS (D-269)."""
    from .sources import release_sources

    texts = [(p.doc, p.text) for p in release_sources(str(root), release_id)[1]]
    extra = ADDENDUM.format(lang=lang, max_points=MAX_POINTS, max_chars=MAX_POINT_CHARS)
    if offers == "terms":
        extra += OFFER_RULE.format(offer_chars=OFFER_POINT_CHARS)
    elif offers == "code":
        extra += OFFER_CODE_RULE
    agent = BriefAgent(llm, prompt, reflex, extra=extra, max_points=MAX_POINTS, max_chars=MAX_POINT_CHARS,
                       model=model, thinking=thinking, offer_chars=OFFER_POINT_CHARS if offers == "terms" else 0)
    t0 = time.perf_counter()
    res = await agent.run(BriefInput(product_id=release_id, document_text=release_document(record, texts, offers)),
                          deadline_ms=deadline_ms)
    if offers == "code" and res.output is not None:
        # D-272: the model's points first (claims and cautions are never pushed out), then the record's offers
        kept = []
        for p in res.output.prompter_points:
            if "offer" in p.source_section.lower():
                log.info("brief point dropped by code: offers come from the record | %r", p.text)
            else:
                kept.append(p)
        res.output.prompter_points = kept + await offer_points(llm, record, lang, lexicon=reflex.lexicon)
    return res, round(time.perf_counter() - t0, 1)


def save_brief(root: Path, release_id: str, out: BriefOutput, models: str) -> Path:
    folder = root / "briefs"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{release_id}.json"
    path.write_text(json.dumps({"release_id": release_id, "model": models, "at": int(time.time() * 1000),
                                "brief": out.model_dump(mode="json")}, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    persisted(path, create_only=True)  # D-263: write-once, like the release
    return path


def load_brief(root: Path, release_id: str) -> BriefOutput | None:
    path = root / "briefs" / f"{release_id}.json"
    if not path.is_file():
        return None
    return BriefOutput.model_validate(json.loads(path.read_text(encoding="utf-8"))["brief"])
