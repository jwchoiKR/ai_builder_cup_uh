"""AI PD (PLANNING 5.1.1): a Google ADK LlmAgent that picks ONE card id from verified candidates.

It never writes wording, so a wrong or non-compliant line cannot reach the host through it. The
three judges stay on the 3 s path; the AI PD runs on broadcast events only. Any failure returns
None and the caller uses the rule fallback (`logic.pd.rule_pick`).
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path

from pydantic import BaseModel

from ..providers.prompts import _examples_text, _parse_file, _template, _until_rule, _with_examples

log = logging.getLogger(__name__)
APP = "ai_pd"


class PdChoice(BaseModel):
    choice: str  # candidate id or "none"
    reason: str


def load_template(prompts_dir: Path):
    pf = _parse_file(prompts_dir / "ai_pd.md")
    return _template(pf, _with_examples(_until_rule(pf.require("SYSTEM INSTRUCTION").lines), _examples_text(pf)))


_MODELS: dict[str, object] = {}  # D-166: one ADK Gemini model (and its genai client) per model name, process-wide


def _gemini(model: str):
    """D-166: given a model name, ADK built a new model object and genai client on every call (a new connection
    and credentials each time, ~1.7 s); one shared object keeps its client."""
    from google.adk.models import Gemini

    if model not in _MODELS:
        _MODELS[model] = Gemini(model=model)
    return _MODELS[model]


class AiPd:
    """One ADK agent and in-memory runner per broadcast session."""

    def __init__(self, *, project: str, location: str, model: str, thinking_level: str, prompts_dir: Path) -> None:
        # ADK's Gemini client reads these; the backend itself passes project/location explicitly.
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project)
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", location)
        from google.adk.agents import LlmAgent
        from google.adk.runners import InMemoryRunner
        from google.genai import types

        self.template = load_template(prompts_dir)
        self.version = self.template.version
        self.model = model
        self._types = types
        system = self.template.system_instruction
        self.agent = LlmAgent(
            name="ai_pd", model=_gemini(model), description="Picks the host's next action card.",
            instruction=lambda _ctx: system,  # a callable: ADK does not template the JSON braces
            output_schema=PdChoice, include_contents="none",
            generate_content_config=types.GenerateContentConfig(
                temperature=0.0, thinking_config=types.ThinkingConfig(thinking_level=thinking_level)),
        )
        self.runner = InMemoryRunner(agent=self.agent, app_name=APP)

    async def choose(self, state: dict, candidates: list[dict], deadline_ms: int) -> tuple[PdChoice | None, int, str]:
        """Returns (choice, latency_ms, status) with status ok | timeout | error | invalid."""
        started = time.perf_counter()
        text = self.template.render({"pd_state_json": state, "pd_candidates_json": candidates})
        msg = self._types.Content(role="user", parts=[self._types.Part(text=text)])
        status, choice = "error", None
        session = None
        try:
            async with asyncio.timeout(deadline_ms / 1000):
                session = await self.runner.session_service.create_session(app_name=APP, user_id="pd")
                final = None
                async for ev in self.runner.run_async(user_id="pd", session_id=session.id, new_message=msg):
                    if ev.is_final_response() and ev.content and ev.content.parts:
                        final = "".join(p.text or "" for p in ev.content.parts)
            choice = PdChoice.model_validate_json(final or "")
            ids = {c["id"] for c in candidates}
            status = "ok" if choice.choice == "none" or choice.choice in ids else "invalid"
            if status == "invalid":
                choice = None
        except TimeoutError:
            status = "timeout"
        except Exception as e:  # noqa: BLE001 - any model/ADK failure falls back to rules
            log.warning("ai_pd failed: %s", type(e).__name__)
        finally:
            if session is not None:
                try:
                    await self.runner.session_service.delete_session(app_name=APP, user_id="pd", session_id=session.id)
                except Exception:  # noqa: BLE001
                    pass
        return choice, round((time.perf_counter() - started) * 1000), status
