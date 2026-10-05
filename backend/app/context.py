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
    _packs: dict = field(default_factory=dict, init=False, repr=False)

    def pack_for(self, market: str, lang: str, release_id: str | None = None) -> tuple[DataPack, Reflex]:
        """D-142: the data pack and reflex of one (market, language), loaded once. The settings' pair is
        `pack`/`reflex`; others load from the same data folder (DataPackError when not offered).
        D-218: with a release, that onboarded product's pack on the same market and language; its passages join the
        retriever's index once."""
        if release_id is not None:
            rkey = (market.upper(), lang, release_id)
            if rkey not in self._packs:
                from .onboarding.release import load_release_full, release_pack

                base, reflex = self.pack_for(market, lang)
                record, translations = load_release_full(self.settings.onboarding_path, release_id)
                pack = release_pack(base, record, release_id, self.settings.onboarding_path, translations,
                                    self.settings.FACT_MODE)
                if pack.rules is not base.rules:  # D-227: no law pack for its category, so no reflex phrases either
                    reflex = Reflex(pack.rules, pack.lexicon)
                pid = pack.products.products[0].product_id
                self.retriever.replace_product(pid, pack.passages)
                self._packs[rkey] = (pack, reflex)
            return self._packs[rkey]
        key = (market.upper(), lang)
        if key not in self._packs:
            if key == (self.pack.market.market, self.pack.lang):
                self._packs[key] = (self.pack, self.reflex)
            else:
                pack = DataPack.load(self.settings.data_path, market, lang)
                self._packs[key] = (pack, Reflex(pack.rules, pack.lexicon))
        return self._packs[key]


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
    if settings.ONBOARDING_GCS_BUCKET:  # D-263: the bucket is the source of truth for onboarding state
        from .onboarding import storage

        storage.configure(settings.onboarding_path, storage.bucket_for(settings.ONBOARDING_GCS_BUCKET,
                                                                       settings.GCP_PROJECT))
    pack = DataPack.load(settings.data_path, settings.MARKET, settings.BROADCAST_LANGUAGE)
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
