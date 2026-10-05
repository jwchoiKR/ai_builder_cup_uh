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
    ONBOARDING_DIR: str = "../data/onboarding"  # D-217: uploaded product files, immutable, git-ignored
    VERIFY_MODE: Literal["full", "risk"] = "full"  # D-236: what a person checks before approving a product
    PREFILTER: Literal["full", "pii_only"] = "full"  # D-237: pii_only leaves profanity and short reactions to triage
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
    PD_THINKING: ThinkingLevel = "LOW"  # D-166: the AI PD on LLM_QUALITY_MODEL (docs/eval/ai-pd-arms.md)
    # D-128: per-agent overrides of LLM_FAST_THINKING (thinking-level comparison, docs/eval/models/README.md)
    COMPLIANCE_THINKING: ThinkingLevel = "LOW"
    CONTEXT_THINKING: ThinkingLevel = "MINIMAL"
    FACTS_THINKING: ThinkingLevel = "MINIMAL"
    TRIAGE_THINKING: ThinkingLevel = "LOW"
    LLM_RETRY_ON_5XX: int = 1
    LLM_CONTEXT_CACHE: bool = True  # measured 10/5: fact checker cached share 44% -> 72.5%, accuracy and latency unchanged
    LLM_CONTEXT_CACHE_TTL_SEC: int = 3600  # request session duration overrides this fallback
    JUDGE_MODE: Literal["split3", "split", "single"] = "split3"  # D-099; split = one UtteranceJudge (rollback)
    JUDGE_TIMEOUT_MS: int = 2500
    # D-187: design arms compared by measurement (user decision 10/5). A = today; B = meaning to the LLM, code only
    # checks it; C = B without the reflex pre-scan; D = agents decide everything, code keeps deadlines, state, routing
    # and idempotency; E = D with the rules retrieved per utterance. The default stays A until a comparison picks one.
    DESIGN_ARM: Literal["A", "B", "C", "D", "E", "F1", "F2"] = "A"
    # D-187: write the calls and tokens per agent of this process as JSON to this path at exit ("" = off)
    LLM_USAGE_REPORT: str = ""
    # D-194 arm E: the Vertex AI Search serving config that picks the compliance rules for each spoken line
    RULE_SEARCH_SERVING_CONFIG: str = ("projects/separk-cloocus/locations/global/collections/default_collection/"
                                       "engines/live-studio-rules-engine/servingConfigs/default_search")
    RULE_SEARCH_PAGE_SIZE: int = 8
    RULE_SEARCH_TIMEOUT_MS: int = 1000
    # D-184: a judge or fact call still unanswered after this sends one identical second request; the first answer
    # wins and the other is cancelled (cloud 00008: two single timeouts were silent misses). 0 = off
    JUDGE_HEDGE_MS: int = 1500
    UTTERANCE_MERGE_WINDOW_MS: int = 3500  # join a final with the previous unfinished one (D-088); 0 = off
    FACT_TIMEOUT_MS: int = 3000  # the "on time" line: a slower fact call counts as a timeout for the health dot
    FACT_LATE_MS: int = 6000  # D-144: a fact call may still answer until here; a late wrong-fact note beats none
    FACT_SEARCH_TIMEOUT_MS: int = 600
    TRIAGE_TIMEOUT_MS: int = 2500
    MODEL_ARMOR_ENABLED: bool = False  # D-125: screen comments before triage (needs a template)
    MODEL_ARMOR_LOCATION: str = "us-central1"
    MODEL_ARMOR_TEMPLATE: str = "live-studio-comments"
    MODEL_ARMOR_TIMEOUT_MS: int = 500  # slower or failing: the comment stays unscreened
    TRIAGE_CONCURRENCY: int = 8  # triage calls in flight; comments arriving beyond this are batched
    TRIAGE_MAX_BATCH: int = 10  # start value, tune with burst tests (PLANNING 5.1.2)
    TRIAGE_BATCH_TIMEOUT_MS: int = 5000  # one call for up to TRIAGE_MAX_BATCH comments; start value
    COMPOSER_TIMEOUT_MS: int = 12000
    DRAFT_VERIFY_TIMEOUT_MS: int = 2500  # D-126: LLM check after verify_answer; slower or failing: unverified
    BRIEF_TIMEOUT_MS: int = 60000
    SUMMARY_TIMEOUT_MS: int = 30000
    MARKET: str = "SG"  # D-129: data/markets/<code>.json (law)
    BROADCAST_LANGUAGE: str = "en"  # D-129: data/lang/<code>.json (wording); must be offered by MARKET
    STT_LOCATION: str = "us"
    STT_MODEL: str = "chirp_3"
    STT_LANGUAGE: str = ""  # empty: the market pack's code for BROADCAST_LANGUAGE (D-129)
    STT_PHRASE_HINTS_ENABLED: bool = True
    # D-186: also hint the market's claim words (the reflex phrases of its rules, in the broadcast language) after
    # the glossary, so a risky word is not heard as a harmless sound-alike ("widens" for "whitens"). Off until measured
    STT_RISK_HINTS: bool = False
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
    HOST_TOP_N: int = 6  # D-113: the compact waiting list (cards are released one at a time by the AI PD)
    HOST_MIN_DWELL_SEC: int = 20
    HOST_REPEAT_THRESHOLD: int = 3  # D-113: an AI-answered question with this many askers is read out on air
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
    def onboarding_path(self) -> Path:
        return _resolve(self.ONBOARDING_DIR)

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
