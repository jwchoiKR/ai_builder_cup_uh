"""Shout-out comments (D-113): purchases, first-time viewers and compliments, by keyword rules on the
reaction path. No LLM call. The AI PD reads them out with a fixed template and the viewer's name."""
from __future__ import annotations

import re

_RULES: list[tuple[str, re.Pattern]] = [
    ("purchase", re.compile(r"\b(just bought|bought (it|one|two|the)|ordered|checked out|purchased)\b", re.I)),
    ("first_time", re.compile(r"\b(first time|new here|my first live)\b", re.I)),
    ("compliment", re.compile(r"\b(love (it|this|the)|so pretty|amazing|great product|so good)\b", re.I)),
]


def shout_kind(text: str) -> str | None:
    return next((kind for kind, rx in _RULES if rx.search(text)), None)
