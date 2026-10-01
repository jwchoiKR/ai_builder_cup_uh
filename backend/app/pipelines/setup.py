"""Pre-broadcast setup (DEV_SPEC §7.7, §8.15, §9.2, §12.7): product documents, Brief Agent results,
glossary versions for STT phrase hints, and prompter point overrides for the next session.

All setup state lives in the top-level SETUP store collection:
- `glossary`  confirmed glossary per product and the glossary version (version 0 = default glossary);
- `overrides` prompter points per product that replace products.json points from the next session;
- `uploads`   PDFs uploaded on /setup and the rebuilt local index;
- `brief:<product_id>` the latest Brief Agent result for a product.
"""
from __future__ import annotations

import hashlib
import io
import re
import time
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

from ..agents.brief import BriefAgent, BriefInput
from ..logic.catalog import Catalog
from ..models.data import Passage, PrompterPoint
from ..store.base import SETUP
from .runtime import ActionError

if TYPE_CHECKING:
    from ..context import AppContext

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_POINT_CHARS = 90

# ---- sheet parsing: PDF text -> passages (§9.2) ----------------------------------------------------

SECTION_NAMES = (
    "Product overview", "Key facts", "Key ingredients", "How to use", "In-house test results",
    "Cautions", "Approved on-air claims", "Frequently asked questions",
)
_SECTION = re.compile(r"^[1-8]\.\s+(" + "|".join(re.escape(s) for s in SECTION_NAMES) + r")\s*$")
_CODE = re.compile(r"Product code\s*:?\s*([A-Z]{2}-[A-Z]{2}-\d{2})")
_PAGE_FOOTER = re.compile(r"^Page \d+$")
_AMOUNT = re.compile(r"^\d+(\.\d+)?\s*%")
_STEP_NUMBER = re.compile(r"^\d+$")
TEST_SUFFIX = " (In-house test. Cosmetic effects only.)"


def slugify(text: str, max_chars: int | None = None) -> str:
    """Lowercase, runs of non-alphanumerics -> '-'. The raw text is cut to `max_chars` first."""
    raw = text if max_chars is None else text[:max_chars]
    return re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")


def _strip_glyphs(line: str) -> str:
    """Bullet glyphs come out of PDF text as control or private-use characters ('\\x7f' in the
    shipped sheets) or as bullet symbols; drop them, keep other symbols such as '°'."""
    return "".join(ch for ch in line if unicodedata.category(ch) not in ("Cc", "Co")
                   and ch not in "•▪●◦‣").strip()


def _clean_lines(text: str) -> list[str]:
    out = []
    for ln in text.splitlines():
        s = _strip_glyphs(ln)
        if "Product Information Sheet" in s or _PAGE_FOOTER.match(s):
            continue  # running page header and footer
        out.append(s)
    return out


def _runs(lines: list[str]) -> list[list[str]]:
    """Blocks of non-empty lines separated by empty lines (bullets lose their glyph in PDF text)."""
    runs, cur = [], []
    for ln in lines:
        if ln:
            cur.append(ln)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return runs


def _join(lines: list[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def _pairs(lines: list[str], headers: int) -> list[tuple[str, str]]:
    cells = [ln for ln in lines if ln][headers:]
    return [(cells[i], cells[i + 1]) for i in range(0, len(cells) - 1, 2)]


def _ingredients(lines: list[str]) -> list[tuple[str, str, str]]:
    cells = [ln for ln in lines if ln][3:]  # Ingredient (INCI) | Amount | Purpose in formula
    rows, name, i = [], [], 0
    while i < len(cells):
        if _AMOUNT.match(cells[i]) and name:
            amount = cells[i]
            i += 1
            while amount.count("(") > amount.count(")") and i < len(cells):  # wrapped "50% (formula" / "base)"
                amount = f"{amount} {cells[i]}"
                i += 1
            purpose = [cells[i]] if i < len(cells) else []
            i += 1
            while i < len(cells) and cells[i][:1].islower():  # wrapped purpose
                purpose.append(cells[i])
                i += 1
            rows.append((_join(name), amount, _join(purpose)))
            name = []
        else:
            name.append(cells[i])
            i += 1
    return rows


def _caution_slug(text: str) -> str:
    head = text[:40]
    if ":" in head:
        return slugify(head.split(":", 1)[0])
    return slugify(text, 40)


def parse_sheet_text(text: str, *, doc: str, product_id: str, code: str) -> list[Passage]:
    """Split a product sheet (PDF text) into passages: one per section paragraph, table row,
    caution, claim list and FAQ item. Ids are `CODE#section-slug#item-slug`."""
    sections: dict[str, list[str]] = {}
    current = None
    for ln in _clean_lines(text):
        m = _SECTION.match(ln)
        if m:
            current = m.group(1)
            sections[current] = []
        elif current is not None:
            sections[current].append(ln)
    out: list[Passage] = []

    def add(section: str, item_slug: str, body: str) -> None:
        if body and item_slug:
            pid = f"{code}#{slugify(section)}#{item_slug}"
            if all(p.passage_id != pid for p in out):
                out.append(Passage(passage_id=pid, product_id=product_id, doc=doc, section=section, text=body))

    if lines := sections.get("Product overview"):
        add("Product overview", "overview", _join(lines))
    if lines := sections.get("Key facts"):
        for item, detail in _pairs(lines, headers=2):
            add("Key facts", slugify(item, 60), f"{item}: {detail}")
    if lines := sections.get("Key ingredients"):
        for name, amount, purpose in _ingredients(lines):
            body = f"{name}: {amount}." + (f" {purpose.rstrip('.')}." if purpose else "")
            add("Key ingredients", slugify(name, 60), body)
    if lines := sections.get("How to use"):
        steps: list[tuple[str, list[str]]] = []
        for ln in (x for x in lines if x):
            if _STEP_NUMBER.match(ln):
                steps.append((ln, []))
            elif steps:
                steps[-1][1].append(ln)
        add("How to use", "steps", " ".join(f"{n}. {_join(t)}" for n, t in steps))
    if lines := sections.get("In-house test results"):
        cells = [ln for ln in lines if ln]
        header = next((i for i, c in enumerate(cells) if c == "Measure"), None)
        if header is not None:
            add("In-house test results", "method", _join(cells[:header]))
            rows = cells[header + 2:]
            i = 0
            while i + 1 < len(rows) and not rows[i].endswith("."):
                measure, result = rows[i], rows[i + 1]
                add("In-house test results", slugify(measure, 60), f"{measure}: {result}.{TEST_SUFFIX}")
                i += 2
    if lines := sections.get("Cautions"):
        for run in _runs(lines):
            body = _join(run)
            add("Cautions", _caution_slug(body), body)
    if lines := sections.get("Approved on-air claims"):
        approved, not_approved, mode, cur = [], [], "intro", []

        def flush() -> None:
            if cur and mode != "intro":
                (approved if mode == "approved" else not_approved).append(_join(cur))
            cur.clear()

        for ln in lines:
            if ln.startswith("Claims not approved"):
                flush()
                mode = "not_approved"
            elif ln.startswith("Reference:"):
                break
            elif not ln:
                flush()
                if mode == "intro":
                    mode = "approved"
            else:
                cur.append(ln)
        flush()
        if approved:
            add("Approved on-air claims", "approved", "Approved claims: " + " ".join(approved))
        if not_approved:
            add("Approved on-air claims", "not-approved", "Claims not approved: " + " ".join(not_approved))
    if lines := sections.get("Frequently asked questions"):
        q, a = None, []
        for ln in (x for x in lines if x):
            if ln.endswith("?"):
                if q:
                    add("Frequently asked questions", slugify(q, 60), f"Q: {q} A: {_join(a)}")
                q, a = ln, []
            elif q:
                a.append(ln)
        if q:
            add("Frequently asked questions", slugify(q, 60), f"Q: {q} A: {_join(a)}")
    return out


def pdf_text(data: bytes) -> tuple[str, int]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages), len(reader.pages)


def product_code(text: str) -> str | None:
    m = _CODE.search(text)
    return m.group(1) if m else None


# ---- stored documents ---------------------------------------------------------------------------


class BriefRecord(BaseModel):
    product_id: str
    status: Literal["ok", "timeout", "error", "invalid"]
    output: dict | None = None
    error: str | None = None
    latency_ms: int = 0
    call_id: str | None = None
    ran_at: int


class GlossaryTerm(BaseModel):
    term: str
    kind: Literal["brand", "product", "ingredient", "technical", "value"]
    spoken_forms: list[str] = []
    source_section: str = ""


class GlossaryDoc(BaseModel):
    version: int = 0
    terms_by_product: dict[str, list[GlossaryTerm]] = {}
    confirmed_at: int | None = None


class OverridesDoc(BaseModel):
    points: dict[str, list[PrompterPoint]] = {}
    updated_at: int | None = None


class UploadRecord(BaseModel):
    product_id: str
    name: str
    sha256: str
    path: str
    pages: int
    passages: int
    doc_version: int
    uploaded_at: int


class UploadsDoc(BaseModel):
    uploads: list[UploadRecord] = []


class TermChoice(GlossaryTerm):
    include: bool = True


class PointChoice(BaseModel):
    text: str
    action: Literal["replace", "add"]
    point_id: str | None = None  # the existing point to replace
    source_section: str | None = None


class ConfirmBody(BaseModel):
    glossary: list[TermChoice] = []
    prompter_points: list[PointChoice] = []


class ConfirmAllBody(BaseModel):
    products: dict[str, ConfirmBody] = Field(default_factory=dict)


# ---- helpers ------------------------------------------------------------------------------------


def _now(ctx: "AppContext") -> int:
    return ctx.clock.now_ms()


def _catalog(ctx: "AppContext") -> Catalog:
    return Catalog(ctx.pack)


def _product_or_404(ctx: "AppContext", product_id: str):
    cat = _catalog(ctx)
    if not cat.is_product(product_id):
        raise ActionError(404, "unknown_product", f"product {product_id} not found")
    return cat.get_product(product_id)


def _uploads_dir(ctx: "AppContext") -> Path:
    return ctx.settings.data_path / "uploads"


@lru_cache(maxsize=64)
def _pdf_info(path: str, mtime: float) -> tuple[str, int]:
    data = Path(path).read_bytes()
    try:
        _, pages = pdf_text(data)
    except Exception:  # noqa: BLE001 - an unreadable file still gets listed
        pages = 0
    return hashlib.sha256(data).hexdigest(), pages


def _info(path: Path) -> tuple[str, int]:
    return _pdf_info(str(path), path.stat().st_mtime)


async def _get(ctx: "AppContext", doc_id: str, model):
    return await ctx.store.get(SETUP, doc_id, model) or model()


# ---- documents (§12.7 step 1) -------------------------------------------------------------------


async def list_documents(ctx: "AppContext") -> dict[str, Any]:
    cat = _catalog(ctx)
    by_doc = {p.doc: p.product_id for p in cat.products}
    status = "Imported to Vertex AI Search" if ctx.settings.RETRIEVER == "vertex_search" else "Indexed locally"
    docs = []
    for path in sorted((ctx.settings.data_path / "products").glob("*.pdf")):
        sha, pages = _info(path)
        docs.append({"name": path.name, "product_id": by_doc.get(path.name), "pages": pages, "sha256": sha,
                     "size": path.stat().st_size, "source": "shipped", "status": status})
    uploads = await _get(ctx, "uploads", UploadsDoc)
    for u in uploads.uploads:
        docs.append({"name": u.name, "product_id": u.product_id, "pages": u.pages, "sha256": u.sha256,
                     "size": Path(u.path).stat().st_size if Path(u.path).is_file() else None, "source": "upload",
                     "status": f"Indexed locally · {u.passages} passages", "uploaded_at": u.uploaded_at})
    return {"documents": docs, "doc_version": ctx.retriever.doc_version()}


async def upload_document(ctx: "AppContext", filename: str, data: bytes) -> dict[str, Any]:
    """§12.7: a shipped PDF (same SHA-256) is already indexed; any other sheet is saved and its
    product's local index is rebuilt (doc_version + 1). The shipped passages.jsonl never changes."""
    name = Path(filename or "upload.pdf").name
    if not name.lower().endswith(".pdf") or not data.startswith(b"%PDF"):
        raise ActionError(400, "not_a_pdf", "Upload a PDF product sheet.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ActionError(413, "too_large", "The PDF is larger than 20 MB.")
    sha = hashlib.sha256(data).hexdigest()
    for path in (ctx.settings.data_path / "products").glob("*.pdf"):
        if _info(path)[0] == sha:
            return {"status": "already_indexed", "message": "Already indexed", "name": path.name}
    uploads = await _get(ctx, "uploads", UploadsDoc)
    if any(u.sha256 == sha for u in uploads.uploads):
        return {"status": "already_indexed", "message": "Already indexed", "name": name}
    try:
        text, pages = pdf_text(data)
    except Exception as e:  # noqa: BLE001
        raise ActionError(422, "unreadable_pdf", f"The PDF could not be read: {e}") from None
    code = product_code(text)
    product = next((p for p in _catalog(ctx).products if p.code == code), None)
    if product is None:
        raise ActionError(422, "unknown_product_code", f"No product with code {code or '(none found)'}.")
    passages = parse_sheet_text(text, doc=name, product_id=product.product_id, code=product.code)
    if not passages:
        raise ActionError(422, "no_sections", "No product sheet sections were found in the PDF.")
    if ctx.settings.APP_ENV == "cloud":
        return {"status": "manual_import", "message": (
            f"Upload {name} to gs://{ctx.settings.GCS_BUCKET}/products/ and run the Vertex AI Search import "
            "(cloud import is manual in v1)."), "product_id": product.product_id}
    folder = _uploads_dir(ctx)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(data)
    replace = getattr(ctx.retriever, "replace_product", None)
    if replace is None:
        raise ActionError(501, "rebuild_unsupported", "This retriever cannot rebuild its index.")
    doc_version = replace(product.product_id, passages)
    uploads.uploads = [u for u in uploads.uploads if u.product_id != product.product_id] + [UploadRecord(
        product_id=product.product_id, name=name, sha256=sha, path=str(path), pages=pages, passages=len(passages),
        doc_version=doc_version, uploaded_at=_now(ctx))]
    await ctx.store.put(SETUP, "uploads", uploads)
    return {"status": "indexed", "message": f"Indexed locally · {len(passages)} passages", "name": name,
            "product_id": product.product_id, "passages": len(passages), "doc_version": doc_version}


async def document_text(ctx: "AppContext", product_id: str) -> str:
    """Brief Agent input (§7.7): an uploaded sheet's PDF text, else the shipped Markdown sheet locally
    or the shipped PDF text in cloud mode."""
    product = _product_or_404(ctx, product_id)
    uploads = await _get(ctx, "uploads", UploadsDoc)
    up = next((u for u in uploads.uploads if u.product_id == product_id and Path(u.path).is_file()), None)
    if up is not None:
        return pdf_text(Path(up.path).read_bytes())[0]
    pdf = ctx.settings.data_path / "products" / product.doc
    md = pdf.with_suffix(".md")
    if ctx.settings.APP_ENV != "cloud" and md.is_file():
        return md.read_text(encoding="utf-8")
    return pdf_text(pdf.read_bytes())[0]


# ---- Brief Agent (§12.7 step 2) -------------------------------------------------------------------


async def run_brief(ctx: "AppContext", product_id: str) -> BriefRecord:
    _product_or_404(ctx, product_id)
    text = await document_text(ctx, product_id)
    agent = BriefAgent(ctx.llm, ctx.prompts["brief_agent"], ctx.reflex)
    t0 = time.perf_counter()
    res = await agent.run(BriefInput(product_id=product_id, document_text=text),
                          deadline_ms=ctx.settings.BRIEF_TIMEOUT_MS)
    record = BriefRecord(product_id=product_id, status=res.status,
                         output=res.output.model_dump(mode="json") if res.output else None, error=res.error,
                         latency_ms=round((time.perf_counter() - t0) * 1000), call_id=res.call_id, ran_at=_now(ctx))
    if res.status == "ok":
        await ctx.store.put(SETUP, f"brief:{product_id}", record)
        return record
    # §7.2: show the error, keep the previous result and glossary
    raise ActionError(502, f"brief_{res.status}", f"Brief Agent {res.status}: {res.error or 'no result'}")


async def get_brief(ctx: "AppContext", product_id: str) -> BriefRecord | None:
    _product_or_404(ctx, product_id)
    return await ctx.store.get(SETUP, f"brief:{product_id}", BriefRecord)


# ---- glossary and prompter overrides (§8.15, §12.7 step 3) -------------------------------------


def _ingredient_term(key: str) -> str:
    return " ".join(w.upper() if len(w) <= 2 else w.capitalize() for w in key.split("_"))


def default_terms(ctx: "AppContext") -> tuple[GlossaryTerm, dict[str, list[GlossaryTerm]]]:
    """§8.15 default glossary: brand, product names and every ingredient in products.json key facts."""
    cat = _catalog(ctx)
    brand = GlossaryTerm(term=cat.brand, kind="brand", spoken_forms=[cat.brand.lower()], source_section="products.json")
    per: dict[str, list[GlossaryTerm]] = {}
    for p in cat.products:
        terms = [GlossaryTerm(term=p.name, kind="product", spoken_forms=[p.name.lower(), p.short_name],
                              source_section="products.json")]
        for key, value in p.key_facts.items():
            if value.strip().endswith("%"):  # ingredient amounts, e.g. "panthenol": "5%"
                name = _ingredient_term(key)
                terms.append(GlossaryTerm(term=name, kind="ingredient", spoken_forms=[name.lower()],
                                          source_section="products.json key facts"))
        per[p.product_id] = terms
    return brand, per


async def current_glossary(ctx: "AppContext") -> dict[str, Any]:
    """The glossary used for STT phrase hints at the next audio stream start (§8.15, §10.3):
    confirmed terms per product, default terms for products not confirmed yet."""
    doc = await _get(ctx, "glossary", GlossaryDoc)
    brand, defaults = default_terms(ctx)
    terms: list[GlossaryTerm] = []
    seen: set[str] = set()
    for t in [brand] + [t for pid in defaults for t in doc.terms_by_product.get(pid, defaults[pid])]:
        if t.term.lower() not in seen:
            seen.add(t.term.lower())
            terms.append(t)
    return {"version": doc.version, "terms": [t.model_dump() for t in terms], "confirmed_at": doc.confirmed_at,
            "confirmed_products": sorted(doc.terms_by_product)}


async def prompter_overrides(ctx: "AppContext") -> dict[str, list[PrompterPoint]]:
    """Accepted prompter point changes per product; they apply from the next session (§12.7)."""
    return dict((await _get(ctx, "overrides", OverridesDoc)).points)


async def current_points(ctx: "AppContext") -> dict[str, list[PrompterPoint]]:
    overrides = await prompter_overrides(ctx)
    return {p.product_id: overrides.get(p.product_id) or list(p.prompter_points) for p in _catalog(ctx).products}


def _apply_points(ctx: "AppContext", product_id: str, base: list[PrompterPoint], choices: list[PointChoice]) -> list[PrompterPoint]:
    points = [pt.model_copy() for pt in base]
    prefix = (points[0].point_id.split("-")[0] if points else product_id[:2])
    for c in choices:
        text = c.text.strip()
        if not text or len(text) > MAX_POINT_CHARS:
            raise ActionError(400, "invalid_point", f"A prompter point must have 1 to {MAX_POINT_CHARS} characters.")
        hit = ctx.reflex.first_hit(text)
        if hit is not None:
            raise ActionError(409, "restricted_phrase", f"The point contains a restricted phrase: '{hit.phrase}'.")
        if c.action == "replace":
            target = next((pt for pt in points if pt.point_id == c.point_id), None)
            if target is None:
                raise ActionError(404, "unknown_point", f"point {c.point_id} not found for {product_id}")
            target.text = text  # keeps the id and its required flag
        else:
            n = 1 + sum(1 for pt in points if pt.point_id.startswith(f"{prefix}-x"))
            points.append(PrompterPoint(point_id=f"{prefix}-x{n}", text=text, required=False))
    return points


async def confirm(ctx: "AppContext", products: dict[str, ConfirmBody]) -> dict[str, Any]:
    """One confirmation = glossary version + 1, whatever number of products it covers."""
    if not products:
        raise ActionError(400, "nothing_to_confirm", "Run the Brief Agent and select terms first.")
    for pid in products:
        _product_or_404(ctx, pid)
    base_points = await current_points(ctx)
    async with ctx.store.transaction() as txn:
        doc = await txn.get(SETUP, "glossary", GlossaryDoc) or GlossaryDoc()
        overrides = await txn.get(SETUP, "overrides", OverridesDoc) or OverridesDoc()
        for pid, body in products.items():
            doc.terms_by_product[pid] = [GlossaryTerm(**t.model_dump(exclude={"include"})) for t in body.glossary if t.include]
            if body.prompter_points:
                overrides.points[pid] = _apply_points(ctx, pid, base_points[pid], body.prompter_points)
        doc.version += 1
        doc.confirmed_at = _now(ctx)
        overrides.updated_at = doc.confirmed_at
        txn.put(SETUP, "glossary", doc)
        txn.put(SETUP, "overrides", overrides)
    return await current_glossary(ctx)
