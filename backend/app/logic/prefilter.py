"""Comment prefilter, no LLM (DEV_SPEC §8.8 step 2)."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

_URL = re.compile(r"https?://|www\.|\b\w+\.(?:com|net|org|sg|ly|io|co|example)\b", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# 8-digit Singapore numbers starting with 6, 8 or 9, optional +65, spaces (or hyphens) allowed.
_PHONE = re.compile(r"(?<![\d+])(?:\+?65[\s-]*)?[689](?:[\s-]?\d){7}(?!\d)")

REACTIONS = frozenset({
    "lol", "lmao", "haha", "hahaha", "wow", "omg", "nice", "cute", "same", "yes", "yesss", "yay",
    "love it", "love this", "so pretty", "so cute", "hi", "hello", "hi hi", "first", "+1",
})


@dataclass(frozen=True)
class PrefilterVerdict:
    kind: Literal["hide", "reaction"] | None  # None: needs the LLM
    hide_category: Literal["link", "personal_info", "profanity"] | None = None
    reason: str = ""

    def as_output(self) -> dict:
        return {"kind": self.kind, "hide_category": self.hide_category, "reason": self.reason}


@lru_cache
def _profanity() -> re.Pattern:
    words = [ln.strip().lower() for ln in (Path(__file__).with_name("profanity.txt")).read_text("utf-8").splitlines()
             if ln.strip() and not ln.startswith("#")]
    alternation = "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in sorted(words, key=len, reverse=True))
    return re.compile(rf"\b(?:{alternation})\b", re.IGNORECASE)


def _reaction_form(text: str) -> str:
    kept = "".join(ch if (ch.isalnum() or ch.isspace() or ch == "+") else " " for ch in text.lower())
    return re.sub(r"\s+", " ", kept).strip()


def _letters(text: str) -> int:
    return sum(1 for ch in text if unicodedata.category(ch).startswith("L"))


def prefilter(text: str) -> PrefilterVerdict:
    if _EMAIL.search(text):
        return PrefilterVerdict("hide", "personal_info", "email address")
    if _PHONE.search(text):
        return PrefilterVerdict("hide", "personal_info", "phone number")
    if _URL.search(text):
        return PrefilterVerdict("hide", "link", "link or domain")
    if _profanity().search(text):
        return PrefilterVerdict("hide", "profanity", "profanity list")
    if _letters(text) < 3:
        return PrefilterVerdict("reaction", None, "emoji, punctuation or fewer than 3 letters")
    if _reaction_form(text) in REACTIONS:
        return PrefilterVerdict("reaction", None, "reaction list")
    return PrefilterVerdict(None)
