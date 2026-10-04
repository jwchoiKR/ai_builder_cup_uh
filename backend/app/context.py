"""Application context: one instance per process, built at startup (fails fast on bad data)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fastapi import Request

from .agents.inputs import BUILDERS
from .bus import HEARTBEAT_SEC, EventBus
from .clock import Clock, SystemClock
from .config import Settings
from .ids import Ids
from .logic.catalog import DataPack
from .logic.reflex import Reflex
from .models.session import AgentCall
from .providers.armor import make_armor
from .providers.llm import LLMBackend, LLMClient, make_backend
from .providers.prompts import PromptTemplate, load_prompts
from .providers.retriever import LocalRetriever, Retriever
from .providers.stt import make_stt
from .scheduler import AsyncScheduler, ManualScheduler
from .store import make_store
from .store.base import AGENT_CALLS_GLOBAL, Store, sub

if TYPE_CHECKING:
    from .pipelines.runtime import Runtimes


class StoreAudit:
    """Writes AgentCall rows and emits `agent.call` (operator debug panel, §7.1)."""

    def __init__(self, store: Store, bus: EventBus) -> None:
        self._store = store
        self._bus = bus

    async def record(self, call: AgentCall, session_id: str | None) -> None:
        if session_id is None:
            await self._store.put(AGENT_CALLS_GLOBAL, call.call_id, call)
            return
        await self._store.put(sub(session_id, "agent_calls"), call.call_id, call)
        await self._bus.emit(session_id, "agent.call", call)


@dataclass
class AppContext:
    settings: Settings
    clock: Clock
    ids: Ids
    pack: DataPack
    prompts: dict[str, PromptTemplate]
    store: Store
    bus: EventBus
    llm: LLMClient
    scheduler: AsyncScheduler | ManualScheduler
    retriever: Retriever
    reflex: Reflex
    runtimes: "Runtimes" = field(init=False)
    stt: object | None = None  # GoogleV2Stt, or None when STT_PROVIDER=mock
    armor: object | None = None  # D-125: Model Armor screening of comments (NoArmor when off)
    sse_heartbeat_sec: float = HEARTBEAT_SEC


def build_context(
    settings: Settings,
    *,
    clock: Clock | None = None,
    llm_backend: LLMBackend | None = None,
    scheduler: AsyncScheduler | ManualScheduler | None = None,
) -> AppContext:
    from .pipelines.runtime import Runtimes

    clock = clock or SystemClock()
    ids = Ids(clock, deterministic=settings.LLM_PROVIDER == "mock")
    pack = DataPack.load(settings.data_path, settings.MARKET, settings.BROADCAST_LANGUAGE)
    if not settings.STT_LANGUAGE:
        settings = settings.model_copy(update={"STT_LANGUAGE": pack.stt_language})
    prompts = load_prompts(settings.prompts_path, BUILDERS)
    store = make_store(settings)
    bus = EventBus(store, clock)
    llm = LLMClient(llm_backend or make_backend(settings), settings, clock, ids, StoreAudit(store, bus))
    if settings.RETRIEVER != "local":
        raise NotImplementedError("RETRIEVER=vertex_search is implemented in phase P6; use RETRIEVER=local")
    ctx = AppContext(
        settings=settings, clock=clock, ids=ids, pack=pack, prompts=prompts, store=store, bus=bus, llm=llm,
        scheduler=scheduler or AsyncScheduler(clock), retriever=LocalRetriever(pack.passages),
        reflex=Reflex(pack.rules, pack.lexicon),
        stt=make_stt(settings, clock),
        armor=make_armor(settings),
    )
    ctx.runtimes = Runtimes(ctx)
    return ctx


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx
