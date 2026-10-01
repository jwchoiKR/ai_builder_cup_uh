"""Server clock. All timestamps are UTC milliseconds since epoch (DEV_SPEC §6.2)."""
from __future__ import annotations

import time
from typing import Protocol


class Clock(Protocol):
    def now_ms(self) -> int: ...


class SystemClock:
    def now_ms(self) -> int:
        return time.time_ns() // 1_000_000


class ManualClock:
    """Test clock that only moves when told to."""

    def __init__(self, start_ms: int = 1_790_000_000_000) -> None:
        self._now = start_ms

    def now_ms(self) -> int:
        return self._now

    def advance(self, ms: int) -> int:
        self._now += ms
        return self._now
