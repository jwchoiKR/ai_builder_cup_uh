"""Feed engine (DEV_SPEC §13.2): background chatter from comment_pool.json and scripted bursts from
comment_script.json, posted through the normal comment pipeline. `expect` fields are ignored."""
from __future__ import annotations

import json
import logging
import random
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..models.session import Segment

if TYPE_CHECKING:
    from .runtime import SessionRuntime

log = logging.getLogger(__name__)

ARM_GRACE_MS = 1000  # a burst armed within 1 s after a segment start fires at once


NO_SCRIPT: dict[str, Any] = {"bursts": {}}
NO_POOL: dict[str, Any] = {"playback": {"seed": 0}, "items": []}


@lru_cache
def load_script(data_dir: str) -> dict[str, Any]:
    path = Path(data_dir) / "demo" / "comment_script.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else NO_SCRIPT  # D-278: optional


@lru_cache
def load_pool(data_dir: str) -> dict[str, Any]:
    path = Path(data_dir) / "demo" / "comment_pool.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else NO_POOL  # D-278: optional


class FeedEngine:
    def __init__(self, rt: "SessionRuntime", demo: bool = True) -> None:
        """D-278: `demo=False` (a release show) gets no demo bursts or chatter: they are about the demo products."""
        self.rt = rt
        data_dir = str(rt.settings.data_path)
        self.script = load_script(data_dir) if demo else NO_SCRIPT
        self.pool = load_pool(data_dir) if demo else NO_POOL
        self.pool_running = False
        self.armed: dict[str, dict] = {}
        self.fired: list[str] = []
        playback = self.pool["playback"]
        self._rng = random.Random(playback["seed"])
        items = self.pool["items"]
        self._hide_items = [i for i in items if (i.get("expect") or {}).get("kind") == "hide"]
        self._normal = [i for i in items if i not in self._hide_items]
        self._rng.shuffle(self._normal)
        self._cursor = 0
        self._hide_cursor = 0
        self._posted = 0

    # ---- state for the Demo Console --------------------------------------------------------------

    def state(self) -> dict[str, Any]:
        return {"pool_running": self.pool_running, "pool_available": bool(self.pool["items"]),  # D-337
                "armed": sorted(self.armed), "fired": list(self.fired),
                "bursts": [{"burst_id": k, "scene": v.get("scene"), "description": v.get("description"),
                            "anchor": v.get("anchor", "trigger"), "count": len(v["comments"])}
                           for k, v in self.script["bursts"].items()]}

    def resolve(self, burst_id: str) -> str | None:
        bursts = self.script["bursts"]
        if burst_id in bursts:
            return burst_id
        matches = [k for k in bursts if k.split("_", 1)[0].lower() == burst_id.lower()]
        return matches[0] if len(matches) == 1 else None

    # ---- background chatter ----------------------------------------------------------------------

    def _notify(self) -> None:
        """`feed.updated` for the Demo Console (D-059)."""
        self.rt.spawn(self.rt.emit("feed.updated", self.state()), name="feed.updated")

    def start_pool(self) -> None:
        if self.pool_running or not self.pool["items"]:  # D-337: a release show has no demo chatter (was a 500)
            return
        self.pool_running = True
        self._schedule_next()
        self._notify()

    def stop_pool(self) -> None:
        was = self.pool_running
        self.pool_running = False
        self.rt.ctx.scheduler.cancel(self.rt.key("feed:pool"))
        if was:
            self._notify()

    def _schedule_next(self) -> None:
        pb = self.pool["playback"]
        gap = self._rng.randint(pb["min_gap_ms"], pb["max_gap_ms"])
        self.rt.ctx.scheduler.call_later(self.rt.key("feed:pool"), gap, self._pool_step)

    async def _pool_step(self) -> None:
        if not self.pool_running or self.rt.closed:
            return
        s = await self.rt.load_session()
        if s.status != "live":
            self.pool_running = False
            return
        seg = await self.rt.current_segment()
        item = self._next_item(seg.product_id if seg else None)
        if item is not None:
            await self._post(item, source="pool", scenario="default")
        self._schedule_next()

    def _next_item(self, on_air: str | None) -> dict | None:
        self._posted += 1
        every = self.pool["playback"]["hide_item_every_n"]
        if self._hide_items and every and self._posted % every == 0:
            item = self._hide_items[self._hide_cursor % len(self._hide_items)]
            self._hide_cursor += 1
            return item
        for _ in range(len(self._normal)):
            item = self._normal[self._cursor % len(self._normal)]
            self._cursor += 1
            if item["product_tag"] in ("any", on_air):
                return item
        return None

    # ---- bursts ----------------------------------------------------------------------------------

    async def fire(self, burst_id: str) -> dict[str, Any]:
        """Schedule a burst at trigger time, or arm it for the next segment start (B5)."""
        from .runtime import ActionError

        key = self.resolve(burst_id)
        if key is None:
            raise ActionError(404, "unknown_burst", f"burst {burst_id} not found")
        burst = self.script["bursts"][key]
        if burst.get("anchor", "trigger") == "next_segment_start":
            now = self.rt.now()
            for seg in await self.rt.segments():
                if seg.start_reason in ("auto_speech", "operator") and 0 <= now - seg.started_at < ARM_GRACE_MS:
                    self._schedule(key, seg.started_at)
                    self._notify()
                    return {"burst_id": key, "status": "fired"}
            self.armed[key] = burst
            self._notify()
            return {"burst_id": key, "status": "armed"}
        self._schedule(key, self.rt.now())
        self._notify()
        return {"burst_id": key, "status": "fired"}

    def on_segment_started(self, seg: Segment) -> None:
        if seg.start_reason not in ("auto_speech", "operator"):
            return  # never on session start or on the reopen after an Undo
        fired = bool(self.armed)
        for key in list(self.armed):
            del self.armed[key]
            self._schedule(key, seg.started_at)
        if fired:
            self._notify()

    def _schedule(self, key: str, anchor_ms: int) -> None:
        burst = self.script["bursts"][key]
        self.fired.append(key)
        for i, c in enumerate(burst["comments"]):
            async def post(c=c) -> None:
                await self._post(c, source="script", scenario=burst.get("scene", "default"))
            self.rt.ctx.scheduler.call_at(self.rt.key(f"feed:{key}:{i}"), anchor_ms + c["offset_ms"], post)

    async def _post(self, item: dict, *, source: str, scenario: str) -> None:
        from .comments import submit_comment
        from .runtime import ActionError

        try:
            await submit_comment(self.rt, author_id=item["author_id"], author_name=item["author_name"],
                                 text=item["text"], source=source, scenario=scenario)
        except ActionError as e:
            log.warning("feed comment dropped (%s): %s", e.code, item["text"])

    def stop_all(self) -> None:
        self.stop_pool()
        self.armed.clear()
        self.rt.ctx.scheduler.cancel_prefix(self.rt.key("feed:"))
