"""Design arms (D-187): which behaviour an agent call uses. Arm A is today's; B and C move meaning to the model and
keep code only for checking it (C also drops the reflex pre-scan); D and E let the agents decide everything.

The prompt additions of an arm family live in `prompts/design_arms.md`, one `## <family>: <agent>` section each.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

FAMILY = {"A": "A", "B": "B", "C": "B", "D": "D", "E": "D"}


def family(arm: str) -> str:
    return FAMILY[arm]


def meaning_to_llm(arm: str) -> bool:
    """Arms B and C: corrections, spoken numbers, hedges, qualifier ids and shout-outs come from the model."""
    return family(arm) == "B"


@lru_cache(maxsize=4)
def _addenda(prompts_dir: str) -> dict[tuple[str, str], str]:
    path = Path(prompts_dir) / "design_arms.md"
    if not path.is_file():
        return {}
    out: dict[tuple[str, str], str] = {}
    for m in re.finditer(r"^## (\w+): (\w+)\n(.*?)(?=^## |\Z)", path.read_text(encoding="utf-8"), re.M | re.S):
        out[(m.group(1), m.group(2))] = m.group(3).strip()
    return out


def system_instruction(base: str, agent: str, arm: str, prompts_dir: Path | str) -> str:
    """The agent's system instruction with its arm family's addition, if any."""
    extra = _addenda(str(prompts_dir)).get((family(arm), agent))
    return f"{base}\n\n{extra}" if extra else base
