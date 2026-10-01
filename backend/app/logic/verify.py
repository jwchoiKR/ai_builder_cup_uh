"""Answer verification (DEV_SPEC §8.9.4). An answer is published automatically only if all rules pass."""
from __future__ import annotations

import re
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation

from ..models.agent_io import ComposerOutput
from ..models.data import Passage
from .reflex import Reflex

MAX_ANSWER_CHARS = 240
MAX_SENTENCES = 2
SET_PRICE_SUFFIX = "#key-facts#live-set-price"

# A sentence ends at . ! ? followed by whitespace or the end of the text; "S$36.00" is one token.
_SENTENCE_END = re.compile(r"[.!?]+(?=\s|$)")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def split_sentences(text: str) -> list[str]:
    parts, start = [], 0
    for m in _SENTENCE_END.finditer(text):
        parts.append(text[start:m.end()].strip())
        start = m.end()
    parts.append(text[start:].strip())
    return [p for p in parts if p]


def _ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def quote_in_passage(quote: str, passage_text: str) -> bool:
    q = _ws(quote)
    return bool(q) and q in _ws(passage_text)


def number_set(text: str) -> set[str]:
    """Numbers normalised so S$36 = S$36.00 = 36 and 32.40 = 32.4."""
    out = set()
    for raw in _NUMBER.findall(text):
        try:
            d = Decimal(raw).normalize()
        except InvalidOperation:
            continue
        out.add(format(d, "f"))
    return out


def is_promo_passage(passage_id: str) -> bool:
    return passage_id.startswith("PROMO#")


def verify_answer(
    output: ComposerOutput,
    passages: Sequence[Passage],
    product_id: str | None,
    *,
    multi: bool,
    reflex: Reflex,
    not_approved_claims: Sequence[str],
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    answer = output.answer.strip()
    by_id = {p.passage_id: p for p in passages}

    # 1. grounded, non-empty, short
    if not output.grounded:
        errors.append("not grounded")
    if not answer:
        errors.append("empty answer")
    if len(answer) > MAX_ANSWER_CHARS:
        errors.append(f"longer than {MAX_ANSWER_CHARS} characters")
    if len(split_sentences(answer)) > MAX_SENTENCES:
        errors.append(f"more than {MAX_SENTENCES} sentences")

    # 2. citations exist and quote their passages
    if not output.citations:
        errors.append("no citation")
    cited: list[Passage] = []
    for c in output.citations:
        p = by_id.get(c.passage_id)
        if p is None:
            errors.append(f"unknown passage {c.passage_id}")
            continue
        if not quote_in_passage(c.quote, p.text):
            errors.append(f"quote not found in {c.passage_id}")
            continue
        cited.append(p)

    # 3. cited passages belong to the product (or promo / set-price passages)
    if not multi:
        for p in cited:
            if not (p.product_id == product_id or is_promo_passage(p.passage_id)
                    or p.passage_id.endswith(SET_PRICE_SUFFIX)):
                errors.append(f"passage {p.passage_id} is about another product")

    # 4. every number in the answer appears in a cited quote
    quoted_numbers: set[str] = set()
    for c in output.citations:
        if c.passage_id in by_id:
            quoted_numbers |= number_set(c.quote)
    for n in sorted(number_set(answer) - quoted_numbers):
        errors.append(f"number {n} not in a cited quote")

    # 5. no restricted wording, even negated
    hits = reflex.scan(answer)
    if hits:
        errors.append(f"restricted phrase '{hits[0].phrase}' ({hits[0].rule_id})")
    low = _ws(answer)
    for claim in not_approved_claims:
        phrase = _ws(claim).rstrip(".")
        if phrase and phrase in low:
            errors.append(f"not-approved claim: {claim}")

    return (not errors, errors)
