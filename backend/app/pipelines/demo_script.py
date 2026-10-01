"""Parser for data/demo/host_script.md (DEV_SPEC §12.6, §13.1, §14.2).

Each table row becomes a step: host lines (the quoted text of rows where "Who acts" is Host) and
operator actions (start, bursts, time sale, B5 arming, end). The Demo Console lists the host lines;
the fixture recorder and the E2E test replay all steps in order.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

_ROW = re.compile(r"^\|\s*(S\d{2})[^|]*\|\s*([^|]+?)\s*\|\s*(.+?)\s*\|\s*(.*?)\s*\|\s*$")
_QUOTED = re.compile(r"\"([^\"]+)\"")
_BURST = re.compile(r"Fire burst \*\*(B\d)\*\*")


@dataclass(frozen=True)
class Step:
    index: int
    scene: str
    who: str  # Host | Operator | System
    action: str  # host_line | start | end | burst | arm_burst | promo_start | edit_reply | setup | auto
    text: str  # the host line, or the raw action text
    arg: str | None  # burst id or promo id
    expected: str

    def as_dict(self) -> dict:
        return asdict(self)


def _classify(who: str, cell: str) -> tuple[str, str, str | None]:
    if who == "Host":
        m = _QUOTED.search(cell)
        return ("host_line", m.group(1), None) if m else ("wait", cell, None)
    if who == "System":
        return "auto", cell, None
    if m := _BURST.search(cell):
        return "burst", cell, m.group(1)
    if "Arm B5" in cell:
        return "arm_burst", cell, "B5"
    if "Start broadcast" in cell:
        return "start", cell, None
    if "End broadcast" in cell:
        return "end", cell, None
    if "Time sale" in cell:
        return "promo_start", cell, "promo_time_sale_10"
    if "Edit reply" in cell:
        return "edit_reply", cell, None
    return "setup", cell, None


def parse_host_script(text: str) -> list[Step]:
    steps: list[Step] = []
    for line in text.splitlines():
        m = _ROW.match(line)
        if not m:
            continue
        scene, who, cell, expected = m.groups()
        action, value, arg = _classify(who.strip(), cell)
        steps.append(Step(len(steps), scene, who.strip(), action, value, arg, expected))
    return steps


@lru_cache
def load_host_script(data_dir: str) -> tuple[Step, ...]:
    return tuple(parse_host_script((Path(data_dir) / "demo" / "host_script.md").read_text(encoding="utf-8")))
