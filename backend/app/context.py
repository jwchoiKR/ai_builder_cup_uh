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
from .logic.catalog import DataPack, DataPackError
from .logic.reflex import Reflex
from .models.session import AgentCall
from .providers.armor import make_armor
from .providers.llm import LLMBackend, LLMClient, make_backend
from .providers.prompts import PromptTemplate, load_prompts
from .providers.retriever import LocalRetriever, ProductDocumentRetriever, Retriever, VertexSearchRetriever
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
    answer_retriever: Retriever | None = None  # ANSWER_RETRIEVER=vertex_search; None = `retriever`
    stt: object | None = None  # GoogleV2Stt, or None when STT_PROVIDER=mock
    armor: object | None = None  # D-125: Model Armor screening of comments (NoArmor when off)
    sse_heartbeat_sec: float = HEARTBEAT_SEC
    _packs: dict = field(default_factory=dict, init=False, repr=False)

    def forget_release(self, release_id: str) -> None:
        """D-266: the next show from this release is built again (its brief has landed)."""
        for key in [k for k in self._packs if len(k) == 3 and (k[2] == release_id or
                                                              (isinstance(k[2], tuple) and release_id in k[2]))]:
            del self._packs[key]

    def pack_for(self, market: str, lang: str, release_id: str | tuple[str, ...] | None = None
                 ) -> tuple[DataPack, Reflex]:
        """D-142: the data pack and reflex of one (market, language), loaded once. The settings' pair is
        `pack`/`reflex`; others load from the same data folder (DataPackError when not offered).
        D-218: with a release, that onboarded product's pack on the same market and language; its passages join the
        retriever's index once."""
        if isinstance(release_id, tuple):  # D-279: a show of several releases, each built as on its own
            rkey = (market.upper(), lang, release_id)
            if rkey not in self._packs:
                from .onboarding.show import show_pack

                pack = show_pack([self.pack_for(market, lang, r)[0] for r in release_id], release_id)
                self._packs[rkey] = (pack, Reflex(pack.rules, pack.lexicon))
            return self._packs[rkey]
        if isinstance(release_id, str) and release_id.startswith("prd_"):
            # rebuilt onboarding: an approved product and its regulation PDF ("<product_id>:<regulation_id>")
            rkey = (market.upper(), lang, release_id)
            if rkey not in self._packs:
                from .onboarding.product_show import build

                pack = build(self.settings, self.pack_for(market, lang)[0], release_id)
                self.retriever.replace_product(pack.products.products[0].product_id, pack.passages)
                self._packs[rkey] = (pack, Reflex(pack.rules, pack.lexicon))
            return self._packs[rkey]
        if release_id is not None:
            raise DataPackError(f"unknown release {release_id!r}")
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
    firestore_client: object | None = None,
) -> AppContext:
    from .pipelines.runtime import Runtimes

    clock = clock or SystemClock()
    ids = Ids(clock, deterministic=settings.LLM_PROVIDER == "mock")
    if settings.JUDGE_MODE != "split3":
        # D-361 (D-358): JUDGE_MODE=split and single read the rule JSON; production judges only on the regulation
        # originals (split3). Those modes stay for the test suite (pinned) and the mock provider's recordings.
        from .agents import split_judges

        allowed = (settings.LLM_PROVIDER == "mock") if split_judges.LEGACY_RULES is None else split_judges.LEGACY_RULES
        if not allowed:
            raise ValueError(f"JUDGE_MODE={settings.JUDGE_MODE} reads the rule JSON; production runs split3 only "
                             "(D-358)")
    pack = DataPack.load(settings.data_path, settings.MARKET, settings.BROADCAST_LANGUAGE)
    prompts = load_prompts(settings.prompts_path, BUILDERS)
    store = make_store(settings, firestore_client=firestore_client)
    bus = EventBus(store, clock)
    llm = LLMClient(llm_backend or make_backend(settings), settings, clock, ids, StoreAudit(store, bus))
    ctx = AppContext(
        settings=settings, clock=clock, ids=ids, pack=pack, prompts=prompts, store=store, bus=bus, llm=llm,
        scheduler=scheduler or AsyncScheduler(clock), retriever=LocalRetriever(pack.passages),
        reflex=Reflex(pack.rules, pack.lexicon),
        stt=make_stt(settings, clock),
        armor=make_armor(settings),
        answer_retriever=_answer_retriever(settings),
    )
    ctx.runtimes = Runtimes(ctx)
    if hasattr(store, "on_loaded"):  # STORE=firestore: a session came back from Firestore (D-428)
        store.on_loaded = ctx.runtimes.session_loaded
    return ctx


def _answer_retriever(settings: Settings) -> Retriever | None:
    """The evidence of viewer answers (ANSWER_RETRIEVER=vertex_search, VERTEX_EVIDENCE); None = the local index."""
    if settings.ANSWER_RETRIEVER != "vertex_search":
        return None
    mode = settings.VERTEX_EVIDENCE
    search = VertexSearchRetriever(settings.GCP_PROJECT, settings.VERTEX_SEARCH_LOCATION,
                                   settings.VERTEX_SEARCH_ENGINE_ID, settings.VERTEX_ANSWER_TIMEOUT_MS,
                                   "answer" if mode == "answer" else "segments", settings.VERTEX_SEARCH_TIMEOUT_MS)

    def load(product_id: str) -> list[tuple[str, bytes]]:
        """The product's uploaded PDFs, from the onboarding bucket (products/<product_id>/, api/products.py)."""
        from .onboarding.storage import bucket_for

        if not settings.ONBOARDING_GCS_BUCKET:
            return []
        bucket = bucket_for(settings.ONBOARDING_GCS_BUCKET, settings.GCP_PROJECT)
        return [(k.rsplit("/", 1)[1], bucket.download(k)) for k in bucket.keys(f"products/{product_id}/")
                if k.lower().endswith(".pdf")]

    # the search is the evidence; the product's own PDF stands in when the search gives nothing (or goes first, for
    # VERTEX_EVIDENCE=document)
    return ProductDocumentRetriever(load, search, settings.WHOLE_DOCUMENT_MAX_CHARS,
                                    first="document" if mode == "document" else "search")


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx
