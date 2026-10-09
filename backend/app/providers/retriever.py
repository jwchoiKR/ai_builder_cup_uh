"""Retriever interface and the local BM25 implementation (DEV_SPEC §9).

VertexSearchRetriever: the evidence of viewer-question answers (ANSWER_RETRIEVER=vertex_search).
"""
from __future__ import annotations

import logging
import re
from collections.abc import Sequence
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


class VertexSearchRetriever:
    """Chunks from a Vertex AI Search app (its data store reads the product documents from GCS). No metadata
    filter: the caller puts the product name in the query, and the chunk is tagged with the asked product."""
    name = "vertex_search"

    def __init__(self, project: str, location: str, engine_id: str) -> None:
        from google.cloud import discoveryengine_v1 as de

        self._de = de
        endpoint = None if location == "global" else f"{location}-discoveryengine.googleapis.com"
        self._options = {"api_endpoint": endpoint} if endpoint else None
        self._client = None  # made on the first search: a grpc aio client belongs to the loop it was made in
        self._serving = (f"projects/{project}/locations/{location}/collections/default_collection"
                         f"/engines/{engine_id}/servingConfigs/default_serving_config")
        self._seen: dict[str, Passage] = {}  # ponytail: grows per process; an LRU if shows run for days

    async def search(self, query: str, *, product_filter: str | None, top_k: int, timeout_ms: int) -> list[Passage]:
        R = self._de.SearchRequest
        req = R(serving_config=self._serving, query=query, page_size=top_k,
                content_search_spec=R.ContentSearchSpec(search_result_mode=R.ContentSearchSpec.SearchResultMode.CHUNKS))
        try:
            if self._client is None:
                self._client = self._de.SearchServiceAsyncClient(client_options=self._options)
            pager = await self._client.search(req, timeout=timeout_ms / 1000)
        except Exception as e:  # noqa: BLE001 - no evidence: the composer finds nothing and a person answers
            log.warning("vertex search failed for %r: %s", query[:80], e)
            return []
        out = []
        for r in list(pager.results)[:top_k]:
            ch = r.chunk
            if not ch.content:
                continue
            p = Passage(passage_id="vx:" + ch.name.split("/documents/")[-1], product_id=product_filter or "",
                        doc=ch.document_metadata.title or ch.document_metadata.uri, section="Vertex AI Search",
                        text=ch.content, score=ch.relevance_score or 0)
            self._seen[p.passage_id] = p
            out.append(p)
        return out

    async def prefetch(self, product_id: str) -> list[Passage]:
        return []

    def doc_version(self) -> int:
        return 0  # ponytail: streaming updates of the data store do not clear cached answers; a version if they must

    def get(self, passage_id: str) -> Passage | None:
        return self._seen.get(passage_id)
