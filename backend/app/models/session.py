"""Runtime data model (DEV_SPEC §6.3). Firestore collection paths are in store/base.py."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SwitchState(BaseModel):  # in session doc
    """D-415: the immediate switch only (no counting, no pending countdown)."""
    last_commit: dict | None = None  # {closed_segment_id, opened_segment_id, at} for Undo
    # D-349: the product that left the air at the last switch or undo, and until when the judges also get its material
    # (labelled "previous")
    previous_product_id: str | None = None
    previous_until: int | None = None


class HostCue(BaseModel):  # in session doc (one active)
    cue_id: str
    text: str
    preset_id: str | None = None
    created_at: int
    status: Literal["active", "done", "cleared"]
    done_by_transcript_id: str | None = None


class PdCard(BaseModel):  # in session doc (one at a time): the AI PD's current suggestion (PLANNING 5.1.1)
    card_id: str
    # D-429: the AI PD makes no question cards any more; the three question kinds stay so a stored card still loads
    kind: Literal["answer_question", "read_question", "clarify_product", "shout_out", "cover_point", "promo",
                  "wrap_up", "switch_product"]
    say: str  # verified wording only: suggested answer, prompter point or promo text
    detail: str | None = None
    ref_id: str  # group_id | point_id | promo_id | product_id
    created_at: int
    hold_until: int  # not replaced before this
    status: Literal["active", "done", "dismissed", "expired"] = "active"
    source: Literal["ai", "rule"]
    reason: str = ""
    segment_id: str | None = None


class ActivePromo(BaseModel):  # in session doc (§8.10)
    promo_id: str
    started_at: int
    ends_at: int


class HostSlot(BaseModel):  # in session doc, ordered (§8.11)
    group_id: str
    pinned: bool = False
    on_host_since: int


class Session(BaseModel):  # [sessions/{session_id}]
    session_id: str
    runsheet_id: str
    title: str
    status: Literal["ready", "live", "ended"]
    # D-111: solo = the host runs the show alone; team = an operator is in the control room
    show_mode: Literal["solo", "team"] = "solo"
    # D-139: proof-plan §1 baseline. False: transcripts and comments are stored and shown, but no judge,
    # triage, answer or AI PD runs (what a host would have without the assistant).
    assistant: bool = True
    # D-142 (JAPAC B): the market (law) and broadcast language (wording) of this show, chosen at setup and
    # frozen for the session; the runtime loads that pack
    market: str = "SG"
    lang: str = "en"
    release_id: str | None = None  # D-218: an onboarded product's release; None for the shipped catalog
    release_ids: list[str] = []  # D-279: a show of 2-3 releases, in segment order (release_id is then None)
    started_at: int | None = None
    ended_at: int | None = None
    current_segment_id: str | None = None
    active_promo_id: str | None = None
    promo_started_at: int | None = None
    pinned_notice: str | None = None
    glossary_version: int = 0
    doc_version: int = 0
    settings_snapshot: dict = {}  # values of §5 at session start
    # Also stored in the session doc (§6.3, §8.7):
    pre_covered: dict[str, list[str]] = {}  # product_id -> point ids covered before it went on air
    switch: SwitchState = Field(default_factory=SwitchState)
    cue: HostCue | None = None
    pd_card: PdCard | None = None
    host_slots: list[HostSlot] = []
    active_promos: list[ActivePromo] = []  # all running promos; active_promo_id is the price-changing one
    # Prompter points confirmed on /setup, frozen at session creation (§12.7): product_id -> points
    prompter_points: dict[str, list[dict]] = {}
    created_at: int


class Segment(BaseModel):  # [sessions/{sid}/segments/{segment_id}]
    segment_id: str
    product_id: str
    order: int
    started_at: int
    ended_at: int | None = None
    start_reason: Literal["session_start", "auto_speech", "operator"]
    planned_duration_sec: int
    covered_point_ids: list[str] = []  # monotonic, never removed
    ticked_item_ids: list[str] = []  # D-372: prompter items (prices, ingredients, cautions) said right; monotonic
    reopen_times: list[int] = []  # D-381/382: every time an undo reopened this segment (a later undo adds, never moves)


class Transcript(BaseModel):  # [sessions/{sid}/transcripts/{transcript_id}]
    transcript_id: str
    text: str
    is_final: bool
    speech_start_at: int | None = None
    speech_end_at: int  # from STT result timing if provided, else receive time
    received_at: int
    source: Literal["mic", "injected"]
    segment_id: str
    # D-088: set when this final was judged together with the previous unfinished final(s)
    merged_from_transcript_id: str | None = None
    judged_text: str | None = None


class Alert(BaseModel):  # [sessions/{sid}/alerts/{alert_id}]
    alert_id: str
    kind: Literal["compliance", "fact"]
    status: Literal["active", "corrected", "dismissed", "cleared"]  # D-410/D-435: no provisional state
    transcript_id: str
    product_id: str
    # compliance
    rule_id: str | None = None
    severity: Literal["HIGH", "MEDIUM"] | None = None
    span: str | None = None
    say_instead: str | None = None
    evidence_ids: list[str] = []  # D-302: the relation arm's evidence sentence ids
    # fact
    field: str | None = None
    stated_value: str | None = None
    correct_value: str | None = None
    passage_id: str | None = None
    quote: str | None = None  # D-374: on a compliance alert, the model's summary of the cited section (not verbatim)
    citation: str | None = None  # D-374: compliance, the model's citation ("<document>#<section>") as it wrote it
    cited_title: str | None = None  # D-433: compliance, the cited document's readable name and section (host red box)
    say: str | None = None  # D-396: fact note, the model's line the host says to fix it
    # timing
    created_at: int
    shown_at: int | None = None  # became active; escalation and latency use this
    host_rendered_at: int | None = None
    escalated_at: int | None = None
    resolved_at: int | None = None
    corrected_by_transcript_id: str | None = None
    corrected_text: str | None = None
    dismissed_reason: str | None = None


class Comment(BaseModel):  # [sessions/{sid}/comments/{comment_id}]
    comment_id: str
    author_id: str
    author_name: str
    text: str
    received_at: int
    source: Literal["viewer", "script", "pool"]
    visibility: Literal["visible", "hidden"] = "visible"
    hide_category: str | None = None
    kind: Literal["pending", "reaction", "question", "hide"] = "pending"
    analysis_id: str | None = None
    group_id: str | None = None
    armor: Literal["blocked", "unscreened"] | None = None  # D-125: never triaged, answered or carded
    language: str | None = None  # the comment's language as triage read it (ISO 639-1), when it is not the show's
    translation_en: str | None = None  # triage's English reading of a comment in another language (operator view)
    signal: Literal["stream_issue", "injection"] | None = None  # triage: a stream problem report, or orders to the system
    # what the asker is told while the question waits (logic/reply_status); kept in step with its group by the runtime
    reply_status: Literal["checking", "host", "team", "answered"] | None = None


class CommentAnalysis(BaseModel):  # [sessions/{sid}/analyses/{analysis_id}]
    analysis_id: str
    comment_id: str
    output: dict  # CommentTriageOutput or prefilter verdict
    product_id: str | None = None
    product_basis: Literal["explicit", "context", "content", "unknown", "operator"]
    context_product_id: str | None = None  # product on air at received_at - STREAM_GRACE_SEC
    route: Literal["AUTO", "HOST", "OPERATOR"] | None = None
    route_reason: str | None = None
    source: Literal["prefilter", "cache", "llm", "fallback", "armor", "unscreened"]
    latency_ms: int | None = None


class QuestionGroup(BaseModel):  # [sessions/{sid}/groups/{group_id}]
    group_id: str
    product_id: str | None = None
    intent: str
    condition_slots: dict[str, str | None]
    canonical_question: str
    member_comment_ids: list[str]
    unique_author_ids: list[str]
    first_at: int
    last_at: int
    route: Literal["AUTO", "HOST", "OPERATOR"]
    route_reason: str
    needs_approval: bool | None = None  # triage's call on its first question; None: not said
    approval_reason: str | None = None
    status: Literal["new", "composing", "ready", "auto_answered", "needs_review", "answered", "rejected", "closed"]
    answer_id: str | None = None  # verified suggested/posted answer
    host_slot: Literal["none", "on_host"] = "none"
    on_host_since: int | None = None
    pinned_by_operator_at: int | None = None
    recalled_at: int | None = None  # operator recall; not re-added for 60 s (§8.13)
    host_verbal_answer_transcript_id: str | None = None  # host answered but nothing was posted
    host_confirmed: bool = False  # host answered an already AI-answered group
    published_message_id: str | None = None  # last reply message (for coalescing)
    closed_reason: str | None = None  # e.g. "ttl", "promo_changed"
    score: float = 0.0
    version: int = 0


class Answer(BaseModel):  # [sessions/{sid}/answers/{answer_id}]
    answer_id: str
    group_id: str | None = None
    text: str
    citations: list[dict]  # {passage_id, quote, section, doc}
    origin: Literal["ai", "operator_edit", "operator_written"]
    verified: bool
    verify_errors: list[str]
    cache_key: str | None = None
    needs_human: bool
    created_at: int
    record: bool = False  # a record answer: the value by code from the product record (logic/record_answers)


class Message(BaseModel):  # [sessions/{sid}/messages/{message_id}] viewer-visible
    message_id: str
    kind: Literal["ai_answer", "host_answer", "brand_answer", "notice", "correction_notice"]
    text: str
    group_id: str | None = None
    reply_to_comment_ids: list[str]
    reply_to_author_names: list[str]
    citations: list[dict]
    state: Literal["pending", "published", "cancelled"]
    created_at: int
    publish_at: int | None = None
    published_at: int | None = None
    idempotency_key: str
    translations: dict[str, str] = {}  # language -> this reply in it, for viewers who asked in that language


class AgentCall(BaseModel):  # [sessions/{sid}/agent_calls/{id}] audit
    call_id: str
    agent: str
    model: str
    prompt_version: str
    started_at: int
    latency_ms: int
    status: Literal["ok", "timeout", "error", "invalid"]
    input_hash: str
    input_preview: str
    output: dict | None = None
    error: str | None = None
    usage: dict | None = None  # D-187: tokens {prompt, output, thoughts, cached} as the model reported them
    failure: str | None = None  # D-306: http_504, client_timeout, http_429 or other_error (None when ok)
    temperature: float | None = None  # D-314: the sampling sent (None = the model's default)
    seed: int | None = None


class Event(BaseModel):  # [sessions/{sid}/events/{seq}]
    seq: int
    session_id: str
    type: str
    at: int
    payload: dict
