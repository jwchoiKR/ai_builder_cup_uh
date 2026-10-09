"""Purpose-based Gemini routing experiment; client creation is explicit."""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from app.providers.llm import LLMRequest
from app.providers.prompts import _examples_text, _parse_file, _template, _until_rule, _with_examples
from experiments.jev_router import SPECIALISTS

GEMINI_ROUTER_DEADLINE_MS = 1500


class RouterOutput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    compliance: bool
    facts: bool
    context: bool
    reason: str


class GeminiRouter:
    def __init__(self, client=None) -> None:
        self._owns_client = client is None
        if client is None:
            from eval_common import make_client

            client, _ = make_client(False)
            client._settings = client._settings.model_copy(update={"LLM_RETRY_ON_5XX": 0})
        self._client = client
        pf = _parse_file(Path(__file__).parent / "prompts" / "router_purpose.md")
        self._template = _template(
            pf, _with_examples(_until_rule(pf.require("SYSTEM INSTRUCTION").lines), _examples_text(pf)))
        self._warm_result = None
        self._warm_lock = asyncio.Lock()

    async def route(self, state: dict) -> tuple[dict[str, float] | None, int, str]:
        started = time.perf_counter()
        template, client = self._template, self._client
        try:
            result = await asyncio.wait_for(client.call(LLMRequest(
                agent="router_purpose", model=client.fast.model, thinking_level=client.fast.thinking_level,
                prompt_version=template.version, system_instruction=template.system_instruction,
                user_message=template.render({"state_json": state}),
                output_model=RouterOutput, deadline_ms=GEMINI_ROUTER_DEADLINE_MS,
                mock_primary_text=state.get("utterance", ""), mock_scenario="eval",
                preview=state.get("utterance", ""))), GEMINI_ROUTER_DEADLINE_MS / 1000)
            if result.status != "ok" or result.output is None:
                return None, result.latency_ms, "timeout" if result.status == "timeout" else "error"
            output = RouterOutput.model_validate(result.output.model_dump())
            return {s: float(getattr(output, s)) for s in SPECIALISTS}, result.latency_ms, "ok"
        except TimeoutError:
            status = "timeout"
        except Exception:
            status = "error"
        return None, round((time.perf_counter() - started) * 1000), status

    async def warm_up(self) -> tuple[dict[str, float] | None, int, str]:
        async with self._warm_lock:
            if self._warm_result is None:
                self._warm_result = await self.route({"utterance": "Hello."})
        return self._warm_result

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
