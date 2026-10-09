from __future__ import annotations

import pytest

from app.agents.utterance_judge import say_instead_fallback, spoken_claim


@pytest.mark.parametrize("text, spoken", [
    ("Helps keep skin hydrated for up to 24 hours.*", "Helps keep skin hydrated for up to 24 hours in our in-house test."),
    ("Helps keep skin hydrated for up to 24 hours.* ", "Helps keep skin hydrated for up to 24 hours in our in-house test."),
    ("Patch tested with no irritation reactions in our in-house test.*", "Patch tested with no irritation reactions in our in-house test."),
    ("It helps relieve the feeling of dryness.", "It helps relieve the feeling of dryness."),
])
def test_spoken_claim(text, spoken):
    assert spoken_claim(text) == spoken
