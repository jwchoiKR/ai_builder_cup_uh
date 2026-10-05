"""Onboarding step 7 (P0, first cut): an approved record becomes an immutable release, and a release becomes a
data pack for the sessions that use it. The release is ADDED next to the shipped products (answers 10/5): a session
created with `release_id` runs a one-segment show of that product under the market's rules; other sessions keep
the shipped catalog.

The adapter still writes the passages under the section names today's live path reads ("Key facts", "Cautions",
...); replacing those lookups with record fields is the spec's section 2 work.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import time
from decimal import ROUND_DOWN, ROUND_HALF_UP, ROUND_UP, Decimal
from pathlib import Path

from ..logic.catalog import DataPack, DataPackError
from ..models.data import (
    AvoidSaying, Passage, PrompterPoint, Product, ProductsFile, Promo, PromosFile, QualifiedResult, Runsheet,
    RunsheetItem,
)
from .record import AvoidSaying as RecordAvoid
from .record import Money, ProductRecord, Text

SEGMENT_SEC = 600


def _slug(text: str, n: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:n] or "item"


def product_key(record: ProductRecord) -> str:
    """D-227: a stable id for brand + product in any script: its Latin letters and digits (if any) plus a short hash,
    so two Korean or Japanese products never share an id."""
    digest = hashlib.sha1(f"{record.brand}|{record.product_name}".encode()).hexdigest()[:8]
    latin = _slug(f"{record.brand} {record.product_name}", 24).replace("-", "_")
    return f"{latin}_{digest}" if latin != "item" else f"p_{digest}"


def law_applies(base: DataPack, category: str) -> bool:
    """D-227: the market's law pack covers this product category (its own category or one it lists in `covers`)."""
    m = base.market
    norm = lambda c: c.strip().lower().replace(" ", "_").rstrip("s")  # noqa: E731
    return m is not None and norm(category) in {norm(m.category), *(norm(c) for c in m.covers)}


def save_release(root: Path, record: ProductRecord, job_id: str, translations: dict | None = None) -> str:
    """Immutable: releases/<release_id>.json, a new id per approval."""
    folder = root / "releases"
    folder.mkdir(parents=True, exist_ok=True)
    base = "rel_" + product_key(record)
    n = 1 + sum(1 for _ in folder.glob(f"{base}_v*.json"))
    release_id = f"{base}_v{n}"
    (folder / f"{release_id}.json").write_text(json.dumps(
        {"release_id": release_id, "job_id": job_id, "approved_at": int(time.time() * 1000),
         "record": record.model_dump(mode="json"), "translations": translations or {}},
        ensure_ascii=False, indent=1), encoding="utf-8")
    return release_id


def load_release(root: Path, release_id: str) -> ProductRecord:
    return load_release_full(root, release_id)[0]


def load_release_full(root: Path, release_id: str) -> tuple[ProductRecord, dict]:
    """The record and its stored translations per language (D-232)."""
    path = root / "releases" / f"{release_id}.json"
    if not re.fullmatch(r"rel_[a-z0-9_]+_v\d+", release_id) or not path.is_file():
        raise DataPackError(f"unknown release {release_id!r}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return ProductRecord.model_validate(data["record"]), data.get("translations") or {}


def _price(prices: list[Money], kind: str, currency: str, market: str) -> Decimal | None:
    for m in prices:
        if m.kind == kind and m.currency == currency and m.market in (None, market):
            return Decimal(m.minor) / 100
    return None


def _rounded(value: Decimal, rule: str | None) -> Decimal:
    """D-223: the stated rounding rule ("nearest 10 cents", "rounded down to the dollar"); 2 decimals, half up when
    none is stated."""
    text = (rule or "").lower()
    quantum = (Decimal("0.1") if re.search(r"10 ?(cents|sen)|0\.1\b", text) else
               Decimal("1") if re.search(r"dollar|ringgit|whole|nearest 1\b|integer", text) else Decimal("0.01"))
    mode = (ROUND_DOWN if re.search(r"\bdown\b|floor", text) else ROUND_UP if re.search(r"\bup\b|ceil", text)
            else ROUND_HALF_UP)
    return (value / quantum).quantize(Decimal("1"), rounding=mode) * quantum


def promos_from_offers(record: ProductRecord, pid: str, main_variant: str, live: Decimal, cur: str,
                       market: str) -> list[Promo]:
    """D-223 (P0 step 4): the record's offers as promos, with every promo price computed in code from the stated
    terms (never by a model): percent off, amount off and a fixed price change the price; a gift over a spend and
    buy-X-get-Y do not (their terms are said as written)."""
    out = []
    for i, o in enumerate(record.offers):
        if o.variant_ids and main_variant not in o.variant_ids:
            continue
        amount = (Decimal(o.amount.minor) / 100 if o.amount is not None and o.amount.currency == cur
                  and o.amount.market in (None, market) else None)
        pct = Decimal(o.percent) if o.percent else None
        price = (live * (1 - pct / 100) if o.kind == "percent_off" and pct is not None else
                 live - amount if o.kind == "amount_off" and amount is not None else
                 amount if o.kind == "fixed_price" and amount is not None else None)
        duration = (o.duration_min or 0) * 60 or SEGMENT_SEC
        common = dict(promo_id=f"{pid}_offer_{i + 1}", kind=o.kind, title=o.title, duration_sec=duration,
                      applies_to=[pid], viewer_text=o.title, host_text=o.title)
        if price is not None and price > 0:
            out.append(Promo(**common, changes_prices=True, promo_prices={pid: float(_rounded(price, o.rounding))},
                             discount_pct_off_live_price=float(pct) if pct is not None else None))
        elif o.kind == "spend_threshold_gift" and amount is not None:
            out.append(Promo(**common, changes_prices=False, min_spend=float(amount)))
        elif o.kind in ("buy_x_get_y", "bundle", "other"):
            out.append(Promo(**common, changes_prices=False))
    return out


UNREVIEWED = " (unreviewed translation)"
UNREVIEWED_DOC = "unreviewed-translation"


def _line(x) -> tuple[str, bool]:
    return (x, False) if isinstance(x, str) else (x.get("text") or x.get("say") or "", bool(x.get("reviewed")))


def in_language(record: ProductRecord, lang: str, translations: dict | None) -> tuple[ProductRecord, set[str]]:
    """D-232: the record's host-facing lines in the show's language: its own when it is written in it, else the stored
    translation, else none (an alert then has no replacement line; nothing is translated live). D-233: also the
    translated texts not reviewed yet (claims carry a visible mark; cautions are kept out of auto-posts)."""
    if record.language.split("-")[0].lower() == lang.split("-")[0].lower():
        return record, set()
    t = (translations or {}).get(lang)
    ev = lambda items, i: items[i].evidence if i < len(items) else []  # noqa: E731
    if t is None:
        return record.model_copy(update={"approved_claims": [], "avoid_saying": [], "cautions": []}), set()
    unreviewed: set[str] = set()

    def text(x) -> str:
        s, ok = _line(x)
        if not ok:
            unreviewed.add(s)
        return s if ok else s + UNREVIEWED

    claims = [Text(text=text(x), evidence=ev(record.approved_claims, i)) for i, x in enumerate(t["approved_claims"])]
    cautions = []
    for i, x in enumerate(t["cautions"]):
        s, ok = _line(x)
        if not ok:
            unreviewed.add(s)
        cautions.append(Text(text=s, evidence=ev(record.cautions, i)))
    avoid = [RecordAvoid(say_not=a["say_not"], say=a["say"] + ("" if a.get("reviewed") else UNREVIEWED),
                         evidence=ev(record.avoid_saying, i)) for i, a in enumerate(t["avoid_saying"])]
    return record.model_copy(update={"approved_claims": claims, "cautions": cautions, "avoid_saying": avoid}), unreviewed


def record_facts(record: ProductRecord, money_of) -> list[tuple[str, str]]:
    """D-242 arm FR: the record's facts as (key, text) lines the fact checker can quote: every size's price in every
    market, superseded values (the documents' older dated version), offer terms, and each test result's qualifier."""
    out: list[tuple[str, str]] = []
    for v in record.variants:
        size = f"{v.size_value} {v.size_unit or ''}".strip() if v.size_value else ""
        for m in v.prices:
            label = f"{m.market or 'any market'} {m.kind} price"
            out.append((f"{v.variant_id}-{m.market}-{m.kind}",
                        f"{v.name}{f' ({size})' if size else ''} · {label}: {money_of(m)}"))
        if size:
            out.append((f"{v.variant_id}-size", f"{v.name} · size: {size}"))
    for c in record.conflicts:
        dated = [(d, v) for v, d in zip(c.values, c.effective_dates) if d]
        if len(dated) >= 2:
            dated.sort()
            current = dated[-1]
            for d, v in dated[:-1]:
                out.append((f"superseded-{c.field}-{d}",
                            f"Superseded: {c.field} was {v} (version of {d}); current value {current[1]} "
                            f"(version of {current[0]}). Saying {v} as current is wrong."))
    for o in record.offers:
        terms = [o.title]
        if o.percent:
            terms.append(f"{o.percent}% off")
        if o.amount is not None:
            terms.append(f"amount {money_of(o.amount)}")
        if o.buy and o.get:
            terms.append(f"buy {o.buy} get {o.get}")
        if o.starts or o.ends:
            terms.append(f"from {o.starts or '?'} to {o.ends or '?'}")
        if o.duration_min:
            terms.append(f"{o.duration_min} minutes")
        out.append((f"offer-{o.offer_id}", "Offer: " + "; ".join(terms)))
    for i, q in enumerate(record.qualified_results):
        out.append((f"result-{i + 1}", f"Test result: {q.statement}. Must be said with: {q.qualifier} ({q.provenance})."))
    return out


def release_pack(base: DataPack, record: ProductRecord, release_id: str, lawpacks: Path | None = None,
                 translations: dict | None = None, fact_mode: str = "sheet") -> DataPack:
    """The base pack's market, language, rules and intents, with this release's one product, passages and show."""
    assert base.market is not None
    record, unreviewed = in_language(record, base.lang, translations)
    # D-233: a test result's marker in a claim ("in 4 weeks†") becomes the qualifier the host must say
    for q in record.qualified_results:
        if q.marker:
            for c in record.approved_claims:
                if q.marker in c.text and q.qualifier not in c.text:
                    c.text = f"{c.text.replace(q.marker, '').rstrip()} ({q.qualifier})"
    cur, market, sym = base.market.currency.code, base.market.market, base.market.currency.symbol
    priced = [(v, _price(v.prices, "list", cur, market), _price(v.prices, "live", cur, market))
              for v in record.variants]
    priced = [(v, lp, live) for v, lp, live in priced if lp is not None or live is not None]
    if not priced:
        raise DataPackError(f"release {release_id} has no {cur} price for market {market}")
    main, list_price, live_price = priced[0]
    list_price, live_price = list_price or live_price, live_price or list_price
    money = lambda d: f"{sym}{d:.2f}"  # noqa: E731
    pid = product_key(record)
    code = main.variant_id
    size = f"{main.size_value} {main.size_unit}".strip() if main.size_value else ""
    doc = record.variants[0].evidence[0].file if record.variants[0].evidence else ""

    passages: list[Passage] = []

    def add(section: str, key: str, text: str, unreviewed_line: bool = False) -> None:
        # D-233: a passage from an unreviewed translation is marked, so an answer citing it is never auto-posted
        passages.append(Passage(passage_id=f"{code}#{_slug(section)}#{_slug(key)}", product_id=pid,
                                doc=UNREVIEWED_DOC if unreviewed_line else doc, section=section, text=text))

    add("Product overview", "overview", f"{record.brand} {record.product_name} ({record.category}).")
    # D-242 arm FR: the price passages name their size, so a second size's price is never read as this one's
    sized = f" ({size})" if fact_mode == "record" and size else ""
    add("Key facts", "list-price", f"List price{sized}: {money(list_price)}")
    add("Key facts", "live-broadcast-price", f"Live broadcast price{sized}: {money(live_price)}")
    if size:
        add("Key facts", "volume", f"Volume: {size}")
    for v, lp, live in priced[1:]:
        add("Key facts", f"variant-{v.variant_id}",
            f"{v.name}: list price {money(lp or live)}, live broadcast price {money(live or lp)}")
    for i, f in enumerate(record.key_facts):
        add("Key facts", f"fact-{i + 1}-{f.text[:30]}", f.text)
    if fact_mode == "record":
        def fact_money(m) -> str:  # this market's currency as shown on air, another one by its code
            amount = Decimal(m.minor) / 100
            return f"{sym}{amount:.2f}" if m.currency == cur else f"{m.currency} {amount:.2f}"

        for key, text in record_facts(record, fact_money):
            add("Record facts", key, text)
    for ing in record.ingredients:
        amount = f": {ing.amount_value}{ing.amount_unit or ''}" if ing.amount_value else ""
        add("Key ingredients", ing.name, f"{ing.name}{amount}{'. ' + ing.purpose if ing.purpose else ''}")
    if record.ingredient_list_complete:
        add("Ingredients", "all", "Ingredients: " + ", ".join(i.name for i in record.ingredients) + ".")
    for i, h in enumerate(record.how_to_use):
        add("How to use", f"step-{i + 1}", h.text)
    for i, c in enumerate(record.cautions):
        add("Cautions", f"caution-{i + 1}", c.text, c.text in unreviewed)
    for i, q in enumerate(record.qualified_results):
        add("In-house test results", f"result-{i + 1}", f"{q.statement} ({q.qualifier})")
    if record.approved_claims:
        add("Approved on-air claims", "approved",
            "Approved claims: " + " ".join(c.text.removesuffix(UNREVIEWED) for c in record.approved_claims),
            any(c.text.endswith(UNREVIEWED) for c in record.approved_claims))
    if record.not_approved_claims:
        add("Approved on-air claims", "not-approved",
            "Claims not approved: " + " ".join(c.text for c in record.not_approved_claims))
    seen: set[str] = set()
    unique = []
    for p in passages:  # repeated keys get a suffix, so passage ids stay unique
        pid_ = p.passage_id
        while pid_ in seen:
            pid_ += "-2"
        seen.add(pid_)
        unique.append(p.model_copy(update={"passage_id": pid_}))

    points = [PrompterPoint(point_id=f"{pid}-p{i + 1}", text=c.text, required=i == 0)
              for i, c in enumerate(record.approved_claims)]
    product = Product(
        product_id=pid, code=code, name=record.product_name,
        short_name=record.short_names[0] if record.short_names else record.product_name,
        eyebrow="", tagline="", doc=doc, volume=size, list_price=float(list_price), live_price=float(live_price),
        hero_badge="", aliases=list(dict.fromkeys([record.product_name, *record.short_names])),
        # D-233: the prompter's ingredient panel: the first 4 ingredients with an amount
        key_facts={_slug(i.name).replace("-", "_"): f"{i.amount_value}{i.amount_unit or ''}".replace("% ", "%")
                   for i in record.ingredients if i.amount_value}
        if len([i for i in record.ingredients if i.amount_value]) <= 4 else
        {_slug(i.name).replace("-", "_"): f"{i.amount_value}{i.amount_unit or ''}"
         for i in [x for x in record.ingredients if x.amount_value][:4]}, prompter_points=points, approved_claims=[c.text for c in record.approved_claims],
        not_approved_claims=[c.text for c in record.not_approved_claims],
        qualified_results=[QualifiedResult(result_id=f"{pid}-r{i + 1}", numbers=q.numbers,
                                           say=f"{q.statement} ({q.qualifier})")
                           for i, q in enumerate(record.qualified_results)],
        cautions=[c.text for c in record.cautions],
        avoid_saying=[AvoidSaying(say_not=a.say_not, say=a.say) for a in record.avoid_saying],
    )
    promos = promos_from_offers(record, pid, main.variant_id, live_price, cur, market)
    runsheet = Runsheet(runsheet_id=release_id, title=f"{record.brand} · {record.product_name}", brand=record.brand,
                        language=record.language, market=market,
                        items=[RunsheetItem(order=1, product_id=pid, planned_duration_sec=SEGMENT_SEC,
                                            required_point_ids=[points[0].point_id] if points else [])],
                        promo_ids=[p.promo_id for p in promos])
    products = ProductsFile(brand=record.brand, currency=cur, currency_symbol=sym, set_offers=[], products=[product])
    # D-227: a category the market's law pack does not cover gets no law rules (never the cosmetics rules); only
    # brand-level checks may run, and there are none until brand guidelines are onboarded
    rules = base.rules if law_applies(base, record.category) else base.rules.model_copy(
        update={"rules": [], "category": record.category})
    if rules is not base.rules and lawpacks is not None and base.market is not None:
        # D-229: an approved law pack built from the regulator's documents for this market and category
        from .lawpack import lawpack_for, to_rules

        found = lawpack_for(lawpacks, base.market.market, record.category)
        if found is not None:
            rules = rules.model_copy(update={"rules": to_rules(*found), "policy_id": found[0]})
    if lawpacks is not None:
        # D-241: the brand's own approved rules are added on top (restrict only: no law rule is removed or replaced)
        from .lawpack import brandpack_for, to_rules as _to_rules

        brand = brandpack_for(lawpacks, record.brand)
        if brand is not None:
            have = {x.rule_id for x in rules.rules}
            extra = [x.model_copy(update={"rule_id": f"BR-{x.rule_id}"}) for x in _to_rules(*brand)
                     if f"BR-{x.rule_id}" not in have]
            rules = rules.model_copy(update={"rules": [*rules.rules, *extra]})
    return dataclasses.replace(base, products=products, runsheets={release_id: runsheet}, rules=rules,
                               promos=PromosFile(promos=promos, rules=base.promos.rules), passages=unique)
