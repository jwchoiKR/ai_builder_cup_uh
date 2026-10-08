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
    return build_context(make_settings(**settings), clock=clock, llm_backend=backend,
                         scheduler=ManualScheduler(clock))


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


def text_pdf(text: str) -> bytes:
    """D-367: a one-page PDF whose text pypdf reads back (regulation originals are PDF only)."""
    lines = [x.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for x in text.splitlines()]
    stream = ("BT /F1 10 Tf 14 TL 20 800 Td " + " ".join(f"({x}) Tj T*" for x in lines) + " ET").encode("latin-1")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (i, o)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % x for x in offsets)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
