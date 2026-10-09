"""A show of 2-3 approved releases (D-279, the user's minimal multi-product show).

Each release's pack is built as for a one-product show (release.py), then merged: products, passages, promos, the run
sheet (one segment per release, in order, each with its own planned time and required points) and the rules. A rule
(D-427: and a law or brand pack) remembers which products it came with, so the compliance judge gets only the rules
of the products a line can be about (`Catalog.rules_for`) and only the packs of the given products
(`originals_for`). Offers stay per release: no set offer across releases.
"""
from __future__ import annotations

import dataclasses

from ..logic.catalog import DataPack, DataPackError
from ..models.data import ProductsFile, PromosFile, Runsheet

MAX_RELEASES = 3


def show_id(release_ids: tuple[str, ...]) -> str:
    return "show_" + "+".join(release_ids)


def show_pack(packs: list[DataPack], release_ids: tuple[str, ...]) -> DataPack:
    """One pack for the show; `packs[i]` is the one-release pack of `release_ids[i]`."""
    if not 2 <= len(packs) <= MAX_RELEASES:
        raise DataPackError(f"a show takes 2 to {MAX_RELEASES} releases, not {len(packs)}")
    first = packs[0]
    symbols = {p.products.currency_symbol for p in packs}
    if len(symbols) > 1:
        raise DataPackError(f"the releases are priced in different currencies: {sorted(symbols)}")
    sid = show_id(release_ids)
    sheets = [next(iter(p.runsheets.values())) for p in packs]
    items = [i.model_copy(update={"order": n}) for n, s in enumerate(sheets) for i in s.items]
    runsheet = Runsheet(runsheet_id=sid, title=" + ".join(s.title for s in sheets),
                        brand=" / ".join(dict.fromkeys(s.brand for s in sheets)), language=first.lang,
                        market=sheets[0].market, items=items, promo_ids=[x for s in sheets for x in s.promo_ids])
    products = ProductsFile(brand=" / ".join(dict.fromkeys(p.products.brand for p in packs)),
                            currency=first.products.currency, currency_symbol=first.products.currency_symbol,
                            set_offers=[], products=[x for p in packs for x in p.products.products])
    rules, owners = [], {}
    for p in packs:
        pids = frozenset(x.product_id for x in p.products.products)
        for r in p.rules.rules:
            if r.rule_id not in owners:
                rules.append(r)
                owners[r.rule_id] = frozenset()
            owners[r.rule_id] |= pids  # ponytail: a same id from two packs is one rule (the first text wins)
        for k in p.rules.pack_ids:  # D-427: a law or brand pack's documents, by the products whose release has it
            owners[k] = owners.get(k, frozenset()) | pids
    return dataclasses.replace(
        first, products=products, runsheets={sid: runsheet},
        rules=first.rules.model_copy(update={"rules": rules,
                                             "sources": list({s.source_id: s for p in packs
                                                              for s in p.rules.sources}.values()),
                                             "pack_ids": list(dict.fromkeys(k for p in packs
                                                                            for k in p.rules.pack_ids))}),
        promos=PromosFile(promos=[x for p in packs for x in p.promos.promos], rules=first.promos.rules),
        passages=[x for p in packs for x in p.passages],
        releases={k: v for p in packs for k, v in p.releases.items()}, rule_products=owners)
