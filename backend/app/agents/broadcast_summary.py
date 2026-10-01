"""BroadcastSummary agent (DEV_SPEC §7.8): prose recap around the code-computed statistics (§8.14).

Post-validation: every number in the recap must appear in the statistics; a sentence with an
unknown number is dropped.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from ..models.agent_io import SummaryOutput
from ..providers.llm import AgentResult, LLMClient, LLMRequest
from ..providers.prompts import PromptTemplate
from . import inputs

_NUMBER = re.compile(r"\d+(\.\d+)?")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
NEUTRAL_HEADLINE = "Broadcast recap based on the recorded statistics."


@dataclass
class SummaryInput:
    stats: dict[str, Any]
    session_id: str | None = None
    scenario: str = "default"
    meta: dict[str, Any] = field(default_factory=dict)


def _norm(raw: str) -> str:
    try:
        return format(Decimal(raw).normalize(), "f")
    except InvalidOperation:
        return raw


def stats_numbers(stats: dict[str, Any]) -> set[str]:
    """Every number written anywhere in the statistics JSON, normalised (36.00 = 36)."""
    text = json.dumps(stats, ensure_ascii=False)
    return {_norm(m.group(0)) for m in _NUMBER.finditer(text)}


def _numbers_ok(text: str, allowed: set[str]) -> bool:
    return all(_norm(m.group(0)) in allowed for m in _NUMBER.finditer(text))


def _keep_sentences(text: str, allowed: set[str]) -> str:
    kept = [s for s in _SENTENCE_END.split(text.strip()) if s and _numbers_ok(s, allowed)]
    return " ".join(kept).strip()


def post_validate(out: SummaryOutput, stats: dict[str, Any]) -> SummaryOutput:
    """§7.8: drop every sentence whose numbers are not all in the statistics."""
    allowed = stats_numbers(stats)
    headline = _keep_sentences(out.headline, allowed) or NEUTRAL_HEADLINE

    def clean(items: list[str]) -> list[str]:
        return [s for s in (_keep_sentences(i, allowed) for i in items) if s]

    return SummaryOutput(headline=headline, highlights=clean(out.highlights), watch_outs=clean(out.watch_outs),
                         follow_ups=clean(out.follow_ups))


class BroadcastSummary:
    name = "broadcast_summary"

    def __init__(self, llm: LLMClient, prompt: PromptTemplate) -> None:
        self.llm = llm
        self.prompt = prompt
        self.prompt_version = prompt.version
        self.model = llm.quality.model

    async def run(self, inp: SummaryInput, *, deadline_ms: int) -> AgentResult[SummaryOutput]:
        user = self.prompt.render({"summary_stats_json": inputs.summary_stats_json(inp.stats)})
        res = await self.llm.call(LLMRequest(
            agent=self.name, model=self.llm.quality.model, thinking_level=self.llm.quality.thinking_level,
            prompt_version=self.prompt_version, system_instruction=self.prompt.system_instruction,
            user_message=user, output_model=SummaryOutput, deadline_ms=deadline_ms, session_id=inp.session_id,
            mock_primary_text="summary", mock_scenario=inp.scenario,
            mock_fallback=lambda _: rule_based_summary(inp.stats), preview="summary",
        ))
        if res.output is not None:
            res.output = post_validate(res.output, inp.stats)
        return res


# ---- rule-based fallback for unit tests -----------------------------------------------------------


def rule_based_summary(stats: dict[str, Any]) -> dict:
    totals = stats.get("totals", {})
    products = stats.get("products", [])
    compliance = stats.get("compliance_alerts", [])
    unanswered = sum(len(p.get("unanswered_groups", [])) for p in products) + len(stats.get("general_unanswered_groups", []))
    highlights = [f"Viewers posted {totals.get('comments', 0)} comments, including {totals.get('questions', 0)} questions."]
    corrected = [a for a in compliance if isinstance(a.get("shown_to_corrected_ms"), int)]
    if corrected:
        highlights.append(f"The host corrected {len(corrected)} compliance alerts on air.")
    watch = [f"There were {len(compliance)} compliance alerts during the broadcast."] if compliance else \
        ["No compliance alert was raised."]
    follow = [f"Reply to the {unanswered} unanswered question groups."] if unanswered else \
        ["Review the question log for follow-up content."]
    return SummaryOutput(headline=f"{stats.get('title', 'Broadcast')} recap.", highlights=highlights,
                         watch_outs=watch, follow_ups=follow).model_dump()
