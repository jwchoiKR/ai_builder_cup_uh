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
    """Arms B to E: corrections, spoken numbers, hedges, qualifier ids and shout-outs come from the model."""
    return family(arm) in ("B", "D")


def no_reflex(arm: str) -> bool:
    """Arms C, D and E: no reflex pre-scan (no provisional chip, no fallback alert when the judge fails)."""
    return arm in ("C", "D", "E")


def agents_decide(arm: str) -> bool:
    """Arms D and E (D-191): the rules and the product facts go whole into the prompts and the agents decide; code
    keeps deadlines, retries, the state machines, routing permissions and post idempotency only (no comment prefilter
    beyond Model Armor, no code number gate on a post, no code check of a draft before the LLM draft verifier)."""
    return family(arm) == "D"


LAYERS = {"A": (), "B": ("B",), "D": ("B", "D")}  # D builds on B's model fields


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
    """The agent's system instruction with its arm family's additions, if any."""
    extras = [x for layer in LAYERS[family(arm)] if (x := _addenda(str(prompts_dir)).get((layer, agent)))]
    return "\n\n".join([base, *extras])
