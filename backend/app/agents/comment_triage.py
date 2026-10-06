"""CommentTriage agent (DEV_SPEC §7.5): classifies one viewer comment. Code decides route,
purchase impact and sensitivity from intents.json."""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field

from ..config import Settings
from ..logic.catalog import Catalog
from ..logic.grouping import normalise_question
from ..models.agent_io import (SLOT_KEYS, CommentTriageBatchOutput, CommentTriageBatchOutputB, CommentTriageOutput,
                               CommentTriageOutputB, ConditionSlots)
from ..models.session import QuestionGroup
from ..providers.llm import MOCK_FIXTURES_DIR, AgentResult, LLMClient, LLMRequest, MockBackend
from ..providers.prompts import PromptTemplate
from . import arms, inputs

GROUP_REF = "@group:"
MAX_CANONICAL_FALLBACK = 120


@dataclass
class TriageInput:
    text: str  # full comment text; truncated to MAX_COMMENT_CHARS for the model
    context_product_id: str | None
    open_groups: list[QuestionGroup] = field(default_factory=list)
    host_line: str | None = None  # D-157: the host's last final, for a short comment only
    session_id: str | None = None
    scenario: str = "default"


def post_validate(out: CommentTriageOutput, catalog: Catalog, text: str, open_group_ids: set[str]) -> CommentTriageOutput:
    o = out.model_copy(deep=True)
    if o.product_id is not None and not catalog.is_product(o.product_id):
        o.product_id, o.product_basis = None, "unknown"
    if o.product_id is None and o.product_basis in ("explicit", "content"):
        o.product_basis = "unknown"
    intents = catalog.pack.intents_by_name
    if o.intent is not None and o.intent not in intents:
        o.intent = "other"
    if o.kind == "question" and o.intent is None:
        o.intent = "other"
    allowed = catalog.pack.intents.condition_slots
    for key in SLOT_KEYS:
        value = getattr(o.condition_slots, key)
        if value is None:
            continue
        if not allowed.get(key):  # D-278: a free slot (person type, condition, combined with): a short phrase
            value = " ".join(value.lower().split())[:MAX_SLOT_CHARS] or None
            setattr(o.condition_slots, key, value)
        elif value not in allowed[key]:
            setattr(o.condition_slots, key, None)
    if o.group_candidate_id not in open_group_ids:
        o.group_candidate_id = None
    if o.kind == "question" and not o.canonical_question.strip():
        o.canonical_question = text.strip()[:MAX_CANONICAL_FALLBACK]
    if o.kind == "hide" and o.hide_category is None:
        o.hide_category = "spam"
    return o


class CommentTriage:
    name = "comment_triage"

    def __init__(self, llm: LLMClient, prompt: PromptTemplate, catalog: Catalog, settings: Settings,
                 batch_prompt: PromptTemplate | None = None) -> None:
        self.llm = llm
        self.prompt = prompt
        self.batch_prompt = batch_prompt
        self.prompt_version = prompt.version
        self.model = llm.fast.model
        self.catalog = catalog
        self.settings = settings
        self.b = arms.meaning_to_llm(settings.DESIGN_ARM)  # D-187 arm B: shout-outs are a triage label

    def _groups(self, open_groups: list[QuestionGroup]):
        """OPEN_GROUPS for the prompt, their ids, and the fixture encode/decode of group ids."""
        groups = inputs.open_groups_json(open_groups, self.settings.TRIAGE_MAX_OPEN_GROUPS)
        by_question = {normalise_question(g["canonical_question"]): g["group_id"] for g in groups}
        id_to_question = {g["group_id"]: normalise_question(g["canonical_question"]) for g in groups}

        def encode(data: dict) -> dict:
            gid = data.get("group_candidate_id")
            if gid in id_to_question:
                data["group_candidate_id"] = GROUP_REF + id_to_question[gid]
            return data

        def decode(data: dict) -> dict:
            ref = data.get("group_candidate_id")
            if isinstance(ref, str) and ref.startswith(GROUP_REF):
                data["group_candidate_id"] = by_question.get(ref[len(GROUP_REF):])
            return data

        return groups, {g["group_id"] for g in groups}, encode, decode

    async def run(self, inp: TriageInput, *, deadline_ms: int) -> AgentResult[CommentTriageOutput]:
        groups, group_ids, encode, decode = self._groups(inp.open_groups)
        user = self.prompt.render({
            "products_compact_json": inputs.products_compact_json(self.catalog),
            "product_id_at_comment_time_minus_grace": inputs.product_id_at_comment_time_minus_grace(inp.context_product_id),
            "recent_host_line_json_or_null": inputs.recent_host_line_json_or_null(inp.host_line),
            "intent_names_json": inputs.intent_names_json(self.catalog),
            "condition_slots_json": inputs.condition_slots_json(self.catalog.pack.intents.condition_slots),
            "open_groups_json": groups,
            "comment_text": inputs.comment_text(inp.text, self.settings.MAX_COMMENT_CHARS),
        })
        res = await self.llm.call(LLMRequest(
            agent=self.name, model=self.llm.triage.model, thinking_level=self.llm.triage.thinking_level,
            prompt_version=self.prompt_version,
            system_instruction=arms.system_instruction(self.prompt.system_instruction, self.name,
                                                       self.settings.DESIGN_ARM, self.settings.prompts_path),
            user_message=user, output_model=CommentTriageOutputB if self.b else CommentTriageOutput,
            deadline_ms=deadline_ms,
            session_id=inp.session_id, mock_primary_text=inp.text, mock_scenario=inp.scenario,
            mock_fallback=lambda _: rule_based_triage(inp.text, inp.context_product_id, self.catalog),
            fixture_encode=encode, fixture_decode=decode, preview=inp.text,
        ))
        if res.output is not None:
            res.output = post_validate(res.output, self.catalog, inp.text, group_ids)
        return res

    async def run_batch(self, inps: list[TriageInput], *, deadline_ms: int) -> list[AgentResult[CommentTriageOutput]]:
        """Several waiting comments in one call (PLANNING 5.1.2). All items share `inps[0].open_groups`.
        Items the model leaves out, or a failed call, fall back to one `run` per comment."""
        assert self.batch_prompt is not None, "run_batch needs the comment_triage_batch prompt"
        groups, group_ids, encode, decode = self._groups(inps[0].open_groups)
        user = self.batch_prompt.render({
            "products_compact_json": inputs.products_compact_json(self.catalog),
            "intent_names_json": inputs.intent_names_json(self.catalog),
            "condition_slots_json": inputs.condition_slots_json(self.catalog.pack.intents.condition_slots),
            "open_groups_json": groups,
            "comments_json": inputs.comments_json([(x.text, x.context_product_id, x.host_line) for x in inps],
                                                  self.settings.MAX_COMMENT_CHARS),
        })

        def each(data: dict, fn) -> dict:
            data["items"] = [fn(it) for it in data.get("items", [])]
            return data

        res = await self.llm.call(LLMRequest(
            agent="comment_triage_batch", model=self.llm.triage.model, thinking_level=self.llm.triage.thinking_level,
            prompt_version=self.batch_prompt.version,
            system_instruction=arms.system_instruction(self.batch_prompt.system_instruction, "comment_triage_batch",
                                                       self.settings.DESIGN_ARM, self.settings.prompts_path),
            user_message=user, output_model=CommentTriageBatchOutputB if self.b else CommentTriageBatchOutput,
            deadline_ms=deadline_ms,
            session_id=inps[0].session_id, mock_primary_text="\n".join(x.text for x in inps),
            mock_scenario=inps[0].scenario,
            mock_fallback=lambda _: {"items": [{**self._mock_one(x, decode), "i": i} for i, x in enumerate(inps)]},
            fixture_encode=lambda d: each(d, encode), fixture_decode=lambda d: each(d, decode),
            preview=f"{len(inps)} comments",
        ))
        by_i = {it.i: it for it in res.output.items} if res.output is not None else {}
        out: list[AgentResult[CommentTriageOutput] | None] = []
        for i, x in enumerate(inps):
            it = by_i.get(i)
            if it is None:
                out.append(None)
                continue
            one = (CommentTriageOutputB if self.b else CommentTriageOutput).model_validate(it.model_dump(exclude={"i"}))
            out.append(AgentResult(res.status, post_validate(one, self.catalog, x.text, group_ids), res.latency_ms,
                                   res.call_id, res.error, res.meta))
        missing = [i for i, r in enumerate(out) if r is None]
        if missing:
            singles = await asyncio.gather(*(self.run(inps[i], deadline_ms=self.settings.TRIAGE_TIMEOUT_MS)
                                             for i in missing))
            for i, r in zip(missing, singles):
                out[i] = r
        return out  # type: ignore[return-value]

    def _mock_one(self, inp: TriageInput, decode) -> dict:
        """Mock provider: the recorded single-comment fixture if there is one, so a burst replays
        the same demo outputs batched or not; else the rule-based triage."""
        mock = MockBackend(getattr(self.llm.backend, "fixtures_dir", MOCK_FIXTURES_DIR))
        for scenario in dict.fromkeys((inp.scenario, "default")):
            path = mock.fixture_path(self.name, inp.text, scenario)
            if path.is_file():
                return decode(json.loads(path.read_text(encoding="utf-8")))
        return rule_based_triage(inp.text, inp.context_product_id, self.catalog)


# ---- rule-based fallback for unit tests (mock provider without a fixture) -----------------------

MAX_SLOT_CHARS = 40
_INTENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("pregnancy_breastfeeding", ("pregnan", "breastfeed")),
    ("medical_condition", ("eczema", "dermatitis", "rosacea")),
    ("efficacy_claim", ("wrinkle", "scar")),
    ("allergy_sensitivity", ("sting", "tingl", "allerg", "irritat")),
    ("shipping", ("ship", "deliver")),
    ("returns", ("return", "refund")),
    ("payment", ("paynow", "payment", "pay ")),
    ("set_price", ("set price", "the set", "set with")),
    ("promo", ("time sale", "promo", "discount")),
    ("ingredient_amount", ("how much of the", "percent", "%")),
    ("price", ("price", "how much", "cost")),
    ("volume", (" ml", "how big", "size")),
    ("fragrance", ("fragrance", "scent", "smell")),
    ("compatibility", ("use it under", "use it over", "use it with", "together with", "use with", "combine")),
    ("suitability", ("suitable for", "good for", "ok for", "okay for", "work for me")),
    ("how_to_use", ("morning", "night", "how to use", "how often", "mix")),
    ("texture", ("sticky", "texture", "heavy", "greasy")),
    ("origin", ("made",)),
    ("ingredients", ("ingredient", "contain")),
]
_QUESTION_HINT = re.compile(r"\?|\b(how|what|can|is|does|do|will|which|where|when|pls|please)\b", re.IGNORECASE)


def rule_based_triage(text: str, context_product_id: str | None, catalog: Catalog) -> dict:
    t = f" {text.lower()} "
    empty_slots = ConditionSlots(person_type=None, life_stage=None, condition=None, combined_with=None, time_of_day=None)
    if "[link removed]" in text and not _QUESTION_HINT.search(text):
        # D-234: the no-LLM stand-in (unit tests, mock demo) hides a link comment that asks nothing; the real triage
        # decides spam vs question itself
        return CommentTriageOutput(kind="hide", hide_category="link", product_id=None, product_basis="unknown",
                                   intent=None, condition_slots=empty_slots, canonical_question="",
                                   group_candidate_id=None, reason="rule-based: link without a question").model_dump()
    if not _QUESTION_HINT.search(text):
        return CommentTriageOutput(kind="reaction", hide_category=None, product_id=None, product_basis="unknown",
                                   intent=None, condition_slots=empty_slots, canonical_question="",
                                   group_candidate_id=None, reason="rule-based: no question").model_dump()
    intent = next((name for name, keys in _INTENT_RULES if any(k in t for k in keys)), "other")
    slots = empty_slots.model_copy()
    if m := re.search(r"\b(?:suitable|good|ok|okay|fine) for (?:my\s+)?([a-z]+(?: [a-z]+)?)", t):  # D-278: any person type
        slots.person_type = m.group(1)
    if "pregnan" in t:
        slots.life_stage = "pregnant"
    elif "breastfeed" in t:
        slots.life_stage = "breastfeeding"
    if m := re.search(r"\b(?:together with|use with|combine with)\s+(?:my\s+|a\s+|the\s+)?([a-z]+(?: [a-z]+)?)", t):
        slots.combined_with = m.group(1)
    named = catalog.product_by_alias(text)
    scope = catalog.pack.intents_by_name[intent].product_scope
    if scope == "none":
        pid, basis = None, "unknown"
    elif named:
        pid, basis = named, "explicit"
    else:
        pid, basis = context_product_id, "context" if context_product_id else "unknown"
    return CommentTriageOutput(kind="question", hide_category=None, product_id=pid, product_basis=basis,
                               intent=intent, condition_slots=slots, canonical_question=text.strip()[:120],
                               group_candidate_id=None, reason="rule-based").model_dump()
