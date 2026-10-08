from __future__ import annotations

import atexit
import os
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


# D-305: the model-only settings are the shipped defaults. The older tests check the code paths as they were written,
# so the test session pins those paths (environment, so get_settings() sees them too); a test turns any setting on
# itself, and test_d305.py runs the shipped defaults (SHIPPED)
LEGACY = {
    "FACT_RELATION": "false", "JUDGE_ARM": "guards", "VERIFY_EVIDENCE": "all", "STT_AWARE": "false",
    "CONTEXT_WINDOW_MS": "0", "NUMBER_CHECK": "false", "SWITCH_ARM_NAME": "true", "CORRECTION_CHECK": "words",
    "QUALIFIER_ADDON": "true", "VERBAL_CHECK": "code", "REFLEX_SCAN": "true", "JUDGE_PRODUCTS": "named",
    "COMMENT_PRODUCT": "code", "DRAFT_GATE": "full", "GROUP_JOIN": "code", "SHOUTOUT": "regex", "PREFILTER": "full",
    "UTTERANCE_MERGE_WINDOW_MS": "3500",
    # D-336: the measured config became the default; the older tests keep the paths they were written for
    "FACT_PROMPT": "v1", "JUDGE_SEED": "", "SINGLE_MODEL": "gemini-3.8-flash", "SINGLE_THINKING": "LOW",
    "SINGLE_FACTS_THINKING": "", "STT_ENDPOINTING": "SHORT", "QUESTION_HOLD": "false",  # D-343
}
for _key, _value in LEGACY.items():
    os.environ.setdefault(_key, _value)
SHIPPED = {k: Settings.model_fields[k].default for k in LEGACY}
# D-336: the verifier arm as it shipped from D-305 to D-335 (the default is now the single arm)
VERIFY_SHIPPED = SHIPPED | {"JUDGE_ARM": "verify", "FACT_PROMPT": "v1", "JUDGE_SEED": "", "QUESTION_HOLD": False}

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
