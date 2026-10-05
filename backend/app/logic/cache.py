"""Answer cache and triage cache (DEV_SPEC §8.12). Never cache judgements, fact checks or publish
decisions."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from .grouping import normalise_question

PRICE_INTENTS = frozenset({"price", "set_price", "promo"})


def answer_cache_key(
    product_id: str | None, intent: str, slots: dict[str, str | None], canonical_question: str,
    promo_state: str, doc_version: int,
) -> str:
    slot_part = ",".join(f"{k}={v}" for k, v in sorted(slots.items()) if v is not None)
    raw = "|".join([product_id or "*", intent, slot_part, normalise_question(canonical_question),
                    promo_state, str(doc_version)])
    return hashlib.sha1(raw.encode()).hexdigest()


def normalise_comment(text: str) -> str:
    """Lowercase, trim, collapse spaces. D-211 (full review P3): punctuation and emoji stay, so "nice!" and
    "nice?" (a reaction and a question) or an exclamation before a question never share a triage result."""
    return re.sub(r"\s+", " ", text.lower()).strip()


def triage_cache_key(text: str, context_product_id: str | None, host_line: str | None = None) -> str:
    # D-157: a short comment read with the host's last line is cached for that line only
    tail = f"|{host_line}" if host_line else ""
    return hashlib.sha1(f"{normalise_comment(text)}|{context_product_id}{tail}".encode()).hexdigest()


@dataclass
class CachedAnswer:
    answer_id: str  # verified Answer the entry was made from
    intent: str


@dataclass
class AnswerCache:
    entries: dict[str, CachedAnswer] = field(default_factory=dict)

    def get(self, key: str) -> CachedAnswer | None:
        return self.entries.get(key)

    def put(self, key: str, value: CachedAnswer) -> None:
        self.entries[key] = value

    def invalidate_intents(self, intents: frozenset[str]) -> int:
        stale = [k for k, v in self.entries.items() if v.intent in intents]
        for k in stale:
            del self.entries[k]
        return len(stale)

    def clear(self) -> None:
        self.entries.clear()


@dataclass
class TriageCache:
    entries: dict[str, dict] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0

    def get(self, key: str) -> dict | None:
        value = self.entries.get(key)
        if value is None:
            self.misses += 1
        else:
            self.hits += 1
        return value

    def put(self, key: str, output: dict) -> None:
        self.entries[key] = {**output, "group_candidate_id": None}  # grouping re-runs
