"""Record answers: a one-value question (price, size) answered by code from the product record, with no LLM draft.

The value is the catalog's own (the price a running promo sets, else the live price; the product's size) and the
citation is the one sheet passage that states it. A price answer also says what helps the viewer decide now: the
list price it is down from, and an offer that is running (a gift over a spend), each from its own passage. Anything less certain returns None and the question takes the
composer path: a condition slot, a product whose variants differ, no passage or more than one passage for the value.
The answer still passes `verify_answer` like a composed draft; only the LLM draft and its LLM check are skipped.
"""
from __future__ import annotations

from collections.abc import Sequence

from ..models.agent_io import Citation, ComposerOutput
from ..models.data import Passage, Promo
from .catalog import Catalog
from .promos import price_promo, promo_passage
from .verify import number_set

RECORD_INTENTS = frozenset({"price", "volume"})
KEY_FACTS = "Key facts"


def _only(passages: Sequence[Passage]) -> Passage | None:
    return passages[0] if len(passages) == 1 else None


def _price(catalog: Catalog, product_id: str, passages: Sequence[Passage], promo: Promo | None,
           offers: Sequence[Promo]) -> tuple[str, list[Passage]] | None:
    product = catalog.get_product(product_id)
    active = price_promo(promo)
    if active is not None and product_id in active.promo_prices:
        value = catalog.price_display(product_id, active)
        text, cited = f"{product.name} is {value} right now ({active.title}).", [promo_passage(active, catalog)]
    else:
        live, listed = number_set(catalog.money(product.live_price)), number_set(catalog.money(product.list_price))
        # the passage of the live price: it states that price and, unless the two are equal, not the list price
        source = _only([p for p in passages if live <= number_set(p.text) and (live == listed or not listed <= number_set(p.text))])
        if source is None:
            return None
        text, cited = f"{product.name} is {catalog.money(product.live_price)} during the live broadcast", [source]
        # the list price it is down from, when one passage states that price alone
        was = _only([p for p in passages if number_set(p.text) == listed]) if product.list_price > product.live_price else None
        if was is not None:
            text += f" (list price {catalog.money(product.list_price)})"
            cited.append(was)
        text += "."
    # one running offer in its own viewer wording (a notice is the operator's banner, not an offer)
    offer = next((o for o in sorted(offers, key=lambda o: o.promo_id)
                  if not o.changes_prices and o.kind != "notice" and o.viewer_text.strip()), None)
    if offer is not None:
        text += f" Also on now: {offer.viewer_text.strip().rstrip('.')}."
        cited.append(promo_passage(offer, catalog))
    return text, cited


def _size(catalog: Catalog, product_id: str, passages: Sequence[Passage]) -> tuple[str, list[Passage]] | None:
    product = catalog.get_product(product_id)
    size = product.volume.strip()
    numbers = number_set(size)
    if not size or not numbers:
        return None
    # the passage of the size alone: it writes the size as the record does and states no other number
    source = _only([p for p in passages if size.lower() in p.text.lower() and number_set(p.text) == numbers])
    if source is None:
        return None
    return f"{product.name} comes in {size}.", [source]


def record_answer(catalog: Catalog, passages: Sequence[Passage], *, product_id: str | None, intent: str,
                  slots: dict[str, str | None], promo: Promo | None, offers: Sequence[Promo] = ()
                  ) -> tuple[ComposerOutput, list[Passage], set[str]] | None:
    """The answer, the passages it cites and the numbers of the asked value itself (a wording of the answer must keep
    them), or None when the record does not settle the question by itself. `passages` are the product's sheet
    passages; `offers` the running offers that change no price."""
    if intent not in RECORD_INTENTS or product_id is None or not catalog.is_product(product_id):
        return None
    if any(slots.values()):
        return None  # "price for students?", "the 100 mL one?": a condition or a variant is the composer's
    product = catalog.get_product(product_id)
    if len({(v.live_price, v.label) for v in product.variants}) > 1:
        return None
    facts = [p for p in passages if p.product_id == product_id and p.section == KEY_FACTS]
    found = (_price(catalog, product_id, facts, promo, offers) if intent == "price"
             else _size(catalog, product_id, facts))
    if found is None:
        return None
    text, cited = found
    output = ComposerOutput(answer=text, citations=[Citation(passage_id=p.passage_id, quote=p.text) for p in cited],
                            grounded=True, needs_human=False, reason="record answer")
    value = (catalog.price_display(product_id, price_promo(promo)) if intent == "price" else product.volume)
    return output, cited, number_set(value)
