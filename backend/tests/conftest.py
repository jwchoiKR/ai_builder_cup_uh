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


# D-353: every FACT_FIXES letter that still has a prompt line (D-432: the code-check letters are deleted)
ALL_FIXES = "F1,F5,Q6"

# D-434 (test migration, user go 10/10): the live path runs as production does (code defaults plus
# deploy/cloudrun.sh; test_d434.py guards that they agree). No live-path setting comes from the environment: the ones a
# developer's shell sets are removed here, and get_settings() never reads the developer's .env in a test.
LIVE_PATH_KEYS = (
    "JUDGE_MODE", "JUDGE_SEED", "JUDGE_TIMEOUT_MS", "VERIFY_TIMEOUT_MS",
    "SINGLE_MODEL", "SINGLE_THINKING", "SINGLE_FACTS_THINKING", "FACTS_MODEL", "FACT_PROMPT",
    "FACT_FIXES", "FACT_TIMEOUT_MS", "FACT_LATE_MS", "QUESTION_HOLD_MS",
    "VERBAL_CHECK", "UTTERANCE_MERGE_WINDOW_MS", "STT_ENDPOINTING", "STT_PHRASE_HINTS_ENABLED", "DESIGN_ARM", "LLM_RETRY_ON_429_MS", "LLM_RETRY_ON_5XX", "JUDGE_HEDGE_MS",
    "HEDGED_AGENTS", "HEDGE_DELAYS", "COMPLIANCE_ESCALATE_SEC", "SWITCH_DUAL_SCOPE_SEC", "CONTEXT_TIMEOUT_MS", "CONTEXT_RETRY_TOTAL_MS",
    "UNDO_SWITCH_WINDOW_SEC",
)
for _key in LIVE_PATH_KEYS:
    os.environ.pop(_key, None)
Settings.model_config["env_file"] = None  # get_settings() in a test: code defaults, never the developer's .env
os.environ.setdefault("LLM_PROVIDER", "mock")  # as make_settings: no Google provider in a test
os.environ.setdefault("STT_PROVIDER", "mock")
os.environ.setdefault("ANSWER_RETRIEVER", "local")

# D-434: the old live-path pins, applied (with the rules-JSON compliance path) only to a file or test marked
# `legacy_live` until it is migrated. Temporary: test_d434 fails when a file outside LEGACY_LIVE_FILES uses it.
LEGACY_LIVE = {
    "VERBAL_CHECK": "code",
    "UTTERANCE_MERGE_WINDOW_MS": "3500", "JUDGE_SEED": "", "SINGLE_MODEL": "gemini-3.8-flash",
    "SINGLE_THINKING": "LOW", "SINGLE_FACTS_THINKING": "", "STT_ENDPOINTING": "SHORT",
    "QUESTION_HOLD_MS": "0",  # D-435: no question hold (was QUESTION_HOLD=false)
}
# The comments path keeps its own test pins (the comments team's tests were written for them)
COMMENT_PINS = {
    "COMMENT_PRODUCT": "code", "GROUP_JOIN": "code", "SHOUTOUT": "regex", "PREFILTER": "full",
    # the host route of sensitive questions in a team show
    "SENSITIVE_APPROVAL": "host", "TRIAGE_RETRIES": "0", "COMPOSE_RETRIES": "0", "TRIAGE_MODEL": "", "GROUP_TTL_WAITING_SEC": "600", "DEFAULT_SHOW_MODE": "solo",
}
for _key, _value in COMMENT_PINS.items():
    os.environ.setdefault(_key, _value)
LEGACY = LEGACY_LIVE | COMMENT_PINS
SHIPPED = {k: Settings.model_fields[k].default for k in LEGACY}
# D-336: the verifier arm as it shipped from D-305 to D-335 (the default is now the single arm)
# D-392: the verify arm is gone; these shipped-default tests run the single arm
VERIFY_SHIPPED = SHIPPED | {"JUDGE_SEED": "",
                            "SINGLE_THINKING": "MEDIUM"}  # D-360: as it shipped

_REPO = Path(__file__).resolve().parents[2]
_TEST_DATA: Path | None = None


def test_data_dir() -> Path:
    """A copy of the runtime data (no products, no market law), built once."""
    global _TEST_DATA
    if _TEST_DATA is None:
        out = Path(tempfile.mkdtemp(prefix="live_studio_test_data_")) / "data"
        shutil.copytree(_REPO / "data", out)
        atexit.register(shutil.rmtree, out.parent, True)
        _TEST_DATA = out
    return _TEST_DATA


def make_settings(**overrides) -> Settings:
    """Test settings: never read the developer's .env; mock providers by default; the test data dir (with the demo
    pack) unless a test names its own."""
    values = {"LLM_PROVIDER": "mock", "STT_PROVIDER": "mock", "ANSWER_RETRIEVER": "local",
              "DATA_DIR": str(test_data_dir()), **overrides}
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


@pytest.fixture(autouse=True)
def _live_path(request, monkeypatch):
    """D-434: every test runs the production live path (the regulation originals, D-358). A test marked
    `legacy_live` (not migrated yet) gets the old pins and the rules-JSON compliance path."""
    from app.config import get_settings

    get_settings.cache_clear()
    legacy = request.node.get_closest_marker("legacy_live") is not None
    if legacy:
        for key, value in LEGACY_LIVE.items():
            monkeypatch.setenv(key, value)
    monkeypatch.setattr("app.agents.split_judges.LEGACY_RULES", legacy)
    from . import judge_fakes

    judge_fakes.ADAPTER_ERRORS.clear()
    yield
    get_settings.cache_clear()
    assert not judge_fakes.ADAPTER_ERRORS, judge_fakes.ADAPTER_ERRORS  # a scripted verdict the adapter refused
