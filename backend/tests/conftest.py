from __future__ import annotations

import pytest

from app.agents.inputs import BUILDERS
from app.bus import EventBus
from app.clock import ManualClock
from app.config import Settings
from app.ids import Ids
from app.logic.catalog import Catalog, DataPack
from app.providers.prompts import load_prompts
from app.store.memory import MemoryStore


def make_settings(**overrides) -> Settings:
    """Test settings: never read the developer's .env; mock providers by default."""
    values = {"LLM_PROVIDER": "mock", "STT_PROVIDER": "mock", **overrides}
    return Settings(_env_file=None, **values)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture(scope="session")
def pack() -> DataPack:
    return DataPack.load(make_settings().data_path)


@pytest.fixture(scope="session")
def prompts():
    return load_prompts(make_settings().prompts_path, BUILDERS)


@pytest.fixture
def catalog(pack) -> Catalog:
    return Catalog(pack)


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock()


@pytest.fixture
def ids(clock) -> Ids:
    return Ids(clock, deterministic=True)


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture
def bus(store, clock) -> EventBus:
    return EventBus(store, clock)
