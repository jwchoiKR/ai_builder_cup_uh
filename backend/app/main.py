"""FastAPI app. Run: `uv run uvicorn app.main:create_app --factory` from backend/.

The static frontend build is mounted here in phase P3.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import audio_ws, demo, events_sse, operator, sessions, viewer
from .api.errors import install_error_handlers
from .clock import Clock
from .config import REPO_DIR, Settings, get_settings
from .context import AppContext, build_context, get_ctx
from .logic.catalog import Catalog
from .providers.llm import LLMBackend

log = logging.getLogger(__name__)

meta = APIRouter()


@meta.get("/health")
async def health(ctx: AppContext = Depends(get_ctx)) -> dict:
    s = ctx.settings
    return {
        "status": "ok",
        "app_env": s.APP_ENV,
        "providers": {
            "llm": ctx.llm.backend.name,
            "stt": s.STT_PROVIDER,
            "store": ctx.store.name,
            "retriever": s.RETRIEVER,
        },
        "models": {
            "location": s.LLM_LOCATION,
            "fast": {"id": ctx.llm.fast.model, "thinking": ctx.llm.fast.thinking_level},
            "quality": {"id": ctx.llm.quality.model, "thinking": ctx.llm.quality.thinking_level},
            "composer": {"id": ctx.llm.composer.model, "thinking": ctx.llm.composer.thinking_level},
            "facts": {"id": ctx.llm.facts.model, "thinking": ctx.llm.facts.thinking_level},  # D-246
            "agent_thinking": {name: getattr(ctx.llm, name).thinking_level  # D-128
                               for name in ("compliance", "context", "facts", "triage")},
            "warmup": ctx.llm.warmup_status,
        },
        "judge_mode": s.JUDGE_MODE,
        "prompts": {name: t.version for name, t in ctx.prompts.items()},
        "demo_tools_enabled": s.DEMO_TOOLS_ENABLED,
        "viewer_input_enabled": s.VIEWER_INPUT_ENABLED,
    }


@meta.get("/catalog")
async def catalog(session: str | None = None, ctx: AppContext = Depends(get_ctx)) -> dict:
    # D-230: with ?session=<sid>, that session's catalog (an onboarded release's product, brand and prices), not the
    # server's shipped one
    if session:
        rt = await ctx.runtimes.get(session)
        pack, cat = rt.pack, rt.catalog
    else:
        pack = ctx.pack
        cat = Catalog(pack)
    products = []
    for p in pack.products.products:
        d = p.model_dump(mode="json")
        d["list_price_display"] = cat.money(p.list_price)
        d["live_price_display"] = cat.money(p.live_price)
        if p.variants:  # D-281: with several sizes no single price or size is "the" one on screen
            first = f" ({p.variants[0].label})"
            d["list_price_display"] += first
            d["live_price_display"] += first
            d["variants_display"] = [f"{v.label}: {cat.money(v.live_price)}" for v in p.variants]
        products.append(d)
    promos = []
    for promo in pack.promos.promos:
        d = promo.model_dump(mode="json")
        d["promo_prices_display"] = {k: cat.money(v) for k, v in promo.promo_prices.items()}
        promos.append(d)
    return {
        "brand": pack.products.brand,
        "currency": pack.products.currency,
        "currency_symbol": pack.products.currency_symbol,
        "products": products,
        "set_offers": [
            {**s.model_dump(mode="json"), "live_price_display": cat.money(s.live_price),
             "promo_prices_display": {p.promo_id: cat.money(p.promo_prices[s.set_id])
                                      for p in pack.promos.promos if s.set_id in p.promo_prices}}
            for s in pack.products.set_offers
        ],
        "promos": promos,
        "runsheets": [rs.model_dump(mode="json") for rs in pack.runsheets.values()],
        "rules": [{"rule_id": r.rule_id, "title": r.title, "severity": r.severity, "source_ref": r.source_ref,
                   "source_id": r.source_id} for r in pack.rules.rules],
        "policy_pdf_url": "/api/files/policy",
        "intents": [i.model_dump(mode="json") for i in pack.intents.intents],
        "passages": {p.passage_id: {"product_id": p.product_id, "doc": p.doc, "section": p.section, "text": p.text}
                     for p in pack.passages},
        "notices": pack.notices.model_dump(mode="json"),
    }


@meta.get("/files/policy")
async def policy_pdf(ctx: AppContext = Depends(get_ctx)) -> FileResponse:
    src = next(s for s in ctx.pack.rules.sources if s.source_id == "ASEAN_APPENDIX_III")
    return FileResponse(ctx.settings.data_path / "policy" / Path(src.file).name, media_type="application/pdf")


def create_app(
    settings: Settings | None = None,
    *,
    clock: Clock | None = None,
    llm_backend: LLMBackend | None = None,
    scheduler=None,
) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # Built eagerly: a broken data pack or prompt file stops the app at startup.
    ctx = build_context(settings, clock=clock, llm_backend=llm_backend, scheduler=scheduler)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        warmup = asyncio.create_task(ctx.llm.warm_up())
        armor_warmup = asyncio.create_task(ctx.armor.warm_up())
        try:
            yield
        finally:
            warmup.cancel()
            armor_warmup.cancel()
            ctx.runtimes.shutdown()
            ctx.scheduler.shutdown()
            if hasattr(ctx.store, "aclose"):  # D-354: SIGTERM: queued Firestore writes go out before the exit
                await ctx.store.aclose()
            await ctx.llm.aclose()

    app = FastAPI(title="LIVE / Studio", version="0.1.0", lifespan=lifespan)
    app.state.ctx = ctx
    install_error_handlers(app)
    for router in (meta, sessions.router, events_sse.router, viewer.router, operator.router, demo.router,
                   audio_ws.router, *_optional_routers()):
        app.include_router(router, prefix="/api")
    _mount_frontend(app)
    return app


def _optional_routers() -> list[APIRouter]:
    """Setup and summary routers (phase P4) are included when their modules exist."""
    import importlib

    out = []
    for name in ("setup", "summary", "onboarding", "testdrive"):
        try:
            out.append(importlib.import_module(f"app.api.{name}").router)
        except ModuleNotFoundError as e:
            if e.name != f"app.api.{name}":
                raise
    return out


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built frontend (frontend/dist) with SPA fallback, if it exists (§4.2)."""
    dist = REPO_DIR / "frontend" / "dist"
    if not (dist / "index.html").is_file():
        return
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise StarletteHTTPException(404, "Not Found")
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")
