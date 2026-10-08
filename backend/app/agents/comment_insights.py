"""CommentInsights agent: the questions of a finished broadcast sorted into topics (pipelines/comment_insights).

The model only says which question belongs to which topic. It returns no numbers; every count on the summary page is
computed by code from the stored comment documents."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models.agent_io import CommentInsightsOutput
from ..providers.llm import AgentResult, LLMClient, LLMRequest
from ..providers.prompts import PromptTemplate
from . import inputs


@dataclass
class InsightsInput:
    questions: list[dict] = field(default_factory=list)  # {key, question, comments, product}
    session_id: str | None = None
    scenario: str = "default"


class CommentInsights:
    name = "comment_insights"

    def __init__(self, llm: LLMClient, prompt: PromptTemplate) -> None:
        self.llm = llm
        self.prompt = prompt
        self.prompt_version = prompt.version
        self.model = llm.quality.model

    async def run(self, inp: InsightsInput, *, deadline_ms: int) -> AgentResult[CommentInsightsOutput]:
        user = self.prompt.render({"asked_questions_json": inputs.asked_questions_json(inp.questions)})
        return await self.llm.call(LLMRequest(
            agent=self.name, model=self.llm.quality.model, thinking_level=self.llm.quality.thinking_level,
            prompt_version=self.prompt_version, system_instruction=self.prompt.system_instruction,
            user_message=user, output_model=CommentInsightsOutput, deadline_ms=deadline_ms,
            session_id=inp.session_id, mock_primary_text=f"{len(inp.questions)} questions",
            mock_scenario=inp.scenario,
            # no fixture: no topics from a model, so the pipeline falls back to the stored topic labels
            mock_fallback=lambda _: {"topics": [], "notes": []},
            preview=f"{len(inp.questions)} questions",
        ))
