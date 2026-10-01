"""LLM provider (DEV_SPEC §7.1, verified in docs/VERIFIED.md items 1-3).

`LLMClient.call()` enforces the agent deadline with asyncio.wait_for, retries once on HTTP 5xx
only (never on timeout), validates the JSON reply with the agent's pydantic model and writes an
audit record. Any failure is returned as a status; it never raises to the caller.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generic, Literal, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from ..clock import Clock
from ..config import BACKEND_DIR, Settings
from ..ids import Ids
from ..models.session import AgentCall

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
Status = Literal["ok", "timeout", "error", "invalid"]

MOCK_FIXTURES_DIR = BACKEND_DIR / "tests" / "fixtures" / "llm"
WARMUP_TIMEOUT_MS = 10_000


@dataclass
class AgentResult(Generic[T]):
    status: Status
    output: T | None
    latency_ms: int
    call_id: str
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)  # model_version, usage, finish_reason


@dataclass
class LLMRequest(Generic[T]):
    agent: str
    model: str
    thinking_level: str
    prompt_version: str
    system_instruction: str
    user_message: str
    output_model: type[T]
    deadline_ms: int
    session_id: str | None = None
    # Mock lookup (§7.1): primary text and scenario tag; fallback builds an output for unit tests.
    mock_primary_text: str = ""
    mock_scenario: str = "default"
    mock_fallback: Callable[["LLMRequest"], dict | None] | None = None
    # §14.2 symbolic ids: encode replaces runtime ids before a fixture is saved, decode resolves
    # them against the current input lists when a fixture is replayed.
    fixture_encode: Callable[[dict], dict] | None = None
    fixture_decode: Callable[[dict], dict] | None = None
    preview: str | None = None  # human-readable input for the audit log


@dataclass
class RawReply:
    text: str
    model_version: str | None = None
    usage: dict[str, Any] | None = None
    finish_reason: str | None = None


class LLMError(Exception):
    """Non-retryable failure (4xx, empty reply, missing fixture...)."""


class LLMServerError(LLMError):
    """HTTP 5xx: retried once."""


class LLMTimeout(Exception):
    pass


class LLMBackend(Protocol):
    name: str

    async def generate(self, req: LLMRequest, timeout_ms: int) -> RawReply: ...
    async def warm_up(self, model: str, timeout_ms: int) -> None: ...
    async def aclose(self) -> None: ...


# ---- mock ----------------------------------------------------------------------------------------


def normalise_primary_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def mock_key(agent: str, primary_text: str, scenario: str) -> str:
    return hashlib.sha1(f"{agent}|{normalise_primary_text(primary_text)}|{scenario}".encode()).hexdigest()


class MockBackend:
    """Canned outputs from tests/fixtures/llm/<agent>/<key>.json (§7.1, §14.2)."""

    name = "mock"

    def __init__(self, fixtures_dir: Path = MOCK_FIXTURES_DIR) -> None:
        self.fixtures_dir = fixtures_dir

    def fixture_path(self, agent: str, primary_text: str, scenario: str) -> Path:
        return self.fixtures_dir / agent / f"{mock_key(agent, primary_text, scenario)}.json"

    async def generate(self, req: LLMRequest, timeout_ms: int) -> RawReply:
        for scenario in dict.fromkeys((req.mock_scenario, "default")):
            path = self.fixture_path(req.agent, req.mock_primary_text, scenario)
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                if req.fixture_decode is not None:
                    text = json.dumps(req.fixture_decode(json.loads(text)))
                return RawReply(text, model_version=f"mock:{scenario}")
        if req.mock_fallback is not None:
            out = req.mock_fallback(req)
            if out is not None:
                return RawReply(json.dumps(out), model_version="mock:fallback")
        raise LLMError(f"no mock fixture for {req.agent} (scenario {req.mock_scenario!r}) and no fallback")

    async def warm_up(self, model: str, timeout_ms: int) -> None:
        return None

    async def aclose(self) -> None:
        return None


class RecordingBackend:
    """Wraps a real backend and stores every valid reply as a mock fixture (§14.2)."""

    def __init__(self, inner: LLMBackend, fixtures_dir: Path = MOCK_FIXTURES_DIR) -> None:
        self.inner = inner
        self.name = f"{inner.name}+record"
        self.mock = MockBackend(fixtures_dir)
        self.recorded: list[Path] = []

    async def generate(self, req: LLMRequest, timeout_ms: int) -> RawReply:
        reply = await self.inner.generate(req, timeout_ms)
        try:
            data = req.output_model.model_validate_json(reply.text).model_dump(mode="json")
        except ValidationError:
            return reply  # invalid replies are not recorded
        if req.fixture_encode is not None:
            data = req.fixture_encode(data)
        path = self.mock.fixture_path(req.agent, req.mock_primary_text, req.mock_scenario)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        self.recorded.append(path)
        return reply

    async def warm_up(self, model: str, timeout_ms: int) -> None:
        await self.inner.warm_up(model, timeout_ms)

    async def aclose(self) -> None:
        await self.inner.aclose()


# ---- Vertex AI -------------------------------------------------------------------------------------


def vertex_config(req: LLMRequest, timeout_ms: int, schema: dict):
    """Request config for google-genai (field names verified, docs/VERIFIED.md item 2).

    - response_json_schema (not response_schema): keeps `dict` fields and our exact JSON Schema;
    - no temperature: ignored by the configured models, Google advises the default (D-008);
    - no HttpOptions.timeout: it also sends X-Server-Timeout, with which Vertex answered 504
      DEADLINE_EXCEEDED after ~1.4 s for a 2.5 s deadline (D-047). The deadline is enforced by
      asyncio.wait_for, whose cancellation closes the request (VERIFIED item 3). SDK retries stay off.
    """
    from google.genai import types

    return types.GenerateContentConfig(
        system_instruction=req.system_instruction,
        response_mime_type="application/json",
        response_json_schema=schema,
        thinking_config=types.ThinkingConfig(thinking_level=req.thinking_level),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


class VertexBackend:
    name = "vertex"

    def __init__(self, project: str, location: str) -> None:
        from google import genai

        # `enterprise=True` is the current name of the legacy `vertexai=True` flag (VERIFIED item 2).
        self._client = genai.Client(enterprise=True, project=project, location=location)
        self._schemas: dict[type, dict] = {}

    def _schema(self, model: type[BaseModel]) -> dict:
        if model not in self._schemas:
            self._schemas[model] = model.model_json_schema()
        return self._schemas[model]

    async def generate(self, req: LLMRequest, timeout_ms: int) -> RawReply:
        import httpx
        from google.genai import errors

        config = vertex_config(req, timeout_ms, self._schema(req.output_model))
        try:
            resp = await self._client.aio.models.generate_content(
                model=req.model, contents=req.user_message, config=config
            )
        except errors.ServerError as e:
            if e.code == 504 or e.status == "DEADLINE_EXCEEDED":
                # The server enforced our own deadline (X-Server-Timeout): a timeout, never retried.
                raise LLMTimeout(f"{e.code} {e.status}") from e
            raise LLMServerError(f"{e.code} {e.status}: {e.message}") from e
        except errors.APIError as e:
            raise LLMError(f"{e.code} {e.status}: {e.message}") from e
        except httpx.TimeoutException as e:
            raise LLMTimeout(type(e).__name__) from e
        except httpx.HTTPError as e:
            raise LLMError(f"{type(e).__name__}: {e}") from e
        finish = str(resp.candidates[0].finish_reason) if resp.candidates else None
        text = resp.text
        if not text:
            raise LLMError(f"empty reply (finish_reason={finish})")
        u = resp.usage_metadata
        usage = None if u is None else {
            "prompt": u.prompt_token_count, "output": u.candidates_token_count,
            "thoughts": u.thoughts_token_count, "cached": u.cached_content_token_count,
        }
        return RawReply(text, resp.model_version, usage, finish)

    async def warm_up(self, model: str, timeout_ms: int) -> None:
        from google.genai import types

        await self._client.aio.models.generate_content(
            model=model,
            contents="Reply with OK.",
            config=types.GenerateContentConfig(
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                http_options=types.HttpOptions(timeout=timeout_ms),
            ),
        )

    async def aclose(self) -> None:
        await self._client.aio.aclose()


# ---- client --------------------------------------------------------------------------------------


class AuditSink(Protocol):
    async def record(self, call: AgentCall, session_id: str | None) -> None: ...


@dataclass(frozen=True)
class ModelSpec:
    model: str
    thinking_level: str


class LLMClient:
    def __init__(
        self,
        backend: LLMBackend,
        settings: Settings,
        clock: Clock,
        ids: Ids,
        audit: AuditSink | None = None,
    ) -> None:
        self.backend = backend
        self._settings = settings
        self._clock = clock
        self._ids = ids
        self._audit = audit
        self.fast = ModelSpec(settings.LLM_FAST_MODEL, settings.LLM_FAST_THINKING)
        self.quality = ModelSpec(settings.LLM_QUALITY_MODEL, settings.LLM_QUALITY_THINKING)  # Brief, Summary
        self.composer = ModelSpec(settings.LLM_QUALITY_MODEL, settings.COMPOSER_THINKING)
        self.warmup_status: dict[str, str] = {}

    async def call(self, req: LLMRequest[T]) -> AgentResult[T]:
        call_id = self._ids.new("call_", req.session_id)
        started_at = self._clock.now_ms()
        t0 = time.perf_counter()
        output: T | None = None
        logged_output: dict | None = None
        error: str | None = None
        meta: dict[str, Any] = {}
        try:
            raw = await asyncio.wait_for(self._generate(req, t0), timeout=req.deadline_ms / 1000)
            meta = {"model_version": raw.model_version, "usage": raw.usage, "finish_reason": raw.finish_reason}
            try:
                output = req.output_model.model_validate_json(raw.text)
                logged_output = output.model_dump(mode="json")
                status: Status = "ok"
            except ValidationError as e:
                status, error = "invalid", _short_validation_error(e)
                logged_output = {"raw": raw.text[:4000]}
        except TimeoutError:
            status, error = "timeout", f"deadline {req.deadline_ms} ms"
        except LLMTimeout as e:
            status, error = "timeout", f"{e} (deadline {req.deadline_ms} ms)"
        except LLMError as e:
            status, error = "error", str(e)[:500]
        except Exception as e:  # noqa: BLE001 - fail safe: never raise into a pipeline (§3.2)
            log.exception("LLM call %s failed", req.agent)
            status, error = "error", f"{type(e).__name__}: {e}"[:500]
        latency_ms = round((time.perf_counter() - t0) * 1000)
        log.info("agent=%s model=%s status=%s latency_ms=%d", req.agent, req.model, status, latency_ms)
        call = AgentCall(
            call_id=call_id, agent=req.agent, model=req.model, prompt_version=req.prompt_version,
            started_at=started_at, latency_ms=latency_ms, status=status,
            input_hash=hashlib.sha1(f"{req.prompt_version}\n{req.user_message}".encode()).hexdigest(),
            input_preview=(req.preview or req.mock_primary_text or req.user_message)[:300],
            output=logged_output, error=error,
        )
        if self._audit is not None:
            try:
                await self._audit.record(call, req.session_id)
            except Exception:  # noqa: BLE001 - audit must not break the call
                log.exception("audit record failed for %s", call_id)
        return AgentResult(status, output, latency_ms, call_id, error, meta)

    async def _generate(self, req: LLMRequest, t0: float) -> RawReply:
        attempts = 1 + max(0, self._settings.LLM_RETRY_ON_5XX)
        for attempt in range(1, attempts + 1):
            remaining_ms = req.deadline_ms - (time.perf_counter() - t0) * 1000
            if remaining_ms <= 0:
                raise LLMTimeout("deadline reached before retry")
            try:
                return await self.backend.generate(req, int(remaining_ms))
            except LLMServerError as e:
                if attempt == attempts:
                    raise
                log.warning("agent=%s 5xx (%s), retry %d/%d", req.agent, e, attempt, attempts - 1)
        raise AssertionError("unreachable")

    async def warm_up(self) -> dict[str, str]:
        """One tiny call per model so the first real call is not a cold start. Not audited."""
        models = list(dict.fromkeys((self.fast.model, self.quality.model)))

        async def one(model: str) -> None:
            t0 = time.perf_counter()
            try:
                await asyncio.wait_for(self.backend.warm_up(model, WARMUP_TIMEOUT_MS), WARMUP_TIMEOUT_MS / 1000)
                self.warmup_status[model] = f"ok {round((time.perf_counter() - t0) * 1000)} ms"
            except Exception as e:  # noqa: BLE001
                self.warmup_status[model] = f"failed: {type(e).__name__}: {str(e)[:200]}"
                log.warning("warm-up of %s failed: %s %s", model, type(e).__name__, e)

        for m in models:
            self.warmup_status.setdefault(m, "pending")
        await asyncio.gather(*(one(m) for m in models))
        return dict(self.warmup_status)

    async def aclose(self) -> None:
        await self.backend.aclose()


def _short_validation_error(e: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()[:5])[:500]


def make_backend(settings: Settings) -> LLMBackend:
    if settings.LLM_PROVIDER == "mock":
        return MockBackend()
    return VertexBackend(settings.GCP_PROJECT, settings.LLM_LOCATION)
