from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import REPO_DIR, Settings

from .conftest import make_settings


def _env_example() -> dict[str, str]:
    values = {}
    for line in (REPO_DIR / ".env.example").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def _as_env(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def test_every_spec_key_exists_with_its_default():
    example = _env_example()
    fields = Settings.model_fields
    assert set(example) == set(fields), "config.py and .env.example must list the same keys (§5)"
    for key, value in example.items():
        assert _as_env(fields[key].default) == value, key


def test_google_provider_requires_project():
    with pytest.raises(ValidationError, match="GCP_PROJECT"):
        Settings(_env_file=None, LLM_PROVIDER="vertex", STT_PROVIDER="mock")
    assert Settings(_env_file=None, LLM_PROVIDER="vertex", STT_PROVIDER="mock", GCP_PROJECT="p").GCP_PROJECT == "p"


def test_vertex_answers_require_an_engine():
    with pytest.raises(ValidationError, match="VERTEX_SEARCH_ENGINE_ID"):
        make_settings(ANSWER_RETRIEVER="vertex_search", VERTEX_SEARCH_ENGINE_ID="", GCP_PROJECT="p")


def test_demo_tools_off_in_cloud_unless_explicit():
    assert make_settings().DEMO_TOOLS_ENABLED is True
    assert make_settings(APP_ENV="cloud").DEMO_TOOLS_ENABLED is False
    assert make_settings(APP_ENV="cloud", DEMO_TOOLS_ENABLED=True).DEMO_TOOLS_ENABLED is True


def test_demo_tools_cloud_rule_reads_environment(monkeypatch):
    monkeypatch.setenv("APP_ENV", "cloud")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("STT_PROVIDER", "mock")
    assert Settings(_env_file=None).DEMO_TOOLS_ENABLED is False
    monkeypatch.setenv("DEMO_TOOLS_ENABLED", "true")
    assert Settings(_env_file=None).DEMO_TOOLS_ENABLED is True


def test_snapshot_is_json_ready(settings):
    snap = settings.snapshot()
    assert snap["JUDGE_TIMEOUT_MS"] == 2500 and snap["LLM_PROVIDER"] == "mock"
