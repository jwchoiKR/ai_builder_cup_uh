from __future__ import annotations

import pytest

from app.logic.reflex import Reflex, normalise


@pytest.fixture(scope="module")
def reflex(pack):
    return Reflex(pack.rules, pack.lexicon)


def rules(hits):
    return [h.rule_id for h in hits]


def test_normalise():
    assert normalise("It’s “100% safe” — S$36.00!") == "it's 100% safe s$36.00"
    assert normalise("No. 1 cream") == "no 1 cream"
