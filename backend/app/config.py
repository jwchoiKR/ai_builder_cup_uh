"""Application settings (DEV_SPEC §5). Every key of the spec exists here with its default."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent

ThinkingLevel = Literal["MINIMAL", "LOW", "MEDIUM", "HIGH"]


class Settings(BaseSettings):
    # `.env` at the repo root; process environment variables override it.
    model_config = SettingsConfigDict(
        env_file=REPO_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    APP_ENV: Literal["local", "cloud"] = "local"
    DATA_DIR: str = "../data"
    PROMPTS_DIR: str = "../prompts"
    STORE: Literal["memory", "firestore"] = "memory"
    RETRIEVER: Literal["local", "vertex_search"] = "local"
    LLM_PROVIDER: Literal["vertex", "mock"] = "vertex"
    STT_PROVIDER: Literal["google_v2", "mock"] = "google_v2"
    GCP_PROJECT: str = ""
    LLM_LOCATION: str = "global"
    LLM_FAST_MODEL: str = "gemini-3.5-flash-lite"
    LLM_FAST_THINKING: ThinkingLevel = "MINIMAL"
    LLM_QUALITY_MODEL: str = "gemini-3.8-flash"
    LLM_QUALITY_THINKING: ThinkingLevel = "MEDIUM"
    COMPOSER_THINKING: ThinkingLevel = "LOW"  # per-agent override for AnswerComposer (D-067)
    LLM_RETRY_ON_5XX: int = 1
    LLM_CONTEXT_CACHE: bool = False
    JUDGE_MODE: Literal["split3", "split", "single"] = "split3"  # D-099; split = one UtteranceJudge (rollback)
    JUDGE_TIMEOUT_MS: int = 2500
    UTTERANCE_MERGE_WINDOW_MS: int = 3500  # join a final with the previous unfinished one (D-088); 0 = off
    FACT_TIMEOUT_MS: int = 3000
    FACT_SEARCH_TIMEOUT_MS: int = 600
    TRIAGE_TIMEOUT_MS: int = 2500
    COMPOSER_TIMEOUT_MS: int = 12000
    BRIEF_TIMEOUT_MS: int = 60000
    SUMMARY_TIMEOUT_MS: int = 30000
    STT_LOCATION: str = "us"
    STT_MODEL: str = "chirp_3"
    STT_LANGUAGE: str = "en-US"
    STT_PHRASE_HINTS_ENABLED: bool = True
    VERTEX_SEARCH_LOCATION: str = "global"
    VERTEX_SEARCH_DATA_STORE_ID: str = ""
    GCS_BUCKET: str = ""
    COMPLIANCE_ESCALATE_SEC: int = 5
    CORRECTED_TOAST_MS: int = 1500
    FACT_NOTE_HOST_MAX_SEC: int = 45
    PUBLISH_CANCEL_WINDOW_MS: int = 2000
    SWITCH_CONSECUTIVE_CUES: int = 2
    SWITCH_CUE_WINDOW_SEC: int = 30
    SWITCH_CANCEL_WINDOW_SEC: int = 5
    UNDO_SWITCH_WINDOW_SEC: int = 60
    STREAM_GRACE_SEC: int = 2
    HOST_TOP_N: int = 3
    HOST_MIN_DWELL_SEC: int = 20
    HOST_REPEAT_THRESHOLD: int = 5
    REPLY_COALESCE_SEC: int = 10
    STALE_COMMENT_SEC: int = 300
    GROUP_TTL_SEC: int = 600
    TRIAGE_MAX_OPEN_GROUPS: int = 30
    JUDGE_MAX_OPEN_QUESTIONS: int = 5
    COMPOSER_TOP_K: int = 6
    COMMENT_RATE_LIMIT_PER_MIN: int = 120
    COMMENT_RATE_LIMIT_PER_AUTHOR_PER_MIN: int = 10
    MAX_COMMENT_CHARS: int = 300
    AUTO_ANSWER_ENABLED: bool = True
    VIEWER_INPUT_ENABLED: bool = False
    DEMO_TOOLS_ENABLED: bool = True
    LOG_LEVEL: str = "INFO"

    @model_validator(mode="after")
    def _check(self) -> "Settings":
        # §5: DEMO_TOOLS_ENABLED MUST be false in `cloud` unless explicitly set.
        if self.APP_ENV == "cloud" and "DEMO_TOOLS_ENABLED" not in self.model_fields_set:
            self.DEMO_TOOLS_ENABLED = False
        if self.uses_google() and not self.GCP_PROJECT:
            raise ValueError(
                "GCP_PROJECT is required when a Google provider is used "
                f"(LLM_PROVIDER={self.LLM_PROVIDER}, STT_PROVIDER={self.STT_PROVIDER}, "
                f"STORE={self.STORE}, RETRIEVER={self.RETRIEVER})"
            )
        if self.RETRIEVER == "vertex_search" and not self.VERTEX_SEARCH_DATA_STORE_ID:
            raise ValueError("VERTEX_SEARCH_DATA_STORE_ID is required when RETRIEVER=vertex_search")
        return self

    def uses_google(self) -> bool:
        return (
            self.LLM_PROVIDER == "vertex"
            or self.STT_PROVIDER == "google_v2"
            or self.STORE == "firestore"
            or self.RETRIEVER == "vertex_search"
        )

    @property
    def data_path(self) -> Path:
        return _resolve(self.DATA_DIR)

    @property
    def prompts_path(self) -> Path:
        return _resolve(self.PROMPTS_DIR)

    def snapshot(self) -> dict[str, Any]:
        """Values of §5, stored on each session at start."""
        return self.model_dump(mode="json")


def _resolve(p: str) -> Path:
    # Relative paths are relative to backend/, whatever the working directory is.
    path = Path(p)
    return path if path.is_absolute() else (BACKEND_DIR / path).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
