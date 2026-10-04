"""Data pack loading and catalog helpers (DEV_SPEC §6.1, §6.4).

Product facts come only from data/products/, rules only from data/markets/ (law) and data/lang/ (wording). Prices are read,
never computed.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from functools import cached_property
from pathlib import Path

from ..models.data import (
    ClaimRulesFile,
    Intent,
    IntentsFile,
    LangPack,
    MarketPack,
    NoticesFile,
    Passage,
    Product,
    ProductsFile,
    Promo,
    PromosFile,
    Rule,
    Runsheet,
    SetOffer,
)

DEFAULT_RUNSHEET_ID = "daon_skincare_demo"

# §6.4: the bare alias "cream" maps to the cream only when "ampoule" is not also present.
_GENERIC_ALIAS_BLOCKERS = {"cream": "ampoule"}


def claim_rules(market: MarketPack, lang: LangPack) -> ClaimRulesFile:
    """D-129: the rules of one broadcast = the market's law + the language's wording for each category."""
    offered = {x.lang for x in market.languages}
    if lang.lang not in offered:
        raise DataPackError(f"market {market.market} does not offer language {lang.lang} (offers {sorted(offered)})")
    missing = sorted({r.category for r in market.rules} - set(lang.categories))
    if missing:
        raise DataPackError(f"language pack {lang.lang} has no wording for categories {missing}")
    return ClaimRulesFile(
        policy_id=market.policy_id, market=market.market, category=market.category, sources=market.sources,
        severity_display=market.severity_display,
        rules=[Rule(**r.model_dump(exclude={"category"}), **lang.categories[r.category].model_dump())
               for r in market.rules],
        negation_cues=lang.negation_cues, quote_cues=lang.quote_cues,
    )


class DataPackError(ValueError):
    pass


def _read_json(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@dataclass(frozen=True)
class DataPack:
    products: ProductsFile
    runsheets: dict[str, Runsheet]
    promos: PromosFile
    rules: ClaimRulesFile
    intents: IntentsFile
    notices: NoticesFile
    passages: list[Passage]
    market: MarketPack | None = None  # D-129: None only for packs built by hand in tests
    lang: str = "en"

    @property
    def stt_language(self) -> str:
        """The chirp_3 code of this broadcast language in this market (D-129)."""
        assert self.market is not None
        return next(x.stt_language for x in self.market.languages if x.lang == self.lang)

    @classmethod
    def load(cls, data_dir: Path, market: str = "SG", lang: str = "en") -> "DataPack":
        if not data_dir.is_dir():
            raise DataPackError(f"DATA_DIR not found: {data_dir}")
        runsheets = {}
        for p in sorted((data_dir / "runsheets").glob("*.json")):
            rs = Runsheet.model_validate(_read_json(p))
            runsheets[rs.runsheet_id] = rs
        passages = []
        with (data_dir / "products" / "passages.jsonl").open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    passages.append(Passage.model_validate_json(line))
        market_pack = MarketPack.model_validate(_read_json(data_dir / "markets" / f"{market.lower()}.json"))
        pack = cls(
            products=ProductsFile.model_validate(_read_json(data_dir / "products" / "products.json")),
            runsheets=runsheets,
            promos=PromosFile.model_validate(_read_json(data_dir / "promos" / "promos.json")),
            rules=claim_rules(market_pack, LangPack.model_validate(_read_json(data_dir / "lang" / f"{lang}.json"))),
            intents=IntentsFile.model_validate(_read_json(data_dir / "policy" / "intents.json")),
            notices=NoticesFile.model_validate(_read_json(data_dir / "templates" / "notices.json")),
            passages=passages,
            market=market_pack,
            lang=lang,
        )
        pack._validate()
        return pack

    def _validate(self) -> None:
        errors: list[str] = []
        pids = {p.product_id for p in self.products.products}
        set_ids = {s.set_id for s in self.products.set_offers}
        points = {p.product_id: {pt.point_id for pt in p.prompter_points} for p in self.products.products}
        promo_ids = {p.promo_id for p in self.promos.promos}

        def unique(kind: str, ids: list[str]) -> None:
            dupes = {i for i in ids if ids.count(i) > 1}
            if dupes:
                errors.append(f"duplicate {kind}: {sorted(dupes)}")

        unique("product_id", [p.product_id for p in self.products.products])
        unique("rule_id", [r.rule_id for r in self.rules.rules])
        unique("intent", [i.intent for i in self.intents.intents])
        unique("promo_id", [p.promo_id for p in self.promos.promos])
        unique("passage_id", [p.passage_id for p in self.passages])
        unique("point_id", [pt for ps in points.values() for pt in ps])
        if not self.runsheets:
            errors.append("no run-sheets in data/runsheets/")
        for s in self.products.set_offers:
            if missing := set(s.product_ids) - pids:
                errors.append(f"set {s.set_id}: unknown products {sorted(missing)}")
        for rs in self.runsheets.values():
            for item in rs.items:
                if item.product_id not in pids:
                    errors.append(f"run-sheet {rs.runsheet_id}: unknown product {item.product_id}")
                elif missing := set(item.required_point_ids) - points[item.product_id]:
                    errors.append(f"run-sheet {rs.runsheet_id}: unknown points {sorted(missing)}")
            if missing := set(rs.promo_ids) - promo_ids:
                errors.append(f"run-sheet {rs.runsheet_id}: unknown promos {sorted(missing)}")
        for promo in self.promos.promos:
            if missing := (set(promo.applies_to) | set(promo.promo_prices)) - pids - set_ids:
                errors.append(f"promo {promo.promo_id}: unknown products {sorted(missing)}")
            if promo.changes_prices and not promo.promo_prices:
                errors.append(f"promo {promo.promo_id}: changes_prices without promo_prices")
        for p in self.passages:
            if p.product_id not in pids:
                errors.append(f"passage {p.passage_id}: unknown product {p.product_id}")
        if DEFAULT_RUNSHEET_ID not in self.runsheets:
            errors.append(f"default run-sheet {DEFAULT_RUNSHEET_ID} missing")
        if self.market is not None and self.products.currency_symbol != self.market.currency.symbol:
            errors.append(f"products are priced in {self.products.currency_symbol}, market "
                          f"{self.market.market} uses {self.market.currency.symbol}")
        if errors:
            raise DataPackError("data pack is inconsistent: " + "; ".join(errors))

    # ---- lookups shared by all sessions ---------------------------------------------------

    @cached_property
    def rules_by_id(self) -> dict[str, Rule]:
        return {r.rule_id: r for r in self.rules.rules}

    @cached_property
    def intents_by_name(self) -> dict[str, Intent]:
        return {i.intent: i for i in self.intents.intents}

    @cached_property
    def promos_by_id(self) -> dict[str, Promo]:
        return {p.promo_id: p for p in self.promos.promos}

    def runsheet(self, runsheet_id: str) -> Runsheet:
        try:
            return self.runsheets[runsheet_id]
        except KeyError:
            raise DataPackError(f"unknown run-sheet {runsheet_id!r}") from None


class Catalog:
    """Catalog helpers for one run-sheet (product order decides `next_product`)."""

    def __init__(self, pack: DataPack, runsheet_id: str = DEFAULT_RUNSHEET_ID) -> None:
        self.pack = pack
        self.runsheet = pack.runsheet(runsheet_id)
        self._products = {p.product_id: p for p in pack.products.products}
        self._sets = {s.set_id: s for s in pack.products.set_offers}
        self.order = [item.product_id for item in sorted(self.runsheet.items, key=lambda i: i.order)]
        self._alias_patterns = [
            (p.product_id, alias, re.compile(rf"\b{re.escape(alias.lower())}\b"))
            for p in pack.products.products
            for alias in p.aliases
        ]

    @property
    def brand(self) -> str:
        return self.pack.products.brand

    @property
    def products(self) -> list[Product]:
        return list(self._products.values())

    @property
    def set_offers(self) -> list[SetOffer]:
        return list(self._sets.values())

    def get_product(self, pid: str) -> Product:
        try:
            return self._products[pid]
        except KeyError:
            raise KeyError(f"unknown product {pid!r}") from None

    def is_product(self, pid: str | None) -> bool:
        return pid in self._products

    def next_product(self, pid: str | None) -> str | None:
        """Next product in run-sheet order; the first product when `pid` is None; None after the last."""
        if pid is None:
            return self.order[0] if self.order else None
        i = self.order.index(pid)
        return self.order[i + 1] if i + 1 < len(self.order) else None

    def runsheet_item(self, pid: str):
        return next(item for item in self.runsheet.items if item.product_id == pid)

    # ---- aliases ----------------------------------------------------------------------------

    def _alias_hits(self, text: str) -> list[tuple[str, str]]:
        t = text.lower()
        return [(pid, alias) for pid, alias, rx in self._alias_patterns if rx.search(t)]

    def products_mentioned(self, text: str) -> set[str]:
        """All products named in `text` by any alias (word boundaries)."""
        return {pid for pid, _ in self._alias_hits(text)}

    def product_by_alias(self, text: str) -> str | None:
        """The product named in `text`: longest matching alias wins; a tie between products is None."""
        t = text.lower()
        hits = [
            (pid, alias)
            for pid, alias in self._alias_hits(text)
            if not (alias in _GENERIC_ALIAS_BLOCKERS and re.search(rf"\b{_GENERIC_ALIAS_BLOCKERS[alias]}\b", t))
        ]
        if not hits:
            return None
        longest = max(len(alias) for _, alias in hits)
        best = {pid for pid, alias in hits if len(alias) == longest}
        return best.pop() if len(best) == 1 else None

    # ---- prices -----------------------------------------------------------------------------

    def money(self, value: float) -> str:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return f"{self.pack.products.currency_symbol}{amount}"

    def live_price_value(self, pid: str) -> float:
        if pid in self._products:
            return self._products[pid].live_price
        if pid in self._sets:
            return self._sets[pid].live_price
        raise KeyError(f"unknown product or set {pid!r}")

    def price_display(self, pid: str, promo: Promo | None = None) -> str:
        """`S$36.00`, or the precomputed promo price (`S$32.40`) while a price-changing promo runs."""
        if promo is not None and promo.changes_prices and pid in promo.promo_prices:
            return self.money(promo.promo_prices[pid])
        return self.money(self.live_price_value(pid))

    # ---- claims -----------------------------------------------------------------------------

    def approved_claims(self, pid: str) -> list[str]:
        return list(self.get_product(pid).approved_claims)

    def not_approved_claims(self, pid: str) -> list[str]:
        return list(self.get_product(pid).not_approved_claims)
