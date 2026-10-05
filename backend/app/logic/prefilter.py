"""Comment prefilter, no LLM (DEV_SPEC §8.8 step 2)."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .lexicon import Lexicon

_URL = re.compile(r"https?://|www\.|\b\w+\.(?:com|net|org|sg|ly|io|co|example)\b", re.IGNORECASE)
# D-234: the whole link, to remove it from a comment that is still a question
_LINK = re.compile(r"(?:https?://|www\.)\S+|\b[\w-]+(?:\.[\w-]+)*\.(?:com|net|org|sg|my|ly|io|co|example)\b(?:/\S*)?",
                   re.IGNORECASE)
LINK_REMOVED = "[link removed]"


def mask_links(text: str) -> str:
    """D-234: a comment's links replaced by "[link removed]"; the rest of the comment stays."""
    return _LINK.sub(LINK_REMOVED, text)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

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


def prefilter(text: str, lex: "Lexicon") -> PrefilterVerdict:
    """Phone numbers come from the market pack, reactions from the language pack (D-134)."""
    if _EMAIL.search(text):
        return PrefilterVerdict("hide", "personal_info", "email address")
    if lex.phone.search(text):
        return PrefilterVerdict("hide", "personal_info", "phone number")
    if _URL.search(text) or LINK_REMOVED in text:
        # D-234 (injection eval: a viewer question with a link was hidden): the link is removed and the rest goes on to
        # triage, which tells spam from a question ("price for the 50ml", no "?" needed); only a bare link is hidden here
        rest = mask_links(text).replace(LINK_REMOVED, " ")
        if _letters(rest) < 3:
            return PrefilterVerdict("hide", "link", "a link and nothing else")
        text = rest
    if _profanity().search(text):
        return PrefilterVerdict("hide", "profanity", "profanity list")
    letters = _letters(text)
    # a short comment with a question mark can be a real question ("ml?", "spf?"): the LLM decides
    if letters == 0 or (letters < 3 and "?" not in text):
        return PrefilterVerdict("reaction", None, "emoji, punctuation or fewer than 3 letters without '?'")
    if _reaction_form(text) in lex.reactions:
        return PrefilterVerdict("reaction", None, "reaction list")
    return PrefilterVerdict(None)
