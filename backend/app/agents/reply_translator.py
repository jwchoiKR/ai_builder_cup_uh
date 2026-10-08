"""ReplyTranslator agent: a posted reply in the language of a viewer who asked in another language.

The reply itself was verified in the show's language. A translation is shown under it only when `faithful_numbers`
holds; any doubt leaves the viewer with the original alone."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..logic.verify import number_set
from ..models.agent_io import ReplyTranslationOutput
from ..providers.llm import AgentResult, LLMClient, LLMRequest
from ..providers.prompts import PromptTemplate
from . import inputs

MAX_GROWTH = 3.0  # a translation this many times longer than the reply added something


@dataclass
class TranslateInput:
    text: str
    language: str
    comments: list[str] = field(default_factory=list)  # the askers' own words in that language
    session_id: str | None = None
    scenario: str = "default"


def faithful_numbers(reply: str, translation: str) -> bool:
    """The translation states exactly the reply's numbers (as digits), is not empty and did not grow out of scale."""
    t = translation.strip()
    return bool(t) and number_set(t) == number_set(reply) and len(t) <= MAX_GROWTH * max(len(reply), 20)


class ReplyTranslator:
    name = "reply_translator"

    def __init__(self, llm: LLMClient, prompt: PromptTemplate) -> None:
        self.llm = llm
        self.prompt = prompt
        self.prompt_version = prompt.version
        self.model = llm.fast.model

    async def run(self, inp: TranslateInput, *, deadline_ms: int) -> AgentResult[ReplyTranslationOutput]:
        user = self.prompt.render({
            "target_language_json": inputs.target_language_json(inp.language),
            "viewer_comments_json": inputs.viewer_comments_json(inp.comments),
            "draft_answer_json": inputs.draft_answer_json(inp.text),
        })
        return await self.llm.call(LLMRequest(
            agent=self.name, model=self.llm.fast.model, thinking_level=self.llm.fast.thinking_level,
            prompt_version=self.prompt_version, system_instruction=self.prompt.system_instruction,
            user_message=user, output_model=ReplyTranslationOutput, deadline_ms=deadline_ms,
            session_id=inp.session_id, mock_primary_text=f"{inp.language}|{inp.text}", mock_scenario=inp.scenario,
            # unit tests without fixtures: no translation, the original stays alone
            mock_fallback=lambda _: {"translation": "", "reason": "rule-based: no translation"},
            preview=f"{inp.language}: {inp.text[:80]}",
        ))
