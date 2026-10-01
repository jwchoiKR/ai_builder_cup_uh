"""Common agent interface (DEV_SPEC §7.1)."""
from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

from ..providers.llm import AgentResult

I = TypeVar("I", contravariant=True)
O = TypeVar("O", bound=BaseModel, covariant=True)


class Agent(Protocol[I, O]):
    name: str  # e.g. "utterance_judge"
    prompt_version: str  # from the prompt file header, e.g. "utterance_judge_v1"
    model: str  # from config

    async def run(self, inp: I, *, deadline_ms: int) -> AgentResult[O]: ...
