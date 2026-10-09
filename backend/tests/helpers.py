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
    firestore_client = settings.pop("firestore_client", None)  # STORE=firestore: the fake Firestore client (D-428)
    return build_context(make_settings(**settings), clock=clock, llm_backend=backend,
                         scheduler=ManualScheduler(clock), firestore_client=firestore_client)


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


def product_show(ctx: AppContext, info: dict, regulations: list[tuple[str, bytes]],
                 product_id: str = "prd_000000000001", regulation_id: str = "reg_000000000001") -> str:
    """A rebuilt-onboarding show without a bucket: the product's pack is built and cached on the context, and its
    regulation PDFs registered for the compliance judge. Returns the release id to create the session with."""
    from app.agents.originals import register_regulation
    from app.logic.reflex import Reflex
    from app.onboarding.product_show import product_pack, show_key

    key = show_key(product_id, regulation_id)
    market, lang = ctx.settings.MARKET, ctx.settings.BROADCAST_LANGUAGE
    pack = product_pack(ctx.pack_for(market, lang)[0], info, key)
    register_regulation(regulation_id, regulations)
    ctx.retriever.replace_product(product_id, pack.passages)
    ctx._packs[(market.upper(), lang, key)] = (pack, Reflex(pack.rules, pack.lexicon))
    return key
