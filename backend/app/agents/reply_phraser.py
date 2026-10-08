"""ReplyPhraser agent: the wording of a record answer (logic/record_answers).

Code takes the value from the record and writes it as a plain sentence; this agent words that sentence as a reply to
what the viewers actually asked. `keeps_the_facts` decides whether the wording is used: the main value must be said and
no number may appear that the plain sentence does not state. Otherwise the plain sentence is posted."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..logic.verify import number_set
from ..models.agent_io import ReplyPhraseOutput
from ..providers.llm import AgentResult, LLMClient, LLMRequest
from ..providers.prompts import PromptTemplate
from . import inputs


@dataclass
class PhraseInput:
    facts: str  # the record answer as code wrote it
    question: str
    comments: list[str] = field(default_factory=list)
    session_id: str | None = None
    scenario: str = "default"


def keeps_the_facts(facts: str, reply: str, required: set[str]) -> bool:
    """The reply says the asked value (`required` numbers) and states no number the facts do not."""
    said = number_set(reply)
    return bool(reply.strip()) and required <= said and said <= number_set(facts)


class ReplyPhraser:
    name = "reply_phraser"

    def __init__(self, llm: LLMClient, prompt: PromptTemplate) -> None:
        self.llm = llm
        self.prompt = prompt
        self.prompt_version = prompt.version
        self.model = llm.fast.model

    async def run(self, inp: PhraseInput, *, deadline_ms: int) -> AgentResult[ReplyPhraseOutput]:
        user = self.prompt.render({
            "draft_answer_json": inputs.draft_answer_json(inp.facts),
            "canonical_question": inputs.canonical_question(inp.question),
            "viewer_comments_json": inputs.viewer_comments_json(inp.comments or [inp.question]),
        })
        return await self.llm.call(LLMRequest(
            agent=self.name, model=self.llm.fast.model, thinking_level=self.llm.fast.thinking_level,
            prompt_version=self.prompt_version, system_instruction=self.prompt.system_instruction,
            user_message=user, output_model=ReplyPhraseOutput, deadline_ms=deadline_ms,
            session_id=inp.session_id, mock_primary_text=inp.facts, mock_scenario=inp.scenario,
            # unit tests without fixtures: no wording, the plain sentence is posted
            mock_fallback=lambda _: {"reply": "", "reason": "rule-based: no wording"},
            preview=inp.facts[:80],
        ))
