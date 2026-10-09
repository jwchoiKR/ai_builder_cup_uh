"""Application settings (DEV_SPEC §5). Every key of the spec exists here with its default."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import field_validator, model_validator
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
    # D-263: the bucket that holds onboarding state in the cloud (uploads, releases, packs); empty = local disk only
    ONBOARDING_GCS_BUCKET: str = ""
    # D-267: the offline onboarding reads (product, law and brand packs); gemini-3.1-pro-preview is the Pro arm
    ONBOARDING_MODEL: str = "gemini-3.8-flash"
    ONBOARDING_THINKING: ThinkingLevel = "HIGH"
    # D-267: the caution pass, routing, category pick and coverage audit; empty = ONBOARDING_MODEL, and their own
    # thinking levels (MEDIUM; LOW for the category pick)
    ONBOARDING_PASS_MODEL: str = ""
    ONBOARDING_PASS_THINKING: str = ""
    # D-274 arm: "show" puts every caution and direction into the show's language and merges repeats by meaning
    ONBOARDING_CAUTION_LANG: Literal["as_written", "show"] = "as_written"
    VERIFY_MODE: Literal["full", "risk", "lean"] = "lean"  # D-254 lean: risk, at most 10 items; D-263 default  # D-236: what a person checks before approving a product
    PREFILTER: Literal["full", "pii_only"] = "full"  # D-308: back until measured
    # D-280: switchable fixes of fact-claim code drops ("F1,F2,..."); empty = today's checks
    # D-353 (user order): only the fixes that are prompt lines (F1, F5, Q6 in prompts/design_arms.md); every code text
    # check is off: Q5 fragment hold, Q1T code-added qualifier alert, G4/G5, Q2/G1 and the guards-arm checks.
    # Was "F1,F2,F3,F4,F5,R1,Q1E,Q1T,Q2,Q3,Q4,Q5,Q6,G1,G2,G3,G4,G5,G6,G7,CK" (D-293, D-294, D-297)
    FACT_FIXES: str = "F1,F5,Q6"
    # D-296: the fact checker returns evidence sentence ids and a relation (contradicts, consistent, not in the
    # documents, uncertain); code builds the quote
    # D-300 R2: "verify" turns the flaggers' code drops off and sends each candidate alert to one stronger model
    # (VERIFY_MODEL) that keeps or rejects it with the evidence; "guards" is the guard layer (R3)
    # D-309 "single": the compliance judge and the fact checker on one model (SINGLE_MODEL, SINGLE_THINKING; unless
    # COMPLIANCE_MODEL / FACTS_MODEL name another), no verifier, no code drops
    JUDGE_ARM: Literal["guards", "single"] = "single"  # D-305; D-336: the measured config; D-392: no verify or vote
    # D-314 (eval): the live judges' sampling (compliance_judge, fact_checker, context_judge); empty = not sent (the
    # model's default, D-008). JUDGE_TEMPERATURE is a number ("0"), JUDGE_SEED an integer ("7")
    JUDGE_TEMPERATURE: str = ""
    JUDGE_SEED: str = "7"  # D-336: the measured config (a seed removes most run-to-run flips)
    # D-302: "self" adds a confidence (0-1) to each violation and claim, a log field only
    VOTE_CONFIDENCE: Literal["off", "self"] = "off"
    VERIFY_TIMEOUT_MS: int = 5000  # D-306/D-309: the compliance judge's deadline in the single arm
    # D-303 (STT set): the judges and the verifier are told the line is speech-to-text (missing quote marks,
    # sound-alike names, misheard numbers, sentences in pieces)
    STT_AWARE: bool = False  # D-308: back (STT set: 96.3/11.1/5 with the STT bundle)
    # D-303: the judges read the finals of the last N ms (0 = the last two)
    CONTEXT_WINDOW_MS: int = 0  # D-308: back
    # D-304: each code rule that judges meaning, switchable against the model's own judgment (defaults: today)
    # D-353 (user order 10/8): no code word, name, number or regex check on the host's text; the model decides
    # D-353 addendum (user, 10/8): back to "code": spoken-answer posting belongs to the comments team (out of scope)
    VERBAL_CHECK: Literal["code", "judge"] = "code"  # judge: numbers said and hedges from the context judge (arm B's)
    JUDGE_PRODUCTS: Literal["named", "all"] = "all"  # D-353; named: a code alias match picks the products in scope
    COMMENT_PRODUCT: Literal["code", "triage"] = "code"  # D-308: back;  # triage: the comment's product from triage, no alias rules
    DRAFT_GATE: Literal["full", "provenance"] = "full"  # D-308: back;  # provenance: citations, products and numbers only
    GROUP_JOIN: Literal["code", "model"] = "code"  # D-308: back;  # model: no only-open-group or stem joins
    SHOUTOUT: Literal["regex", "judge"] = "regex"  # D-308: back;  # judge: triage labels shout-outs (arm B's)
    FACT_RELATION: bool = True  # D-297 hybrid: the relation arm with the fact guards off but Q2/G1
    # D-312 v2: fact_relation_v2.md (only the host's own assertions, sound-alike values uncertain, the documents' value
    # before the relation) and the compliance judge's sound-alike tester-name line; D-313 v3: v2 plus endorsements
    # ("Correct.") of the previous line's facts
    # D-325 v4: v3 plus "a documents' value with a condition, said without it, contradicts"
    # D-331 v5: v3 plus a stance per claim (HOST_ASSERTS, HOST_ENDORSES, REPORTS_OR_ASKS): reported words not checked
    # D-333 v6: v5 plus answers take the question's subject, a rejection with a new value is a claim, questions stay
    # REPORTS_OR_ASKS
    # D-345 v7: v5 plus stated_as_heard (number-word homophones read as digits) before the relation
    # D-347 v8: v5 plus "lists of rejected claim wordings are never a fact source"
    FACT_PROMPT: Literal["v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8"] = "v5"  # D-336: the measured config
    # D-328: the fact checker marks each claim host or other (reported words, a question to someone); a contradiction
    # in someone else's words waits for the next line's check (it endorses, rejects or neither), at most
    # REPORTED_HOLD_MS when no next line comes. Needs FACT_PROMPT v2-v4.
    REPORTED_HOLD: bool = False
    REPORTED_HOLD_MS: int = 2500
    # D-328: the compliance judge's rule for lines that warn against a risky use or negate a claim
    COMPLIANCE_NEG: bool = False
    # D-333: the compliance judge judges what this line endorses from the previous line as this line's own claim
    COMPLIANCE_ENDORSE: bool = False
    # D-356: ACTIVE_ALERTS by per-call handle; the compliance judge answers {handle, fixed_by_this_line} first.
    # D-358: on by default (the originals path always uses handles; this setting only matters for the legacy path)
    CORRECTION_HANDLES: bool = True
    # D-334 (the user's design): a final ending with "?" waits for the next final (QUESTION_HOLD_MS), and the two are
    # judged as one utterance by all three judges; with none, the question is judged alone
    QUESTION_HOLD: bool = True  # D-343: measured (pool 7 + pairs: two-host lines 82.8% -> 96.6%, no one-host loss)
    QUESTION_HOLD_MS: int = 2500
    # D-334 alternative: the fact checker reads a CONVERSATION block (the last 3 finals, oldest first) and checks only
    # the last line, using the earlier ones to understand it
    CONTEXT_JUDGE: bool = False
    # D-360 (user): the fact checker flags ONLY facts on the host prompter: its passages are the prompter's display
    # snapshot (price and offers, the shown ingredients, points, in-house test results, cautions); no product files,
    # no record facts the prompter does not show. Was "docs" (D-247/D-255). The release pack itself is still built at
    # record level for its other readers (answers to viewers).
    FACT_MODE: Literal["sheet", "record", "docs", "prompter"] = "prompter"  # D-237: pii_only leaves profanity and short reactions to triage
    PROMPTS_DIR: str = "../prompts"
    STORE: Literal["memory", "firestore"] = "memory"
    FIRESTORE_DATABASE: str = "live-studio"  # D-354: the Firestore database of STORE=firestore
    # D-428: an ended session leaves memory this long after its summary is written; STORE=firestore keeps it and reads
    # it back when it is opened. 0 keeps every session in memory.
    SESSION_EVICT_AFTER_SEC: int = 900
    # D-428: the comments team's second Firestore writer was merged into STORE=firestore. D-430: true runs as
    # STORE=firestore (one warning), so there is still one writer; false changes nothing
    SESSIONS_FIRESTORE: bool = False
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
    FACTS_THINKING: ThinkingLevel = "LOW"  # D-255: sealed unseen products, 5 s budget
    # D-309 JUDGE_ARM=single: the one model and thinking level of the compliance judge and the fact checker
    SINGLE_MODEL: str = "gemini-3.5-flash-lite"  # D-336: the measured config (Flash-Lite, compliance MEDIUM, facts LOW)
    SINGLE_THINKING: ThinkingLevel = "LOW"  # D-360 (user): the compliance judge thinks LOW (was MEDIUM, D-336)
    SINGLE_FACTS_THINKING: Literal["", "MINIMAL", "LOW", "MEDIUM", "HIGH"] = "LOW"  # D-311: the fact checker's; empty = SINGLE_THINKING
    COMPLIANCE_MODEL: str = ""
    # D-310: the compliance judge's cached prefix also holds the on-air product's documents (the fact checker's FD
    # files and passages): names said as sound-alikes can be matched, and the prefix passes the cache minimum
    COMPLIANCE_DOCS: bool = False  # D-309: the compliance judge's model; empty = LLM_FAST_MODEL (VERIFY_MODEL in single)
    FACTS_MODEL: str = ""  # D-246: the fact checker's model (base and FR); empty = LLM_FAST_MODEL
    TRIAGE_THINKING: ThinkingLevel = "LOW"
    LLM_RETRY_ON_5XX: int = 1
    # D-340 (review H15): a 429 (Google's shared capacity) is retried once after this many ms, when the call's
    # deadline leaves room for it; 0 = no retry (as before), a switch until measured
    LLM_RETRY_ON_429_MS: int = 500  # D-351: on (user-approved); retried only when the deadline leaves 1 s after it
    LLM_CONTEXT_CACHE: bool = True  # measured 10/5: fact checker cached share 44% -> 72.5%, accuracy and latency unchanged
    LLM_CONTEXT_CACHE_TTL_SEC: int = 3600  # request session duration overrides this fallback
    JUDGE_MODE: Literal["split3", "split", "single"] = "split3"  # D-099; split = one UtteranceJudge (rollback)
    JUDGE_TIMEOUT_MS: int = 2500
    # D-187: design arms compared by measurement (user decision 10/5). A = today; B = meaning to the LLM, code only
    # checks it; C = B without the reflex pre-scan; D = agents decide everything, code keeps deadlines, state, routing
    # and idempotency; E = D with the rules retrieved per utterance. The default stays A until a comparison picks one.
    DESIGN_ARM: Literal["A", "B", "C", "D", "E", "F1", "F2"] = "A"
    # D-270 arm: the judges' target_group bullet; "split" = an age band or usage direction is not a vulnerable claim
    VULNERABLE_WORDING: Literal["d256", "split"] = "d256"
    # D-187: write the calls and tokens per agent of this process as JSON to this path at exit ("" = off)
    LLM_USAGE_REPORT: str = ""
    # D-194 arm E: the Vertex AI Search serving config that picks the compliance rules for each spoken line
    RULE_SEARCH_SERVING_CONFIG: str = ""  # D-289: not recreated in the new project (arm E only)
    RULE_SEARCH_PAGE_SIZE: int = 8
    RULE_SEARCH_TIMEOUT_MS: int = 1000
    # D-184: a judge or fact call still unanswered after this sends one identical second request; the first answer
    # wins and the other is cancelled (cloud 00008: two single timeouts were silent misses). 0 = off
    JUDGE_HEDGE_MS: int = 1500
    # D-287: which alert-path agents get the second request ("compliance,fact": names or prefixes); empty = all
    HEDGED_AGENTS: str = "compliance,fact,context"  # D-293; D-308: add "verifier" to hedge it (off until compared)
    # D-292: a later second request for some agents ("fact=3000,context=2000": name or prefix = ms); the others use
    # JUDGE_HEDGE_MS. A delay at or past the agent's deadline sends no second request
    HEDGE_DELAYS: str = "fact=3000,context=2000"  # D-293 (D-413: the verifier entry is gone with its agent)
    UTTERANCE_MERGE_WINDOW_MS: int = 3500  # D-308: back  # join a final with the previous unfinished one (D-088); 0 = off
    # the "on time" line: a slower fact call counts as a timeout for the health dot; D-255: fact corrections may take
    # 5 s at p95 (user, 10/6), the same as the deadline, so there is no late window any more
    FACT_TIMEOUT_MS: int = 5000
    FACT_LATE_MS: int = 5000  # D-144: a fact call may still answer until here; a late wrong-fact note beats none
    FACT_SEARCH_TIMEOUT_MS: int = 600
    # Triage decides whether a reply needs a person's approval, so it runs on the quality model: a comment may wait
    # a few seconds, a wrong decision may not. Empty TRIAGE_MODEL = LLM_FAST_MODEL. When the call fails or runs past
    # its deadline, the same comment is triaged at once on the fast model (TRIAGE_FALLBACK_*), so a slow quality
    # model costs time, not an answer.
    TRIAGE_MODEL: str = "gemini-3.8-flash"
    TRIAGE_TIMEOUT_MS: int = 10000
    TRIAGE_FALLBACK_THINKING: ThinkingLevel = "MEDIUM"
    TRIAGE_FALLBACK_TIMEOUT_MS: int = 8000
    MODEL_ARMOR_ENABLED: bool = False  # D-125: screen comments before triage (needs a template)
    MODEL_ARMOR_LOCATION: str = "us-central1"
    MODEL_ARMOR_TEMPLATE: str = "live-studio-comments"
    MODEL_ARMOR_TIMEOUT_MS: int = 500  # slower or failing: the comment stays unscreened
    # a comment whose triage failed (timeout, 429) is triaged again this many times, this long apart, before it
    # goes to the operator as "AI unavailable"
    TRIAGE_RETRIES: int = 2
    TRIAGE_RETRY_AFTER_MS: int = 5000
    TRIAGE_CONCURRENCY: int = 8  # triage calls in flight; comments arriving beyond this are batched
    TRIAGE_MAX_BATCH: int = 10  # start value, tune with burst tests (PLANNING 5.1.2)
    TRIAGE_BATCH_TIMEOUT_MS: int = 5000  # one call for up to TRIAGE_MAX_BATCH comments; start value
    COMPOSER_TIMEOUT_MS: int = 12000
    DRAFT_VERIFY_TIMEOUT_MS: int = 8000  # D-126: LLM check after verify_answer; slower or failing: unverified
    # the draft verifier is the last look before a reply is posted by itself: it thinks (empty = LLM_FAST_THINKING)
    DRAFT_VERIFY_THINKING: Literal["", "MINIMAL", "LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    BRIEF_TIMEOUT_MS: int = 60000
    BRIEF_MODEL: str = ""  # D-265: the BriefAgent's model; empty = LLM_QUALITY_MODEL
    BRIEF_THINKING: ThinkingLevel = "MEDIUM"  # D-265: MEDIUM (today) vs HIGH, measured on the sealed releases
    # D-269 arm: "terms" gives the brief every offer term with its id and one point per offer up to 240 characters;
    # D-272: "code" (default after the blind grading) builds the offer points from the record, after the model's
    BRIEF_OFFERS: Literal["sheet", "terms", "code"] = "code"
    # D-276 arm: "code" gives every record caution (and every safety direction) a required point, worded by the model
    # only when the meaning survives
    BRIEF_CAUTIONS: Literal["model", "code"] = "model"
    SUMMARY_TIMEOUT_MS: int = 30000
    MARKET: str = "SG"  # D-129: data/markets/<code>.json (law)
    BROADCAST_LANGUAGE: str = "en"  # D-129: data/lang/<code>.json (wording); must be offered by MARKET
    STT_LOCATION: str = "us"
    STT_MODEL: str = "chirp_3"
    # D-305: chirp_3 endpointing (STANDARD cut pieces 73 -> 21 of 240 at the same WER; to be measured end to end)
    STT_ENDPOINTING: Literal["SHORT", "STANDARD", "SUPERSHORT"] = "STANDARD"  # D-336: the measured config
    STT_LANGUAGE: str = ""  # empty: the market pack's code for BROADCAST_LANGUAGE (D-129)
    STT_PHRASE_HINTS_ENABLED: bool = True
    # D-186: also hint the market's claim words (the reflex phrases of its rules, in the broadcast language) after
    # the glossary, so a risky word is not heard as a harmless sound-alike ("widens" for "whitens"). Off until measured
    STT_RISK_HINTS: bool = False
    # D-327: "record" adds each on-show release's names, sizes and test names from its approved record to the hints
    STT_HINTS: Literal["base", "record"] = "base"
    STT_HINT_BOOST: str = ""  # D-327: a boost (0-20) on the phrase set; empty = none (chirp_3 accepts it, probe 10/7)
    VERTEX_SEARCH_LOCATION: str = "global"
    VERTEX_SEARCH_DATA_STORE_ID: str = ""
    GCS_BUCKET: str = ""
    COMPLIANCE_ESCALATE_SEC: int = 5
    CORRECTED_TOAST_MS: int = 1500
    PUBLISH_CANCEL_WINDOW_MS: int = 2000
    # D-349/D-415: the context judge's transition verdict alone switches at once (no name match, no confirm, no
    # countdown); for SWITCH_DUAL_SCOPE_SEC after a switch or an undo the judges get both products, labelled
    SWITCH_DUAL_SCOPE_SEC: int = 10
    # D-351: the context call and its one retry share this deadline (immediate switch arm only)
    CONTEXT_RETRY_TOTAL_MS: int = 4000
    UNDO_SWITCH_WINDOW_SEC: int = 60
    STREAM_GRACE_SEC: int = 2
    HOST_TOP_N: int = 6  # D-113: the compact waiting list (cards are released one at a time by the AI PD)
    HOST_MIN_DWELL_SEC: int = 20
    HOST_REPEAT_THRESHOLD: int = 3  # D-113: an AI-answered question with this many askers is read out on air
    REPLY_COALESCE_SEC: int = 10
    STALE_COMMENT_SEC: int = 300
    # the show a new session is when nobody says: team = one host on air and an operator at the desk (the product's
    # normal case); solo = the host alone, with no operator screen in use
    DEFAULT_SHOW_MODE: Literal["team", "solo"] = "team"
    GROUP_TTL_SEC: int = 600
    GROUP_TTL_WAITING_SEC: int = 3600  # a question still waiting for the operator or the host
    JUDGE_MAX_OPEN_QUESTIONS: int = 5
    COMPOSER_TOP_K: int = 6
    COMMENT_RATE_LIMIT_PER_MIN: int = 120
    COMMENT_RATE_LIMIT_PER_AUTHOR_PER_MIN: int = 10
    MAX_COMMENT_CHARS: int = 300
    AUTO_ANSWER_ENABLED: bool = True
    # a price or size question the record settles is answered by code, with no LLM draft (logic/record_answers)
    # Routing has two outcomes: triage says whether a person must approve the reply; a question that needs none and
    # gets a verified draft is posted, everything else waits for the host or the operator. The intent is a label
    # (record answers, retrieval), and decides the route only when triage did not say (intents.json).
    # Questions are not grouped by meaning: only a comment that repeats a member's own words joins a group, and every
    # other question gets its own reply and its own row (hold-out runs: grouping by meaning merged different questions).
    RECORD_ANSWERS: bool = True
    # the wording of a record answer by the ReplyPhraser (the value stays the record's; code checks its numbers);
    # off, or on any failure, the plain sentence code wrote is posted
    RECORD_PHRASING: bool = True
    # a grounded draft the code gate rejects is written once more with the gate's reasons
    COMPOSER_REVISE: bool = True
    # a group whose draft failed because the composer's model call failed is drafted again this many times
    COMPOSE_RETRIES: int = 1
    COMPOSE_RETRY_AFTER_MS: int = 5000
    RECORD_PHRASING_TIMEOUT_MS: int = 3000
    # who settles a sensitive question (pregnancy, a condition, an allergy, an age limit, an efficacy claim), always
    # with a suggested reply. both: the host's card and the operator's review list at once; the host saying the
    # reply or the operator approving it posts it, whichever comes first. host: the host's card only (D-113).
    # operator: the operator's list only, and the host saying it posts nothing. A solo show has no operator.
    SENSITIVE_APPROVAL: Literal["both", "host", "operator"] = "both"
    # a posted reply is also shown in the language of viewers who asked in another language (pipelines/translation)
    REPLY_TRANSLATION_TIMEOUT_MS: int = 4000
    VIEWER_INPUT_ENABLED: bool = False
    DEMO_TOOLS_ENABLED: bool = True
    LOG_LEVEL: str = "INFO"

    @field_validator("JUDGE_TEMPERATURE", "JUDGE_SEED", "STT_HINT_BOOST")
    @classmethod
    def _sampling(cls, v: str, info) -> str:
        """D-314: a bad sampling value fails at startup, not inside a judge call (D-327: and the hint boost)."""
        v = v.strip()
        if v:
            n = (int if info.field_name == "JUDGE_SEED" else float)(v)
            if info.field_name == "STT_HINT_BOOST" and not 0 <= n <= 20:
                raise ValueError("STT_HINT_BOOST must be between 0 and 20")
        return v

    @model_validator(mode="after")
    def _check(self) -> "Settings":
        if self.SESSIONS_FIRESTORE:  # D-430: never stops the server
            import logging

            logging.getLogger(__name__).warning(
                "SESSIONS_FIRESTORE is merged into STORE=firestore (D-428); using STORE=firestore")
            self.STORE = "firestore"
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
