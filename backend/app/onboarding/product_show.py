"""Rebuilt onboarding, step 5: an approved product (products/<id>/approved.json) and an uploaded regulation PDF
(regulations/<id>/) in the onboarding bucket become one show's data pack.

The show key "<product_id>:<regulation_id>" is the session's release id, so a session loaded again (another instance)
builds the same pack. The live compliance judge reads only the uploaded regulation PDF (no market law, no rule JSON,
so the comment checks get no restricted phrases); the prompter shows the product's prices and points.
"""
from __future__ import annotations

import dataclasses
import json
import re

from ..logic.catalog import DataPack, DataPackError
from ..models.data import (Passage, Product, ProductsFile, PromosFile, PrompterPoint, Runsheet, RunsheetItem)

SHOW_KEY = re.compile(r"(prd_[0-9a-f]{12}):(reg_[0-9a-f]{12})")
SEGMENT_SEC = 600


def show_key(product_id: str, regulation_id: str) -> str:
    return f"{product_id}:{regulation_id}"


def load(bucket, key: str) -> tuple[dict, list[tuple[str, bytes]]]:
    """The approved product info and the regulation PDFs (name, bytes) of a show key."""
    m = SHOW_KEY.fullmatch(key)
    if m is None:
        raise DataPackError(f"not a product show: {key!r}")
    product_id, regulation_id = m.groups()
    approved = bucket.download(f"products/{product_id}/approved.json")
    if approved is None:
        raise DataPackError(f"product {product_id} is not approved")
    pdfs = [(k.rsplit("/", 1)[1], bucket.download(k)) for k in bucket.keys(f"regulations/{regulation_id}/")
            if k.lower().endswith(".pdf")]
    if not pdfs:
        raise DataPackError(f"no regulation file {regulation_id}")
    return json.loads(approved)["info"], pdfs


def product_pack(base: DataPack, info: dict, key: str) -> DataPack:
    """The base pack's market, language and intents, with this one product, its prompter points, and the regulation
    PDF as the only document the compliance judge reads."""
    assert base.market is not None
    product_id, regulation_id = SHOW_KEY.fullmatch(key).groups()
    cur, sym = base.market.currency.code, base.market.currency.symbol
    if info.get("currency") and info["currency"].upper() != cur:
        raise DataPackError(f"the product is priced in {info['currency']}; this server's market uses {cur}")
    live = info.get("live_price") or info.get("list_price")
    if not live:
        raise DataPackError("the product has no price")
    list_price = float(info.get("list_price") or live)
    points = [PrompterPoint(point_id=f"{product_id}-p{i}", text=p["text"], required=bool(p["required"]))
              for i, p in enumerate(info.get("points", []), 1)]
    name, brand = info["product_name"], info["brand"]
    product = Product(product_id=product_id, code=product_id, name=name, short_name=name, eyebrow=brand, tagline="",
                      doc="", volume="", list_price=list_price, live_price=float(live), hero_badge="", aliases=[name],
                      key_facts={}, prompter_points=points, approved_claims=[p.text for p in points],
                      not_approved_claims=[], stt_terms=info.get("stt_terms") or [],
                      brand=brand, category=str(info.get("category") or "").strip())  # D-448
    passages = [Passage(passage_id=f"{product_id}#key-facts#live-price", product_id=product_id, doc="", section="Key facts",
                        text=f"Live broadcast price: {sym}{float(live):.2f}"),
                Passage(passage_id=f"{product_id}#key-facts#list-price", product_id=product_id, doc="", section="Key facts",
                        text=f"List price: {sym}{list_price:.2f}")]
    if points:
        passages.append(Passage(passage_id=f"{product_id}#claims#approved", product_id=product_id, doc="",
                                section="Approved on-air claims",
                                text="Approved claims: " + " ".join(p.text for p in points)))
    runsheet = Runsheet(runsheet_id=key, title=f"{brand} · {name}", brand=brand, language=base.lang,
                        market=base.market.market,
                        items=[RunsheetItem(order=1, product_id=product_id, planned_duration_sec=SEGMENT_SEC,
                                            required_point_ids=[p.point_id for p in points if p.required])],
                        promo_ids=[])
    rules = base.rules.model_copy(update={"rules": [], "pack_ids": [regulation_id], "policy_id": regulation_id})
    return dataclasses.replace(
        base, products=ProductsFile(brand=brand, currency=cur, currency_symbol=sym, set_offers=[], products=[product]),
        runsheets={key: runsheet}, rules=rules, promos=PromosFile(promos=[], rules=base.promos.rules),
        passages=passages, releases={})


def build(settings, base: DataPack, key: str) -> DataPack:
    """The show's pack, read from the onboarding bucket; the regulation PDF is handed to the compliance judge."""
    from ..agents.originals import register_regulation
    from .storage import bucket_for

    if not settings.ONBOARDING_GCS_BUCKET:
        raise DataPackError("ONBOARDING_GCS_BUCKET is not set")
    info, pdfs = load(bucket_for(settings.ONBOARDING_GCS_BUCKET, settings.GCP_PROJECT), key)
    pack = product_pack(base, info, key)
    register_regulation(pack.rules.pack_ids[0], pdfs)
    return pack
