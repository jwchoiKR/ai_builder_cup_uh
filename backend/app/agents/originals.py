"""D-358: the regulation ORIGINALS the live compliance judge reads, as they are (no rule JSON).

A show's regulation PDFs are the ones uploaded with its products (rebuilt onboarding: each release pairs a product
with a regulation file). The model gets the files as parts of its cached prefix; code keeps each file's text only to
check that a cited quote is really in that original (provenance)."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path




@dataclass(frozen=True)
class Original:
    name: str  # the document name the model cites ("asean_cosmetic_claims_guideline_appendix_iii_2007.pdf")
    title: str
    source_id: str
    data: bytes
    mime: str
    text: str  # what code can read of it, for the quote check


def squash(text: str) -> str:
    """Letters and digits only (any script), lower case: PDF text extraction splits and joins words ("pro ducts").
    D-361: Korean, Chinese, Malay or Thai text keeps its letters (it was Latin only)."""
    return "".join(ch for ch in unicodedata.normalize("NFKC", text).casefold() if ch.isalnum())


def _slug(text: str) -> str:
    return re.sub(r"[^0-9a-z]+", "-", text.casefold()).strip("-")


def citation_rule_id(doc: str, section: str) -> str:
    """The alert's rule id for a citation: the document's stem and the section, normalised ("asean-...-2007#3-b")."""
    return f"{_slug(Path(doc).stem)}#{_slug(section)}"


def cited_title(d: "Original | None", doc: str, section: str) -> str:
    """D-433: the host's words for a citation: the document's title (a market source's), else its file name without
    the extension, then the section as the model wrote it ("kelmar_code 2.1"); never the rule-id slug."""
    if d is not None and d.title and d.title not in (d.name, d.name.split(":", 1)[-1]):
        name = d.title
    else:
        name = Path((d.name.split(":", 1)[-1] if d is not None else doc).strip()).stem
    return f"{name} {section.strip()}".strip()


def _text(name: str, data: bytes) -> str:
    """What code can read of a PDF, for the quote check."""
    import io

    from pypdf import PdfReader

    try:
        return "\n".join(f"[page {i + 1}] {p.extract_text() or ''}" for i, p in enumerate(PdfReader(io.BytesIO(data)).pages))
    except Exception:  # noqa: BLE001 - an unreadable PDF leaves no text to check quotes against
        return ""


# a show's uploaded regulation PDFs by regulation id (onboarding/product_show.py registers them at show start)
_REGULATIONS: dict[str, list[Original]] = {}  # ponytail: one entry per regulation for the process's life


def register_regulation(regulation_id: str, pdfs: list[tuple[str, bytes]]) -> None:
    _REGULATIONS[regulation_id] = [Original(name, name, regulation_id, data, "application/pdf", _text(name, data))
                                   for name, data in pdfs]


def originals_for(catalog, product_ids) -> tuple[tuple[Original, ...], tuple[str, ...]]:
    """The regulation PDFs of these products, and the regulation ids that have none. In a multi-product show a
    regulation belongs to the products whose release has it. D-361: two regulations may each have a file of the same
    name; both are kept, the later one named "<regulation id>:<name>"."""
    owners, ids = catalog.pack.rule_products, set(product_ids)
    found, missing = [], []
    for sid in sorted(k for k in catalog.pack.rules.pack_ids if owners is None or owners.get(k, frozenset()) & ids):
        docs = _REGULATIONS.get(sid)
        if not docs:
            missing.append(sid)
            continue
        names = {x.name for x in found}
        found += [d if d.name not in names else Original(f"{sid}:{d.name}", d.title, d.source_id, d.data, d.mime, d.text)
                  for d in docs]
    return tuple(found), tuple(missing)
