from __future__ import annotations

import atexit
import shutil
import tempfile
from pathlib import Path

import pytest

from app.agents.inputs import BUILDERS
from app.bus import EventBus
from app.clock import ManualClock
from app.config import Settings
from app.ids import Ids
from app.logic.catalog import Catalog, DataPack
from app.providers.prompts import load_prompts
from app.store.memory import MemoryStore


_REPO = Path(__file__).resolve().parents[2]
_TEST_DATA: Path | None = None


def test_data_dir() -> Path:
    """D-278: the runtime data has no products. Tests run on a copy of it plus the demo pack that only tests load
    (tests/fixtures/demo_pack: products, run-sheets, promos; the demo PDFs from data/demo_sources), built once."""
    global _TEST_DATA
    if _TEST_DATA is None:
        out = Path(tempfile.mkdtemp(prefix="live_studio_test_data_")) / "data"
        shutil.copytree(_REPO / "data", out)
        shutil.copytree(Path(__file__).parent / "fixtures" / "demo_pack", out, dirs_exist_ok=True)
        for pdf in (_REPO / "data" / "demo_sources").glob("*.pdf"):
            shutil.copy2(pdf, out / "products" / pdf.name)
        atexit.register(shutil.rmtree, out.parent, True)
        _TEST_DATA = out
    return _TEST_DATA


def make_settings(**overrides) -> Settings:
    """Test settings: never read the developer's .env; mock providers by default; the test data dir (with the demo
    pack) unless a test names its own."""
    values = {"LLM_PROVIDER": "mock", "STT_PROVIDER": "mock", "DATA_DIR": str(test_data_dir()), **overrides}
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
