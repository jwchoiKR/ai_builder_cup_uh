"""Law packs from regulator documents (D-229): the uploaded PDFs, kept as they are. D-427 (user): no model reads them
at upload; the live compliance judge reads the originals (D-358). A human approves; the approved pack is versioned
and selected for a release whose category it covers (when the market's shipped pack does not cover it).

Nothing here names a product, brand, market or category: they come from the upload request.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .storage import persisted


class LawPackRecord(BaseModel):
    """D-427: the categories a pack covers, from the upload request. A pack approved before D-427 also holds the
    name, regulator and rules a model read from its files; those fields are ignored."""
    model_config = ConfigDict(extra="ignore")
    covers: list[str]


def save_lawpack(root: Path, market: str, rec: LawPackRecord, job_id: str) -> str:
    folder = root / "lawpacks"
    folder.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{market}|{'|'.join(rec.covers)}".encode()).hexdigest()[:8]
    base = f"law_{market.lower()}_{key}"
    pack_id = f"{base}_v{1 + sum(1 for _ in folder.glob(f'{base}_v*.json'))}"
    (folder / f"{pack_id}.json").write_text(json.dumps(
        {"pack_id": pack_id, "market": market.upper(), "job_id": job_id, "approved_at": int(time.time() * 1000),
         "record": rec.model_dump(mode="json")}, ensure_ascii=False, indent=1), encoding="utf-8")
    persisted(folder / f"{pack_id}.json", create_only=True)  # D-263: approved packs are write-once
    return pack_id


def lawpack_for(root: Path, market: str, category: str) -> tuple[str, LawPackRecord] | None:
    """The newest approved pack of this market that covers the category, or None."""
    folder = root / "lawpacks"
    if not folder.is_dir():
        return None
    norm = lambda c: c.strip().lower().replace(" ", "_").rstrip("s")  # noqa: E731
    best = None
    for p in folder.glob(f"law_{market.lower()}_*_v*.json"):
        data = json.loads(p.read_text(encoding="utf-8"))
        rec = LawPackRecord.model_validate(data["record"])
        if norm(category) in {norm(c) for c in rec.covers} and (best is None or data["approved_at"] > best[0]):
            best = (data["approved_at"], data["pack_id"], rec)
    return (best[1], best[2]) if best else None


def save_brandpack(root: Path, brand: str, rec: LawPackRecord, job_id: str) -> str:
    """D-241: a brand's own rules (guidelines), versioned per brand; they only add restrictions (never remove a law
    rule)."""
    folder = root / "brandpacks"
    folder.mkdir(parents=True, exist_ok=True)
    base = "brand_" + hashlib.sha1(brand.strip().lower().encode()).hexdigest()[:10]
    pack_id = f"{base}_v{1 + sum(1 for _ in folder.glob(f'{base}_v*.json'))}"
    (folder / f"{pack_id}.json").write_text(json.dumps(
        {"pack_id": pack_id, "brand": brand, "job_id": job_id, "approved_at": int(time.time() * 1000),
         "record": rec.model_dump(mode="json")}, ensure_ascii=False, indent=1), encoding="utf-8")
    persisted(folder / f"{pack_id}.json", create_only=True)  # D-263: approved packs are write-once
    return pack_id


def brandpack_for(root: Path, brand: str) -> tuple[str, LawPackRecord] | None:
    """The newest approved brand pack of this brand, or None."""
    folder = root / "brandpacks"
    base = "brand_" + hashlib.sha1(brand.strip().lower().encode()).hexdigest()[:10]
    best = None
    for p in folder.glob(f"{base}_v*.json") if folder.is_dir() else []:
        data = json.loads(p.read_text(encoding="utf-8"))
        if best is None or data["approved_at"] > best[0]:
            best = (data["approved_at"], data["pack_id"], LawPackRecord.model_validate(data["record"]))
    return (best[1], best[2]) if best else None
