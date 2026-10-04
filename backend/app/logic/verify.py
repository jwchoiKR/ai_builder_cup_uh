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
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


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


# D-117 B8: numbers are checked with their subject ("panthenol 5%"), not only "appears in some quote"
_TOKEN = re.compile(r"\d+(?:\.\d+)?|[a-z][a-z'-]*")
_UNITS = frozenset("""ml mls percent s sgd dollar dollars hour hours week weeks month months day days minute minutes
pump pumps drop drops g x of and the a an is are has have with""".split())
SUBJECT_WINDOW = 3


def _words_near(tokens: list[str], i: int) -> list[tuple[int, str]]:
    """(distance, word) around tokens[i]; before wins a tie. Units and fillers ("S$" -> "s", "is") do not
    count toward the distance (D-135: "live broadcast price is S$36.00")."""
    left = [t for t in tokens[:i] if t not in _UNITS][::-1]
    right = [t for t in tokens[i + 1:] if t not in _UNITS]
    out = []
    for d in range(1, SUBJECT_WINDOW + 1):
        for side in (left, right):
            if d <= len(side) and not side[d - 1][0].isdigit():
                out.append((d, side[d - 1][:5]))
    return out


_LABELLED = re.compile(r"([A-Za-z][A-Za-z ()/'-]{1,60}):\s*(?:S\$|\$)?(\d+(?:\.\d+)?)")


def quoted_subjects(quotes: Sequence[str], stopwords: frozenset[str]) -> dict[str, set[str]]:
    """Subjects of the sheet's "Label: value" facts ("Panthenol: 5%" -> panthenol = 5). A label word
    with several values ("price" in "Live price" and "List price") cannot tell them apart and is dropped."""
    by_word: dict[str, set[str]] = {}
    near: dict[str, set[str]] = {}  # every number a word stands next to anywhere in the quotes
    for q in quotes:
        for label, value in _LABELLED.findall(q):
            for w in _TOKEN.findall(label.lower()):
                if not w[0].isdigit() and w not in stopwords and w not in _UNITS and len(w) > 2:
                    by_word.setdefault(w[:5], set()).update(number_set(value))
        tokens = _TOKEN.findall(q.lower())
        for i, tok in enumerate(tokens):
            if tok[0].isdigit():
                for _, w in _words_near(tokens, i):
                    near.setdefault(w, set()).update(number_set(tok))
    # "(3 molecular weights): 1%" or "48-hour patch test: 0 of 30": a label word next to another number
    # cannot tell values apart either
    return {w: ns for w, ns in by_word.items() if len(ns) == 1 and near.get(w, ns) <= ns}


def misattributed_numbers(answer: str, subjects: dict[str, set[str]]) -> list[tuple[str, str]]:
    """(number, subject) pairs in the answer whose subject has another value in the quotes."""
    out = []
    # D-135: within one clause only (split at . ; ( ) ", " and "and"): "(list price S$48.00). The set ..." must
    # not tie 48 to "set"; a number is fine when any subject of its clause near it has that value
    for clause in re.split(r"[;()]|,\s|\band\b|(?<!\d)[.!?](?!\d)", answer.lower()):
        tokens = _TOKEN.findall(clause)
        for i, tok in enumerate(tokens):
            if not tok[0].isdigit():
                continue
            near = [w for _, w in _words_near(tokens, i) if w in subjects]
            if near and not any(number_set(tok) <= subjects[w] for w in near):
                out.extend((n, near[0]) for n in sorted(number_set(tok)))
    return out


def is_promo_passage(passage_id: str) -> bool:
    return passage_id.startswith("PROMO#")


IN_HOUSE_SECTION = "In-house test results"

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
    if len(reflex.lexicon.split_sentences(answer)) > MAX_SENTENCES:
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

    # 6. D-117 B8: a number next to a subject of the quotes must be that subject's value there
    subjects = quoted_subjects([c.quote for c in output.citations if c.passage_id in by_id], reflex.lexicon.stopwords)
    for n, subject in misattributed_numbers(answer, subjects):
        errors.append(f"number {n} is not the value of '{subject}' in the cited quotes")

    # 7. D-126: a number from an in-house test result is said with "in-house" / "our test" (D007)
    test_numbers: set[str] = set()
    for p in cited:
        if p.section == IN_HOUSE_SECTION:
            test_numbers |= number_set(p.text)
    if test_numbers & number_set(answer) and not reflex.lexicon.is_qualified(answer):
        errors.append("in-house test result without 'in-house test'")

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
