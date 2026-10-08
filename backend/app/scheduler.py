"""Timers and background tasks.

All delayed work (escalation, publish windows, switch countdown, promo end, feed offsets, ticks)
goes through a Scheduler with string keys, so a timer can be replaced or cancelled by key.
`AsyncScheduler` runs in real time. `ManualScheduler` runs only when a test calls `advance()`,
together with `ManualClock`, so timer behaviour is deterministic in tests.
"""
from __future__ import annotations

import asyncio
import heapq
import itertools
import logging
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

from .clock import Clock, ManualClock

log = logging.getLogger(__name__)

TimerFn = Callable[[], Awaitable[Any]]


def _log_task_error(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        log.error("background task %s failed", task.get_name(), exc_info=exc)


class _TaskTracker:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()

    def spawn(self, coro: Coroutine, name: str | None = None) -> asyncio.Task:
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        task.add_done_callback(_log_task_error)
        return task

    async def idle(self) -> None:
        """Wait until no spawned task is running (tasks may spawn more tasks)."""
        for _ in range(1000):
            await asyncio.sleep(0)
            if not self._tasks:
                return
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
        raise RuntimeError("scheduler did not become idle")

    def cancel_all(self) -> None:
        for t in list(self._tasks):
            t.cancel()


class AsyncScheduler(_TaskTracker):
    def __init__(self, clock: Clock) -> None:
        super().__init__()
        self._clock = clock
        self._timers: dict[str, asyncio.Task] = {}

    def call_at(self, key: str, when_ms: int, fn: TimerFn) -> None:
        self.cancel(key)

        async def runner() -> None:
            delay = (when_ms - self._clock.now_ms()) / 1000
            if delay > 0:
                await asyncio.sleep(delay)
            # Unregister before running: cancel(key) can no longer interrupt a half-applied change,
            # and fn may schedule the same key again.
            if self._timers.get(key) is asyncio.current_task():
                del self._timers[key]
            await fn()

        task = asyncio.create_task(runner(), name=f"timer:{key}")
        task.add_done_callback(_log_task_error)
        self._timers[key] = task

    def call_later(self, key: str, delay_ms: int, fn: TimerFn) -> None:
        self.call_at(key, self._clock.now_ms() + delay_ms, fn)

    def cancel(self, key: str) -> bool:
        task = self._timers.pop(key, None)
        if task is None:
            return False
        task.cancel()
        return True

    def cancel_prefix(self, prefix: str) -> None:
        for key in [k for k in self._timers if k.startswith(prefix)]:
            self.cancel(key)

    def has(self, key: str) -> bool:
        return key in self._timers

    def shutdown(self) -> None:
        for key in list(self._timers):
            self.cancel(key)
        self.cancel_all()


class ManualScheduler(_TaskTracker):
    """Test scheduler: timers fire only inside `advance()`, in time order, with the clock set
    to each timer's due time. Spawned tasks run normally; `advance()` waits for them."""

    def __init__(self, clock: ManualClock) -> None:
        super().__init__()
        self._clock = clock
        self._timers: dict[str, tuple[int, int, TimerFn]] = {}
        self._seq = itertools.count()

    def call_at(self, key: str, when_ms: int, fn: TimerFn) -> None:
        self._timers[key] = (when_ms, next(self._seq), fn)

    def call_later(self, key: str, delay_ms: int, fn: TimerFn) -> None:
        self.call_at(key, self._clock.now_ms() + delay_ms, fn)

    def cancel(self, key: str) -> bool:
        return self._timers.pop(key, None) is not None

    def cancel_prefix(self, prefix: str) -> None:
        for key in [k for k in self._timers if k.startswith(prefix)]:
            del self._timers[key]

    def has(self, key: str) -> bool:
        return key in self._timers

    def due_at(self, key: str) -> int | None:
        entry = self._timers.get(key)
        return entry[0] if entry else None

    async def advance(self, ms: int) -> None:
        target = self._clock.now_ms() + ms
        while True:
            await self.idle()
            due = [(when, seq, key) for key, (when, seq, _) in self._timers.items() if when <= target]
            if not due:
                break
            when, _, key = heapq.nsmallest(1, due)[0]
            _, _, fn = self._timers.pop(key)
            if when > self._clock.now_ms():  # D-422: advance (not set), so the monotonic time moves too
                self._clock.advance(when - self._clock.now_ms())
            await fn()
        if target > self._clock.now_ms():
            self._clock.advance(target - self._clock.now_ms())
        await self.idle()

    def shutdown(self) -> None:
        self._timers.clear()
        self.cancel_all()
