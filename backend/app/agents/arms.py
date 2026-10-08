"""Design arms (D-187): which behaviour an agent call uses. Arm A is today's; B and C move meaning to the model and
keep code only for checking it (C also drops the reflex pre-scan); D and E let the agents decide everything.

The prompt additions of an arm family live in `prompts/design_arms.md`, one `## <family>: <agent>` section each.
"""
from __future__ import annotations

import dataclasses
import re
from functools import lru_cache
from pathlib import Path

FAMILY = {"A": "A", "B": "B", "C": "B", "D": "D", "E": "D", "F1": "D", "F2": "D"}


def family(arm: str) -> str:
    return FAMILY[arm]


def meaning_to_llm(arm: str) -> bool:
    """Arms B to F2: corrections, spoken numbers, hedges, qualifier ids and shout-outs come from the model."""
    return family(arm) in ("B", "D")


def no_reflex(arm: str) -> bool:
    """Arms C to F2: no reflex pre-scan (no provisional chip, no fallback alert when the judge fails)."""
    return arm in ("C", "D", "E", "F1", "F2")


def agents_decide(arm: str) -> bool:
    """Arms D to F2 (D-191): the rules and the product facts go whole into the prompts and the agents decide; code
    keeps deadlines, retries, the state machines, routing permissions and post idempotency only (no comment prefilter
    beyond Model Armor, no code number gate on a post, no code check of a draft before the LLM draft verifier)."""
    return family(arm) == "D"


def whole_facts(arm: str) -> bool:
    """Arms D and E: every product sheet in the judges' prompts, and search plus the whole sheet for the composer."""
    return arm in ("D", "E")


def files(arm: str) -> bool:
    """Arms F1 and F2 (D-192): whole files from the document store. The judges get the on-air product's file in the
    cached prefix, loaded at session start and at each switch; the composer does no search."""
    return arm in ("F1", "F2")


def tools(arm: str) -> bool:
    """Arm F1 (D-192): the composer asks for the files it needs (list_documents, get_product, get_rules)."""
    return arm == "F1"


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


def system_instruction(base: str, agent: str, arm: str, prompts_dir: Path | str, extra_b: bool = False) -> str:
    """The agent's system instruction with its arm family's additions, if any. D-304 `extra_b`: arm B's addition for
    this agent alone (one piece of arm B switched on by itself)."""
    layers = LAYERS[family(arm)]
    layers = (*layers, "B") if extra_b and "B" not in layers else layers
    extras = [x for layer in layers if (x := _addenda(str(prompts_dir)).get((layer, agent)))]
    return "\n\n".join([base, *extras])


_TARGET_GROUP = re.compile(r"^- CURRENT_PRODUCT `target_group`.*?(?=^- )", re.M | re.S)
TARGET_GROUP_PROMPTS = ("utterance_judge", "compliance_judge_rules", "judge_single")  # D-358: the rules prompt


def split_target_group(prompts: dict, prompts_dir: Path | str) -> dict:
    """D-270 arm "split" (critic's ruling 10/6): the D-256 target_group bullet, which put "suitability" under the
    vulnerable-group rules, is replaced by `design_arms.md` "VS: target_group": an age band or a usage direction is
    fine; a safety promise, a condition claim or "no medical check needed" is not. The judges' versions get "+vs"."""
    bullet = _addenda(str(prompts_dir))[("VS", "target_group")] + "\n"
    out = dict(prompts)
    for name in TARGET_GROUP_PROMPTS:
        p = prompts[name]
        system, n = _TARGET_GROUP.subn(lambda _: bullet, p.system_instruction, count=1)
        if n != 1:
            raise ValueError(f"{name}: no target_group bullet to replace (D-270)")
        out[name] = dataclasses.replace(p, version=f"{p.version}+vs", system_instruction=system)
    return out
