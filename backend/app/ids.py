"""Runtime ids (DEV_SPEC §6.2): ULIDs with a prefix, or deterministic counters in mock mode."""
from __future__ import annotations

import os
from collections import defaultdict

from .clock import Clock

PREFIXES = ("ses_", "seg_", "tr_", "cm_", "grp_", "ans_", "msg_", "al_", "fx_", "cue_", "ev_", "call_", "an_", "pd_")

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def ulid(now_ms: int) -> str:
    """26-char ULID: 48-bit millisecond timestamp + 80 random bits, Crockford base32."""
    value = (now_ms & ((1 << 48) - 1)) << 80 | int.from_bytes(os.urandom(10), "big")
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(chars))


class Ids:
    """Creates ids. With `deterministic=True` (LLM_PROVIDER=mock) ids are prefix + zero-padded
    counter, counted per (session, prefix), so fixtures and E2E assertions are stable."""

    def __init__(self, clock: Clock, *, deterministic: bool) -> None:
        self._clock = clock
        self.deterministic = deterministic
        self._counters: defaultdict[tuple[str | None, str], int] = defaultdict(int)

    def new(self, prefix: str, session_id: str | None = None) -> str:
        if prefix not in PREFIXES:
            raise ValueError(f"unknown id prefix {prefix!r}")
        if not self.deterministic:
            return prefix + ulid(self._clock.now_ms())
        key = (session_id, prefix)
        self._counters[key] += 1
        return f"{prefix}{self._counters[key]:06d}"
