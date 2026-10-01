"""Retriever interface and the local BM25 implementation (DEV_SPEC §9).

The Vertex AI Search adapter arrives in phase P6 behind the same interface.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Protocol

from rank_bm25 import BM25Okapi

from ..models.data import Passage

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
        self._passages = list(passages)
        self._by_id = {p.passage_id: p for p in self._passages}
        self._doc_version = doc_version
        self._index: dict[str | None, tuple[list[Passage], BM25Okapi]] = {}
        groups: dict[str | None, list[Passage]] = {None: self._passages}
        for p in self._passages:
            groups.setdefault(p.product_id, []).append(p)
        for key, ps in groups.items():
            # Filter by product before scoring: one index per product.
            self._index[key] = (ps, BM25Okapi([tokenize(p.text) for p in ps]))

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
