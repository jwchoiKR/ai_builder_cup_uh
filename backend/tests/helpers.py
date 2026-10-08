"""Shared helpers for runtime-level tests: manual clock and scheduler, mock LLM."""
from __future__ import annotations

from pathlib import Path

from app.clock import ManualClock
from app.context import AppContext, build_context
from app.pipelines.comments import submit_comment
from app.pipelines.runtime import SessionRuntime, create_session
from app.providers.llm import LLMBackend, MockBackend
from app.scheduler import ManualScheduler

from .conftest import make_settings


def make_ctx(fixtures_dir: Path | None = None, backend: LLMBackend | None = None, **settings) -> AppContext:
    clock = ManualClock()
    backend = backend or (MockBackend(fixtures_dir) if fixtures_dir else MockBackend())
    comments_client = settings.pop("comments_client", None)  # COMMENTS_FIRESTORE=True: the fake Firestore client
    return build_context(make_settings(**settings), clock=clock, llm_backend=backend,
                         scheduler=ManualScheduler(clock), comments_client=comments_client)


async def live_runtime(ctx: AppContext, show_mode: str = "solo") -> SessionRuntime:
    s = await create_session(ctx, "daon_skincare_demo", show_mode)
    rt = await ctx.runtimes.get(s.session_id)
    await rt.start()
    await ctx.scheduler.advance(5000)  # past STREAM_GRACE_SEC, so comments have a context product
    return rt


async def say(rt: SessionRuntime, author: str, text: str, *, scenario: str = "default", wait: bool = True):
    c = await submit_comment(rt, author_id=f"u_{author.lower()}", author_name=author, text=text, source="script",
                             scenario=scenario)
    if wait:
        await rt.ctx.scheduler.idle()
    return c
