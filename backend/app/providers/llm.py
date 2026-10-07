"""LLM provider (DEV_SPEC §7.1, verified in docs/VERIFIED.md items 1-3).

`LLMClient.call()` enforces the agent deadline with asyncio.wait_for, retries once on HTTP 5xx
only (never on timeout), validates the JSON reply with the agent's pydantic model and writes an
audit record. Any failure is returned as a status; it never raises to the caller. D-184: the judges and the
fact checker send one identical second request when the first has not answered after JUDGE_HEDGE_MS.
"""
from __future__ import annotations

import asyncio
import atexit
import hashlib
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
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
    cache_prefix: str = ""  # exact static prefix of user_message; retain full text for fallback
    cache_ttl_sec: int | None = None
    parts: tuple = ()  # P0 onboarding: (bytes, mime type) files sent before user_message (Vertex only)
    # D-247 arm FD: (bytes, mime type) files cached with the system instruction (before cache_prefix); sent
    # uncached before user_message while the cache is not ready
    cache_parts: tuple = ()
    temperature: float | None = None  # D-302: a vote run's sampling temperature; None = the model's default
    seed: int | None = None  # D-314: the sampling seed; None = not sent
    hedge: bool = True  # D-302: False sends no second request (vote runs)


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
        **({"temperature": req.temperature} if req.temperature is not None else {}),  # D-302 vote runs
        **({"seed": req.seed} if req.seed is not None else {}),  # D-314
    )


def _log_cache_failure(task: asyncio.Task, agent: str) -> None:
    if task.cancelled():
        return
    e = task.exception()
    if e is not None:
        log.warning("context cache creation failed for %s: %s: %s", agent, type(e).__name__, e)


@dataclass
class _ContextCache:
    task: asyncio.Task | None = None  # the one creation in flight (single-flight), never cancelled by a caller
    name: str | None = None
    expires_at: float = 0
    eligible: bool | None = None


class VertexBackend:
    name = "vertex"

    def __init__(self, project: str, location: str, *, context_cache: bool = False,
                 cache_ttl_sec: int = 3600) -> None:
        from google import genai

        # `enterprise=True` is the current name of the legacy `vertexai=True` flag (VERIFIED item 2).
        self._client = genai.Client(enterprise=True, project=project, location=location)
        self._schemas: dict[type, dict] = {}
        self._context_cache = context_cache
        self._cache_ttl_sec = cache_ttl_sec
        self._caches: dict[str, _ContextCache] = {}

    def _cache_entry(self, req: LLMRequest) -> _ContextCache | None:
        if (not self._context_cache or not req.session_id or not (req.cache_prefix or req.cache_parts)
                or not req.user_message.startswith(req.cache_prefix)):
            return None
        # Vertex documents 4,096 tokens for Gemini 3, 2,048 for Gemini 2.
        if not re.match(r"gemini-[23]\.", req.model):
            return None
        # Content-addressed: sessions with the same pack share one cache (D-130; the session id was in
        # the key, so every new session, e.g. each eval case, created its own).
        key = hashlib.sha256(json.dumps([
            req.agent, req.model, req.prompt_version, req.system_instruction, req.cache_prefix,
            [hashlib.sha256(data).hexdigest() for data, _ in req.cache_parts],
        ], ensure_ascii=False).encode()).hexdigest()
        if key not in self._caches:
            # Bound local state without evicting an entry whose creation is in flight.
            if len(self._caches) >= 256:
                victim = next((k for k, v in self._caches.items() if v.task is None or v.task.done()), None)
                if victim is None:
                    return None
                del self._caches[victim]
            self._caches[key] = _ContextCache()
        return self._caches[key]

    def _cache_task(self, req: LLMRequest, entry: _ContextCache) -> asyncio.Task | None:
        """The creation of this entry's cache: running, or started now. None while a cache (or a known
        "not eligible" / "failed, retry later") is fresh."""
        if entry.expires_at > time.monotonic():
            return None
        if entry.task is None or entry.task.done():
            entry.task = asyncio.create_task(self._create_cache(req, entry), name=f"context-cache:{req.agent}")
            entry.task.add_done_callback(lambda t, agent=req.agent: _log_cache_failure(t, agent))
        return entry.task

    @staticmethod
    def _contents(req: LLMRequest, text: str):
        """The files (onboarding parts or cached parts), then the text."""
        from google.genai import types

        files = req.parts or req.cache_parts
        if not files:
            return text
        return [*(types.Part.from_bytes(data=data, mime_type=mime) for data, mime in files), *([text] if text else [])]

    async def warm_cache(self, req: LLMRequest) -> None:
        """D-247: create this request's context cache now (session start), so the first live call is cached."""
        entry = self._cache_entry(req)
        task = self._cache_task(req, entry) if entry is not None else None
        if task is not None:
            await asyncio.shield(task)

    async def _create_cache(self, req: LLMRequest, entry: _ContextCache) -> str | None:
        from google.genai import types

        entry.name = None
        ttl = max(60, req.cache_ttl_sec if req.cache_ttl_sec is not None else self._cache_ttl_sec)
        try:
            if entry.eligible is None:
                count = await self._client.aio.models.count_tokens(
                    model=req.model, contents=self._contents(req, req.cache_prefix),
                    config=types.CountTokensConfig(system_instruction=req.system_instruction),
                )
                minimum = 4096 if req.model.startswith("gemini-3.") else 2048
                if count.total_tokens is None:
                    raise LLMError("token count returned no total")
                entry.eligible = count.total_tokens >= minimum
            if not entry.eligible:
                entry.expires_at = time.monotonic() + ttl
                return None
            started = time.monotonic()
            cached = await self._client.aio.caches.create(
                model=req.model,
                config=types.CreateCachedContentConfig(
                    system_instruction=req.system_instruction, contents=self._contents(req, req.cache_prefix),
                    ttl=f"{ttl}s",
                ),
            )
            if not cached.name:
                raise LLMError("cache creation returned no name")
        except Exception:
            entry.expires_at = time.monotonic() + 60  # cool down, then try again
            raise
        entry.name = cached.name
        entry.expires_at = started + ttl
        return entry.name

    def _schema(self, model: type[BaseModel]) -> dict:
        if model not in self._schemas:
            self._schemas[model] = model.model_json_schema()
        return self._schemas[model]

    async def generate(self, req: LLMRequest, timeout_ms: int) -> RawReply:
        import httpx
        from google.genai import errors, types

        config = vertex_config(req, timeout_ms, self._schema(req.output_model))
        entry = self._cache_entry(req)
        cache_name = None
        if entry is not None:
            task = self._cache_task(req, entry)
            if task is None:
                cache_name = entry.name
            else:
                # D-130: wait a little for the creation, but never cancel it: if this call's budget runs
                # out, it goes uncached and the cache is ready for the next calls. (wait_for used to
                # cancel the creation itself, so a creation slower than the budget never finished.)
                try:
                    cache_name = await asyncio.wait_for(asyncio.shield(task), timeout=min(1.0, timeout_ms / 5000))
                except asyncio.TimeoutError:
                    log.info("context cache for %s still being created; this call runs uncached", req.agent)
                except Exception:  # the reason is logged once by the task's done callback
                    cache_name = None
        try:
            if cache_name:
                cached_config = config.model_copy(update={"system_instruction": None, "cached_content": cache_name})
                try:
                    resp = await self._client.aio.models.generate_content(
                        model=req.model, contents=req.user_message[len(req.cache_prefix):], config=cached_config,
                    )
                except Exception:  # fall back once; normal uncached error/retry handling stays below
                    entry.name, entry.expires_at = None, time.monotonic() + 60
                    log.warning("context cache use failed for %s", req.agent)
                    resp = await self._client.aio.models.generate_content(
                        model=req.model, contents=self._contents(req, req.user_message), config=config,
                    )
            elif req.parts or req.cache_parts:  # P0 onboarding / D-247: whole files (PDF, images, text)
                resp = await self._client.aio.models.generate_content(
                    model=req.model, contents=self._contents(req, req.user_message), config=config
                )
            else:
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
        for entry in self._caches.values():
            if entry.task is not None and not entry.task.done():
                entry.task.cancel()
        self._caches.clear()  # remote caches expire at their TTL
        await self._client.aio.aclose()


# ---- client --------------------------------------------------------------------------------------


class AuditSink(Protocol):
    async def record(self, call: AgentCall, session_id: str | None) -> None: ...


# D-187: calls and tokens per agent in this process, to compare the cost of the design arms
USAGE: dict[str, dict[str, int]] = {}
_USAGE_FIELDS = ("prompt", "output", "thoughts", "cached")


def failure_kind(status: str, error: str | None) -> str | None:
    """D-306: what kind of failure a call was, to tell infrastructure from logic: a client-side deadline, the server's
    504 or 429 (Google's shared capacity), or anything else."""
    if status == "ok":
        return None
    if status == "timeout":
        return "client_timeout"
    e = (error or "").lower()
    if "504" in e or "deadline_exceeded" in e or "deadline exceeded" in e:
        return "http_504"
    if "429" in e or "resource_exhausted" in e or "resource exhausted" in e:
        return "http_429"
    return "other_error"


def add_usage(agent: str, usage: dict | None) -> None:
    row = USAGE.setdefault(agent, {"calls": 0, **{k: 0 for k in _USAGE_FIELDS}})
    row["calls"] += 1
    for k in _USAGE_FIELDS:
        row[k] += int((usage or {}).get(k) or 0)


def write_usage_report(path: str) -> None:
    """D-187: the per-agent totals and their sum as JSON."""
    total = {"calls": 0, **{k: 0 for k in _USAGE_FIELDS}}
    for row in USAGE.values():
        for k in total:
            total[k] += row[k]
    from . import rule_search  # D-194 arm E: retrieval latency and the rule ids per line, for recall

    report = {"agents": USAGE, "total": total} | ({"rule_search": rule_search.summary()}
                                                  if rule_search.STATS["calls"] else {})
    Path(path).write_text(json.dumps(report, indent=1), encoding="utf-8")


# D-184: the agents on the 3 s alert path, whose single slow call must not be a silent miss
# D-301: "verifier" only when HEDGED_AGENTS names it (not in the default list)
SAMPLED_AGENTS = frozenset({"compliance_judge", "fact_checker", "context_judge"})  # D-314
HEDGED_AGENTS = frozenset({"compliance_judge", "context_judge", "utterance_judge", "judge_single", "fact_checker",
                           "verifier"})


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
        # D-128: the fast model with a thinking level per agent
        # D-309 JUDGE_ARM=single: the compliance judge and the fact checker on the strong model
        single = getattr(settings, "JUDGE_ARM", "") == "single"
        strong = getattr(settings, "SINGLE_MODEL", settings.LLM_QUALITY_MODEL)
        strong_thinking = getattr(settings, "SINGLE_THINKING", "LOW")
        self.compliance = ModelSpec(getattr(settings, "COMPLIANCE_MODEL", "") or (strong if single else settings.LLM_FAST_MODEL),
                                    strong_thinking if single else settings.COMPLIANCE_THINKING)
        self.context = ModelSpec(settings.LLM_FAST_MODEL, settings.CONTEXT_THINKING)
        facts_thinking = getattr(settings, "SINGLE_FACTS_THINKING", "") or strong_thinking  # D-311
        self.facts = ModelSpec(settings.FACTS_MODEL or (strong if single else settings.LLM_FAST_MODEL),
                               facts_thinking if single else settings.FACTS_THINKING)  # D-246; D-309
        self.triage = ModelSpec(settings.LLM_FAST_MODEL, settings.TRIAGE_THINKING)
        self.brief = ModelSpec(settings.BRIEF_MODEL or settings.LLM_QUALITY_MODEL, settings.BRIEF_THINKING)  # D-265
        self.verify = ModelSpec(getattr(settings, "VERIFY_MODEL", settings.LLM_QUALITY_MODEL),
                                getattr(settings, "VERIFY_THINKING", "LOW"))  # D-300
        self.warmup_status: dict[str, str] = {}
        # D-184: per agent, calls that sent a second request, and how many of those the second one answered
        self.hedges: dict[str, dict[str, int]] = {}
        # D-287: HEDGED_AGENTS narrows the second request to some of the alert-path agents (cost); empty = all
        names = [x.strip() for x in getattr(settings, "HEDGED_AGENTS", "").split(",") if x.strip()]
        self._hedged_agents = (frozenset(a for a in HEDGED_AGENTS if any(a.startswith(n) for n in names))
                               if names else HEDGED_AGENTS)
        # D-292: HEDGE_DELAYS gives some agents a later second request (the slow tail only)
        self._hedge_delays: dict[str, int] = {}
        for item in getattr(settings, "HEDGE_DELAYS", "").split(","):
            if "=" in item:
                name, ms = (x.strip() for x in item.split("=", 1))
                for a in HEDGED_AGENTS:
                    if a.startswith(name):
                        self._hedge_delays[a] = int(ms)
        if settings.LLM_USAGE_REPORT:
            atexit.register(write_usage_report, settings.LLM_USAGE_REPORT)

    @property
    def design_arm(self) -> str:
        """D-187: the design arm this process runs."""
        return self._settings.DESIGN_ARM

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def prompts_path(self) -> Path:
        return self._settings.prompts_path

    async def call(self, req: LLMRequest[T]) -> AgentResult[T]:
        if req.agent in SAMPLED_AGENTS:  # D-314: the live judges' sampling, when set (a vote run keeps its own)
            t, s = self._settings.JUDGE_TEMPERATURE.strip(), self._settings.JUDGE_SEED.strip()
            req = replace(req, temperature=float(t) if t and req.temperature is None else req.temperature,
                          seed=int(s) if s and req.seed is None else req.seed)
        call_id = self._ids.new("call_", req.session_id)
        started_at = self._clock.now_ms()
        t0 = time.perf_counter()
        output: T | None = None
        logged_output: dict | None = None
        error: str | None = None
        meta: dict[str, Any] = {}
        try:
            hedge_ms = (self._hedge_delays.get(req.agent, self._settings.JUDGE_HEDGE_MS)
                        if req.agent in self._hedged_agents and req.hedge else 0)
            work = self._hedged(req, t0, hedge_ms) if 0 < hedge_ms < req.deadline_ms else self._generate(req, t0)
            raw = await asyncio.wait_for(work, timeout=req.deadline_ms / 1000)
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
        usage = meta.get("usage")
        add_usage(req.agent, usage)
        log.info("agent=%s model=%s status=%s latency_ms=%d tokens=%s", req.agent, req.model, status, latency_ms,
                 "/".join(str((usage or {}).get(k) or 0) for k in _USAGE_FIELDS))  # prompt/output/thoughts/cached
        call = AgentCall(
            call_id=call_id, agent=req.agent, model=req.model, prompt_version=req.prompt_version,
            started_at=started_at, latency_ms=latency_ms, status=status,
            input_hash=hashlib.sha1(f"{req.prompt_version}\n{req.user_message}".encode()).hexdigest(),
            input_preview=(req.preview or req.mock_primary_text or req.user_message)[:300],
            output=logged_output, error=error, usage=usage, failure=failure_kind(status, error),
            temperature=req.temperature, seed=req.seed,
        )
        meta["failure"] = call.failure
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

    async def _hedged(self, req: LLMRequest, t0: float, hedge_ms: int) -> RawReply:
        """D-184: the first request; if it has not answered after `hedge_ms`, one identical second request. The first
        reply wins and the other is cancelled; an error from one waits for the other."""
        first = asyncio.ensure_future(self._generate(req, t0))
        done, _ = await asyncio.wait({first}, timeout=hedge_ms / 1000)
        if done:
            return first.result()
        second = asyncio.ensure_future(self._generate(req, t0))
        count = self.hedges.setdefault(req.agent, {"hedged": 0, "second_won": 0})
        count["hedged"] += 1
        log.info("agent=%s no answer after %d ms: second request sent", req.agent, hedge_ms)
        pending = {first, second}
        error: BaseException | None = None
        try:
            while pending:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    if task.exception() is None:
                        if task is second:
                            count["second_won"] += 1
                        return task.result()
                    error = task.exception()
            assert error is not None
            raise error
        finally:
            for task in (first, second):
                if not task.done():
                    task.cancel()

    async def warm_cache(self, req: LLMRequest) -> None:
        """D-247: create a request's context cache ahead of its first call (backends without caches: nothing)."""
        warm = getattr(self.backend, "warm_cache", None)
        if warm is not None:
            try:
                await warm(req)
            except Exception as e:  # noqa: BLE001 - the calls still run, uncached
                log.warning("context cache warm-up for %s failed: %s: %s", req.agent, type(e).__name__, e)

    async def warm_up(self) -> dict[str, str]:
        """One tiny call per model so the first real call is not a cold start. Not audited."""
        models = list(dict.fromkeys((self.fast.model, self.facts.model, self.quality.model)))

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
    return VertexBackend(settings.GCP_PROJECT, settings.LLM_LOCATION,
                         context_cache=settings.LLM_CONTEXT_CACHE,
                         cache_ttl_sec=settings.LLM_CONTEXT_CACHE_TTL_SEC)
