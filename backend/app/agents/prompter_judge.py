"""D-450: the prompter judge. One call per final host line, in parallel with the other three judges and waited on by
none of them: which prompter points the host has now said. The only judge that ticks points (the context judge no
longer does). `host_words` is kept in the agent-call log only; code takes the point ids, and an unknown id is skipped
where the ticks are applied."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..logic.catalog import Catalog
from ..models.agent_io import PrompterJudgeOutput
from ..models.data import PrompterPoint
from ..providers.llm import AgentResult, LLMClient, LLMRequest
from ..providers.prompts import PromptTemplate
from . import inputs


@dataclass
class PrompterInput:
    utterance: str  # the line as the judges read it (a merged STT-split line's joined text)
    on_air: str  # the product of the line's own segment
    previous: list[str] = field(default_factory=list)
    points: dict[str, list[PrompterPoint]] | None = None  # Setup overrides of the products' points
    session_id: str | None = None
    scenario: str = "default"


class PrompterJudge:
    name = "prompter_judge"

    def __init__(self, llm: LLMClient, prompt: PromptTemplate, catalog: Catalog) -> None:
        self.llm = llm
        self.prompt = prompt
        self.prompt_version = prompt.version
        self.catalog = catalog

    async def run(self, inp: PrompterInput, *, deadline_ms: int | None = None) -> AgentResult[PrompterJudgeOutput]:
        """D-455: no deadline by default: the verdict counts whenever it comes (the caller applies it to the line's own
        segment)."""
        user = self.prompt.render({
            "prompter_judge_points_json": inputs.prompter_judge_points_json(self.catalog, inp.on_air, inp.points),
            "last_two_final_transcripts_json": inp.previous[-2:],
            "utterance_text": inputs.utterance_text(inp.utterance),
        })
        return await self.llm.call(LLMRequest(
            agent=self.name, model=self.llm.prompter.model, thinking_level=self.llm.prompter.thinking_level,
            prompt_version=self.prompt_version, system_instruction=self.prompt.system_instruction, user_message=user,
            output_model=PrompterJudgeOutput, deadline_ms=deadline_ms, session_id=inp.session_id,
            retry_429=False, hedge=False,  # D-449: one call, no 429 wait, not hedged; D-455: no deadline
            mock_primary_text=inp.utterance, mock_scenario=inp.scenario, mock_fallback=lambda _: {"covered": []},
            preview=inp.utterance,
        ))
