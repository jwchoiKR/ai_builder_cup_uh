"""Retriever interface and the local BM25 implementation (DEV_SPEC §9).

The evidence of viewer-question answers (ANSWER_RETRIEVER=vertex_search): ProductDocumentRetriever hands over the
asked product's whole document when it is short, and VertexSearchRetriever picks passages when it is not.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import re
from collections.abc import Callable, Sequence
from typing import Protocol

from rank_bm25 import BM25Okapi

from ..models.data import Passage

log = logging.getLogger(__name__)

PREFETCH_SECTIONS = ("Key facts", "Key ingredients", "How to use", "Cautions", "In-house test results")
_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?%?")


def tokenize(text: str) -> list[str]:
    """Lowercase words and numbers; `%` stays attached ("4%")."""
    return _TOKEN.findall(text.lower())


class Retriever(Protocol):
    name: str

    async def search(self, query: str, *, product_filter: str | None, top_k: int, timeout_ms: int) -> list[Passage]: ...
    async def prefetch(self, product_id: str) -> list[Passage]: ...
    def doc_version(self) -> int: ...
    def get(self, passage_id: str) -> Passage | None: ...


class LocalRetriever:
    name = "local"

    def __init__(self, passages: Sequence[Passage], doc_version: int = 0) -> None:
        self._doc_version = doc_version
        self._build(passages)

    def _build(self, passages: Sequence[Passage]) -> None:
        self._passages = list(passages)
        self._by_id = {p.passage_id: p for p in self._passages}
        self._index: dict[str | None, tuple[list[Passage], BM25Okapi]] = {}
        groups: dict[str | None, list[Passage]] = {None: self._passages}
        for p in self._passages:
            groups.setdefault(p.product_id, []).append(p)
        for key, ps in groups.items():
            # Filter by product before scoring: one index per product. D-278: no passages (a clean base before any
            # release) is no index, not a BM25 over nothing
            if ps:
                self._index[key] = (ps, BM25Okapi([tokenize(p.text) for p in ps]))

    def replace_product(self, product_id: str, passages: Sequence[Passage]) -> int:
        """Swap one product's passages (a rebuilt sheet from /setup) and bump doc_version (§12.7).
        The shipped passages.jsonl on disk is never modified."""
        others = [p for p in self._passages if p.product_id != product_id]
        self._build(others + [p for p in passages if p.product_id == product_id])
        self._doc_version += 1
        return self._doc_version

    def passages_of(self, product_id: str) -> list[Passage]:
        return [p for p in self._passages if p.product_id == product_id]

    async def search(self, query: str, *, product_filter: str | None, top_k: int, timeout_ms: int) -> list[Passage]:
        if product_filter not in self._index:
            return []
        ps, bm25 = self._index[product_filter]
        tokens = tokenize(query)
        if not tokens:
            return []
        scores = bm25.get_scores(tokens)
        ranked = sorted(zip(scores, range(len(ps))), key=lambda t: (-t[0], t[1]))
        return [ps[i].model_copy(update={"score": float(s)}) for s, i in ranked[:top_k] if s > 0]

    async def prefetch(self, product_id: str) -> list[Passage]:
        return [p for p in self._passages if p.product_id == product_id and p.section in PREFETCH_SECTIONS]

    def doc_version(self) -> int:
        return self._doc_version

    def get(self, passage_id: str) -> Passage | None:
        return self._by_id.get(passage_id)

    def sections(self, product_id: str, sections: Sequence[str]) -> list[Passage]:
        return [p for p in self._passages if p.product_id == product_id and p.section in sections]


SEGMENTS_PER_DOC = 10  # the API's most
SEARCH_PAGE_SIZE = 50  # documents per search: the asked product's file is picked out of them by its folder


def product_segments(results: Sequence[dict], product_filter: str | None, top_k: int) -> list[Passage]:
    """The asked product's passages out of a search's results (`derived_struct_data` of each document, as a dict).

    The data store has no field to filter on, so the product is told by the file's place: an approved product's PDF
    is stored under `<product_id>/` in the search bucket (api/products.py), whatever the product is. The `top_k`
    best segments are kept and returned in document order (file, page), so the same question shows the composer the
    same text in the same order. A passage's id is its product, page and text, so it is the same id every time."""
    found: list[tuple[float, str, int, Passage]] = []
    for doc in results:
        link = str(doc.get("link") or "")
        folder = link.rsplit("/", 2)[-2] if link.count("/") >= 3 else ""
        if product_filter is not None and folder != product_filter:
            continue
        name = link.rsplit("/", 1)[-1]
        for seg in doc.get("extractive_segments") or []:
            text = " ".join(str(seg.get("content") or "").split())
            if not text:
                continue
            number = str(seg.get("pageNumber") or "")
            page = int(number) if number.isdigit() else 0
            pid = product_filter or folder
            passage = Passage(passage_id=f"vx:{pid}:p{page}:{hashlib.sha1(text.encode()).hexdigest()[:10]}",
                              product_id=pid, doc=name, section=f"Product document, page {page}" if page else
                              "Product document", text=text, score=float(seg.get("relevanceScore") or 0.0))
            found.append((-passage.score, name, page, passage))
    best = sorted(found, key=lambda t: (t[0], t[1], t[2], t[3].passage_id))[:top_k]
    return [p for _, _, _, p in sorted(best, key=lambda t: (t[1], t[2], t[3].passage_id))]


class VertexSearchRetriever:
    """The evidence of viewer-question answers, from the Vertex AI Search app, in one of two ways (`evidence`):

    - "segments" (the default): the search results' own text. The asked product's passages, word for word from its
      document, are the evidence, and the composer writes the reply from them. The same query returns the same
      passages, so nothing between the question and the composer is written by a model.
    - "answer": the app's own written answer (answer_query: search + answer with citations, like the console
      Preview) is the one evidence passage. A model writes it anew on every call, without a seed, from every
      product's documents (no metadata filter: the caller puts the product name in the query, and the passage is
      tagged with the asked product)."""
    name = "vertex_search"

    def __init__(self, project: str, location: str, engine_id: str, timeout_ms: int, evidence: str = "segments",
                 search_timeout_ms: int = 3000) -> None:
        from google.cloud import discoveryengine_v1 as de

        self._de = de
        endpoint = None if location == "global" else f"{location}-discoveryengine.googleapis.com"
        self._options = {"api_endpoint": endpoint} if endpoint else None
        self._client = None  # made on the first search: a grpc aio client belongs to the loop it was made in
        self._search_client = None
        self._serving = (f"projects/{project}/locations/{location}/collections/default_collection"
                         f"/engines/{engine_id}/servingConfigs/default_serving_config")
        self._timeout_ms = timeout_ms  # the caller's search budget is too short for a written answer
        self._evidence, self._search_timeout_ms = evidence, search_timeout_ms
        self._seen: dict[str, Passage] = {}  # ponytail: grows per process; an LRU if shows run for days

    async def _segments(self, query: str, product_filter: str | None, top_k: int) -> list[Passage]:
        S = self._de.SearchRequest
        req = S(
            serving_config=self._serving, query=query, page_size=SEARCH_PAGE_SIZE,
            content_search_spec=S.ContentSearchSpec(extractive_content_spec=S.ContentSearchSpec.ExtractiveContentSpec(
                max_extractive_segment_count=SEGMENTS_PER_DOC, return_extractive_segment_score=True)),
            # the default threshold drops a document that answers "no" to the question (CLAUDE.md, quirks)
            relevance_threshold=S.RelevanceThreshold.LOWEST,
        )
        try:
            if self._search_client is None:
                self._search_client = self._de.SearchServiceAsyncClient(client_options=self._options)
            page = (await self._search_client.search(req, timeout=self._search_timeout_ms / 1000)).pages
            first = await anext(aiter(page))  # one page: SEARCH_PAGE_SIZE documents
            to_dict = self._de.SearchResponse.SearchResult.to_dict
            docs = [to_dict(r)["document"].get("derived_struct_data") or {} for r in first.results]
        except Exception as e:  # noqa: BLE001 - no evidence: the composer finds nothing and a person answers
            log.warning("vertex search failed for %r: %s", query[:80], e)
            return []
        passages = product_segments(docs, product_filter, top_k)
        log.info("vertex search for %r: %d documents, %d passages of %s", query[:80], len(docs), len(passages),
                 product_filter or "any product")
        for p in passages:
            self._seen[p.passage_id] = p
        return passages

    async def search(self, query: str, *, product_filter: str | None, top_k: int, timeout_ms: int) -> list[Passage]:
        if self._evidence == "segments":
            return await self._segments(query, product_filter, top_k)
        R = self._de.AnswerQueryRequest
        req = R(
            serving_config=self._serving,
            query=self._de.Query(text=query),
            query_understanding_spec=R.QueryUnderstandingSpec(
                query_rephraser_spec=R.QueryUnderstandingSpec.QueryRephraserSpec(disable=False, max_rephrase_steps=1)),
            search_spec=R.SearchSpec(search_params=R.SearchSpec.SearchParams(max_return_results=10)),
            answer_generation_spec=R.AnswerGenerationSpec(
                model_spec=R.AnswerGenerationSpec.ModelSpec(model_version="stable"), include_citations=True,
                answer_language_code="en", ignore_non_answer_seeking_query=False),
        )
        try:
            if self._client is None:
                self._client = self._de.ConversationalSearchServiceAsyncClient(client_options=self._options)
            answer = (await self._client.answer_query(req, timeout=self._timeout_ms / 1000)).answer
        except Exception as e:  # noqa: BLE001 - no evidence: the composer finds nothing and a person answers
            log.warning("vertex answer failed for %r: %s", query[:80], e)
            return []
        if answer.answer_skipped_reasons or not answer.answer_text.strip():
            log.info("vertex answer skipped for %r: %s", query[:80], list(answer.answer_skipped_reasons))
            return []
        # answer.name comes back empty: the id is the text's hash, so the same answer keeps one id
        p = Passage(passage_id="vx:" + hashlib.sha1(answer.answer_text.encode()).hexdigest()[:16],
                    product_id=product_filter or "",
                    doc="Vertex AI Search answer", section="Vertex AI Search", text=answer.answer_text, score=1.0)
        self._seen[p.passage_id] = p
        return [p]

    async def prefetch(self, product_id: str) -> list[Passage]:
        return []

    def doc_version(self) -> int:
        return 0  # ponytail: streaming updates of the data store do not clear cached answers; a version if they must

    def get(self, passage_id: str) -> Passage | None:
        return self._seen.get(passage_id)


def document_pages(product_id: str, files: Sequence[tuple[str, bytes]]) -> list[Passage]:
    """A product's PDFs as one passage per page with text, in file and page order. A page's id is its product, page
    and text, so it is the same id on every read."""
    from pypdf import PdfReader

    out: list[Passage] = []
    for name, data in sorted(files):
        for n, page in enumerate(PdfReader(io.BytesIO(data)).pages, 1):
            text = " ".join((page.extract_text() or "").split())
            if text:
                out.append(Passage(passage_id=f"doc:{product_id}:p{n}:{hashlib.sha1(text.encode()).hexdigest()[:10]}",
                                   product_id=product_id, doc=name, section=f"Product document, page {n}", text=text,
                                   score=1.0))
    return out


class ProductDocumentRetriever:
    """The asked product's own PDF next to the search (`search`), in one of two orders (`first`):

    - "search" (VERTEX_EVIDENCE=segments, the default): the search's passages are the evidence. When the search
      fails or returns nothing for the product (a 429, a timeout, a file the data store has not indexed yet, a file
      outside the documents one search returns), the product's document is read from the onboarding bucket instead,
      so a search that is down does not leave a question without evidence.
    - "document" (VERTEX_EVIDENCE=document): the document first, the search only when it is too long.

    The document is handed over whole, every page in order, when it has at most `max_chars` characters: then the
    evidence is the same whatever the wording of the question. A longer one is not handed over (no evidence)."""
    name = "product_document"

    def __init__(self, load: Callable[[str], list[tuple[str, bytes]]], search: Retriever | None,
                 max_chars: int, first: str = "search") -> None:
        self._load, self._fallback, self._max_chars, self._first = load, search, max_chars, first
        self._pages: dict[str, list[Passage]] = {}  # an uploaded product's file never changes (write-once)
        self._by_id: dict[str, Passage] = {}

    async def _document(self, product_id: str) -> list[Passage]:
        if product_id not in self._pages:
            try:
                pages = document_pages(product_id, await asyncio.to_thread(self._load, product_id))
            except Exception as e:  # noqa: BLE001 - an unreadable file: the search decides, this time
                log.warning("product document of %s not read: %s", product_id, e)
                return []
            self._pages[product_id] = pages
            self._by_id.update({p.passage_id: p for p in pages})
        return self._pages[product_id]

    async def _whole(self, product_id: str | None) -> list[Passage]:
        pages = await self._document(product_id) if product_id else []
        return list(pages) if pages and sum(len(p.text) for p in pages) <= self._max_chars else []

    async def _searched(self, query: str, product_filter: str | None, top_k: int, timeout_ms: int) -> list[Passage]:
        if self._fallback is None:
            return []
        return await self._fallback.search(query, product_filter=product_filter, top_k=top_k, timeout_ms=timeout_ms)

    async def search(self, query: str, *, product_filter: str | None, top_k: int, timeout_ms: int) -> list[Passage]:
        if self._first == "document":
            return await self._whole(product_filter) or await self._searched(query, product_filter, top_k, timeout_ms)
        found = await self._searched(query, product_filter, top_k, timeout_ms)
        if found:
            return found
        pages = await self._whole(product_filter)
        if pages:
            log.warning("no search result for %s: its own document is the evidence (%d pages)", product_filter,
                        len(pages))
        return pages

    async def prefetch(self, product_id: str) -> list[Passage]:
        return []

    def doc_version(self) -> int:
        return 0

    def get(self, passage_id: str) -> Passage | None:
        return self._by_id.get(passage_id) or (self._fallback.get(passage_id) if self._fallback else None)
