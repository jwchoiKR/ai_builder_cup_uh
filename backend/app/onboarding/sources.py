"""Arm FD (FACT_MODE=docs, D-247): a release's original files for the live fact checker.

The model gets the files as onboarding read them (PDF, images and HTML as parts; DOCX, XLSX and CSV as text with
locators). Code gets one "Source file" passage per file, whose text is what code can read of that file (text files,
converted text, PDF text, HTML without tags) plus the record's evidence quotes from it (the only text code has of an
image). A correction that quotes a file is kept only when its quote is in that passage (the usual passage check).
"""
from __future__ import annotations

import functools
import io
import json
import re
from pathlib import Path

from ..models.data import Passage
from .files import model_part
from .storage import ensure

SECTION = "Source file"


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    try:
        pages = PdfReader(io.BytesIO(data)).pages
        return "\n".join(f"[page {i + 1}] {p.extract_text() or ''}" for i, p in enumerate(pages))
    except Exception:  # noqa: BLE001 - an unreadable PDF leaves only the record's quotes
        return ""


def _code_text(part) -> str:
    if part.mime == "application/pdf":
        return _pdf_text(part.data)
    if part.mime == "text/html":
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", part.data.decode("utf-8", "replace")))
    if part.mime == "text/plain":
        return part.data.decode("utf-8", "replace")
    return ""  # images: only the record's quotes


@functools.lru_cache(maxsize=32)
def release_sources(root: str, release_id: str) -> tuple[tuple[tuple[bytes, str], ...], tuple[Passage, ...]]:
    """(model parts, code passages) of a release's files; empty when the release or its files are gone."""
    rel = Path(root) / "releases" / f"{release_id}.json"
    if not rel.is_file():
        return (), ()
    data = json.loads(rel.read_text(encoding="utf-8"))
    folder = Path(root) / data["job_id"]
    index = folder / "files.json"
    if not index.is_file():
        return (), ()
    from .release import product_key
    from .record import ProductRecord

    record = ProductRecord.model_validate(data["record"])
    quotes: dict[str, list[str]] = {}

    def walk(x) -> None:
        if isinstance(x, dict):
            if {"file", "locator", "quote"} <= x.keys():
                quotes.setdefault(x["file"], []).append(f"[{x['locator']}] {x['quote']}")
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(data["record"])
    pid = product_key(record)
    parts: list[tuple[bytes, str]] = []
    passages: list[Passage] = []
    for e in json.loads(index.read_text(encoding="utf-8")):
        path = folder / e["file"]
        if not ensure(path):  # D-263: read back from the bucket after a cold start
            continue
        part = model_part(e["name"], path.read_bytes())
        parts += [(f"FILE {e['name']}".encode(), "text/plain"), (part.data, part.mime)]
        text = "\n".join([_code_text(part), *dict.fromkeys(quotes.get(e["name"], []))])
        passages.append(Passage(passage_id=f"file:{e['name']}", product_id=pid, doc=e["name"], section=SECTION,
                                text=text))
    return tuple(parts), tuple(passages)
