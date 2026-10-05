"""UtteranceJudge agent (DEV_SPEC §7.3): compliance, correction, answer linking, prompter and switch
in one call (`JUDGE_MODE=split`). `JUDGE_MODE=single` adds the fact check to the same call
(judge_single.md). The default `split3` cuts the same jobs into two calls (split_judges.py, D-099);
the input values, checks and rule-based fallbacks here are shared with it."""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from ..logic.catalog import Catalog
from ..logic import qualifier
from ..logic.grouping import normalise_question
from ..logic.reflex import Reflex
from ..models.agent_io import JudgeSingleOutput, UtteranceJudgeOutput
from ..models.data import Passage, Promo, PrompterPoint
from ..models.session import Alert, HostCue, QuestionGroup, SwitchState
from ..providers.llm import AgentResult, LLMClient, LLMRequest
from ..providers.prompts import PromptTemplate
from . import fact_checker, inputs

GROUP_REF, ALERT_REF = "@group:", "@alert:"
STATIC_JUDGE_KEYS = frozenset({"current_product_json", "run_sheet_compact_json",
                             "approved_claims_of_current_product_json", "rules_compact_json",
                             "prompter_points_json", "passages_json"})


@dataclass
class JudgeInput:
    utterance: str
    on_air: str
    active_alerts: list[Alert] = field(default_factory=list)
    open_questions: list[tuple[QuestionGroup, str | None]] = field(default_factory=list)
    on_screen_group_id: str | None = None  # D-112: the question card the host sees now
    cue: HostCue | None = None
    previous: list[str] = field(default_factory=list)
    points_by_product: dict[str, list[PrompterPoint]] | None = None
    session_id: str | None = None
    scenario: str = "default"
    # single mode only
    switch: SwitchState = field(default_factory=SwitchState)
    promo: Promo | None = None
    passages: list[Passage] = field(default_factory=list)


def spoken_claim(text: str) -> str:
    """The '*' of an approved claim marks the in-house-test qualifier; the host must say the
    qualifier, not read the asterisk (§8.4.3 rule, also applied to judge output, D-062)."""
    claim = text.strip()
    if "*" not in claim:
        return claim
    claim = claim.replace("*", "").rstrip()
    if "in-house test" in claim.lower():
        return claim
    if claim.endswith("."):
        claim = claim[:-1]
    return claim + " in our in-house test."


def qualified_say(say: str, on_air, catalog: Catalog) -> str:
    """D-131 (holdout H090): a say-instead line with a number of an in-house result carries the qualifier,
    even when the model copied the approved claim without its '*'. Otherwise the host gets a
    test-qualifier alert for saying exactly the line they were given."""
    say = spoken_claim(say)
    lex = catalog.lexicon
    if on_air is None or lex.is_qualified(say):
        return say
    r = qualifier.approved_replacement(say, on_air, [p for p in catalog.products if p is not on_air], lex)
    numbers = {w for w in lex.content_words(say) if w.isdigit()}
    return r.say if r is not None and numbers & set(r.numbers) else say


def say_instead_fallback(catalog: Catalog, product_id: str) -> str:
    """§8.4.3: the on-air product's first approved claim, with the in-house-test qualifier."""
    return spoken_claim(catalog.approved_claims(product_id)[0])


APPROVED_SPAN_MIN = 0.8
LEAD_IN_MAX_WORDS = 8  # D-146: "In our in-house test," said as its own final


# D-132: product-sheet sections whose statements the host may repeat. Not "Cautions" (a warning's words
# reused out of context could hide a claim) and not "Approved on-air claims", which also lists the claims
# NOT approved (the approved ones come from the product's own list); a FAQ passage counts by its answer.
SHEET_SECTIONS = frozenset({"Product overview", "Key facts", "Key ingredients", "How to use",
                            "In-house test results", "Frequently asked questions"})


def _sheet_statements(passages) -> list[str]:
    """One sentence at a time, so words from different sentences never add up to a claim."""
    out = []
    for p in passages:
        if p.section in SHEET_SECTIONS:
            text = p.text.split(" A: ", 1)[1] if " A: " in p.text else p.text
            out += [x for x in re.split(r"(?<=[.!?;])\s+", text) if x]
    return out


def _is_approved_wording(span: str, product, lex, passages=()) -> bool:
    """The flagged words are the product's own approved wording: an approved claim, an approved in-house
    result, a prompter point or a statement of its product sheet (D-132, sealed AW010: "suitable for all
    skin types" is in the cream's sheet) - at least 80% of the span's content words, every number of it."""
    words = lex.content_words(span)
    if len(words) < 3:
        return False
    numbers = {w for w in words if w.isdigit()}
    texts = [*product.approved_claims, *(r.say for r in product.qualified_results),
             *(p.text for p in product.prompter_points), *_sheet_statements(passages)]
    for text in texts:
        heard = lex.content_words(text)
        if lex.coverage(words, heard) >= APPROVED_SPAN_MIN and numbers <= set(heard):
            return True
    return False


def _span_phrase(span: str, text: str, lex) -> str:
    """D-174: a span too short to compare ("all users") is compared with the phrase around it in the utterance
    (between commas or sentence marks): "all skin types and all users" is the sheet's own wording."""
    if len(lex.content_words(span)) >= 3:
        return span
    return next((part.strip() for part in re.split(r"[,;:.!?]", text) if span.lower() in part.lower()), span)


def validate_compliance(o, catalog: Catalog, values: dict):
    """In place, on any output with `compliance` and `correction`: drop unknown rules and alert ids
    that were not in the input; severity comes from the rule."""
    rules = catalog.pack.rules_by_id
    text = values.get("utterance_text") or ""
    # D-105: a sentence that names our own test never breaks the test-qualifier rule
    # D-146 (sealed show replay): speech-to-text split "In our in-house test," from "skin hydration went up 38% ...";
    # a short lead-in final just before, naming our test and no number, qualifies this one
    prev = (values.get("last_two_final_transcripts_json") or [])[-1:]
    lead_in = (bool(prev) and catalog.lexicon.is_qualified(prev[0]) and not any(ch.isdigit() for ch in prev[0])
               and len(prev[0].split()) <= LEAD_IN_MAX_WORDS)
    qualified = catalog.lexicon.is_qualified(text) or lead_in
    o.compliance.violations = [v for v in o.compliance.violations if v.rule_id in rules
                               and not (v.rule_id == qualifier.RULE_ID and qualified)]
    # D-148 (sealed show replay): STT made "Acne, um, no no," its own final and the judge flagged the word
    # "acne" (HIGH) before the host went on "we cannot say it treats acne". A final that is nothing but the
    # flagged word and fillers is a topic, not a claim.
    lex = catalog.lexicon
    said = [w for w in lex.content_words(text) if w not in lex.fillers]
    o.compliance.violations = [v for v in o.compliance.violations
                               if not (len(said) == 1 and lex.content_words(v.span) == said)]
    kept = []
    on_air_id = (values.get("current_product_json") or {}).get("product_id")
    on_air_product = catalog.get_product(on_air_id) if catalog.is_product(on_air_id) else None
    for v in o.compliance.violations:
        v.severity = rules[v.rule_id].severity
        if (on_air_product is not None and v.rule_id != qualifier.RULE_ID
                and _is_approved_wording(_span_phrase(v.span, text, catalog.lexicon), on_air_product, catalog.lexicon,
                                         [p for p in catalog.pack.passages if p.product_id == on_air_product.product_id])):
            continue  # D-123: approved product wording is never a violation (the qualifier rule still applies)
        if v.rule_id == qualifier.RULE_ID:  # approved wording only, never the model's (D-105)
            on_air = catalog.get_product(values["current_product_json"]["product_id"])
            r = qualifier.approved_replacement(text, on_air, [p for p in catalog.products if p is not on_air],
                                               catalog.lexicon)
            if r is None:
                continue  # D-116: the sentence matches no in-house test result (an amount, price or volume)
            v.say_instead = r.say
        else:
            v.say_instead = qualified_say(v.say_instead, on_air_product, catalog)
        kept.append(v)
    o.compliance.violations = kept
    alert_ids = {a["alert_id"] for a in values["active_alerts_json"]}
    o.correction.corrects_alert_ids = [a for a in dict.fromkeys(o.correction.corrects_alert_ids) if a in alert_ids]
    return o


def validate_context(o, catalog: Catalog, values: dict):
    """In place, on any output with `answer` and `prompter`: drop group, point and cue ids that were
    not in the input, and an unknown switch target."""
    group_ids = {q["group_id"] for q in values["open_questions_json"]}
    if o.answer.matched_group_id is not None and o.answer.matched_group_id not in group_ids:
        o.answer.matched_group_id = None
        o.answer.is_answer = o.answer.consistent_with_suggested = False
    point_ids = {p["point_id"] for p in values["prompter_points_json"]}
    o.prompter.covered_point_ids = [p for p in dict.fromkeys(o.prompter.covered_point_ids) if p in point_ids]
    cue_ids = {c["cue_id"] for c in values["host_cues_json"]}
    o.prompter.covered_cue_ids = [c for c in o.prompter.covered_cue_ids if c in cue_ids]
    if not catalog.is_product(o.prompter.switch.target_product_id):
        o.prompter.switch.target_product_id = None
    return o


def post_validate(out: UtteranceJudgeOutput, catalog: Catalog, values: dict) -> UtteranceJudgeOutput:
    """Drop unknown rules and any id that was not in the input lists; severity comes from the rule."""
    o = out.model_copy(deep=True)
    return validate_context(validate_compliance(o, catalog, values), catalog, values)


def build_judge_values(catalog: Catalog, inp: JudgeInput, single: bool = False) -> dict:
    """Prompt values shared by the UtteranceJudge, judge_single and the split judges (D-099)."""
    values = {
        "current_product_json": inputs.current_product_json(catalog, inp.on_air),
        "run_sheet_compact_json": inputs.run_sheet_compact_json(catalog, inp.on_air),
        "approved_claims_of_current_product_json": inputs.approved_claims_of_current_product_json(catalog, inp.on_air),
        "rules_compact_json": inputs.rules_compact_json(catalog),
        "active_alerts_json": inputs.active_alerts_json(inp.active_alerts),
        "open_questions_json": inputs.open_questions_json(inp.open_questions, len(inp.open_questions),
                                                          inp.on_screen_group_id),
        "prompter_points_json": inputs.prompter_points_json(catalog, inp.on_air, inp.points_by_product),
        "host_cues_json": inputs.host_cues_json(inp.cue),
        "last_two_final_transcripts_json": inp.previous[-2:],
        "utterance_text": inputs.utterance_text(inp.utterance),
    }
    if single:
        values |= {
            "switch_context_json": inputs.switch_context_json(catalog, inp.switch, inp.on_air),
            "active_promo_json_or_null": inputs.active_promo_json_or_null(catalog, inp.promo),
            "set_offers_json": inputs.set_offers_json(catalog, inp.promo),
            "passages_json": inputs.passages_json(inp.passages),
        }
    return values


def symbolic_ids(values: dict) -> tuple[Callable[[dict], dict], Callable[[dict], dict]]:
    """Fixture encode/decode: group and alert ids are new in every session, so a recorded fixture
    names a group by its question and an alert by its span."""
    group_q = {q["group_id"]: normalise_question(q["canonical_question"]) for q in values["open_questions_json"]}
    alert_span = {a["alert_id"]: normalise_question(a["span"] or "") for a in values["active_alerts_json"]}
    q_group = {v: k for k, v in group_q.items()}
    span_alert = {v: k for k, v in alert_span.items()}

    def encode(data: dict) -> dict:
        ans = data.get("answer") or {}
        if ans.get("matched_group_id") in group_q:
            ans["matched_group_id"] = GROUP_REF + group_q[ans["matched_group_id"]]
        corr = data.get("correction") or {}
        corr["corrects_alert_ids"] = [ALERT_REF + alert_span[a] if a in alert_span else a
                                      for a in corr.get("corrects_alert_ids", [])]
        return data

    def decode(data: dict) -> dict:
        ans = data.get("answer") or {}
        ref = ans.get("matched_group_id")
        if isinstance(ref, str) and ref.startswith(GROUP_REF):
            ans["matched_group_id"] = q_group.get(ref[len(GROUP_REF):])
        corr = data.get("correction") or {}
        ids = []
        for a in corr.get("corrects_alert_ids", []):
            if isinstance(a, str) and a.startswith(ALERT_REF):
                a = span_alert.get(a[len(ALERT_REF):])
            if a:
                ids.append(a)
        corr["corrects_alert_ids"] = ids
        return data

    return encode, decode


class UtteranceJudge:
    name = "utterance_judge"

    def __init__(self, llm: LLMClient, prompts: dict[str, PromptTemplate], catalog: Catalog, reflex: Reflex,
                 *, single: bool = False) -> None:
        self.llm = llm
        self.single = single
        self.prompt = prompts["judge_single" if single else "utterance_judge"]
        self.prompt_version = self.prompt.version
        self.model = llm.fast.model
        self.catalog = catalog
        self.reflex = reflex

    def build_values(self, inp: JudgeInput) -> dict:
        return build_judge_values(self.catalog, inp, self.single)

    async def run(self, inp: JudgeInput, *, deadline_ms: int) -> AgentResult:
        values = self.build_values(inp)
        encode, decode = symbolic_ids(values)
        output_model = JudgeSingleOutput if self.single else UtteranceJudgeOutput
        user, prefix = self.prompt.render_cached(values, STATIC_JUDGE_KEYS)
        res = await self.llm.call(LLMRequest(
            agent="judge_single" if self.single else self.name, model=self.llm.fast.model,
            thinking_level=self.llm.fast.thinking_level, prompt_version=self.prompt_version,
            system_instruction=self.prompt.system_instruction, user_message=user,
            cache_prefix=prefix, cache_ttl_sec=sum(i.planned_duration_sec for i in self.catalog.runsheet.items),
            output_model=output_model, deadline_ms=deadline_ms, session_id=inp.session_id,
            mock_primary_text=inp.utterance, mock_scenario=inp.scenario,
            mock_fallback=lambda _: rule_based_judge(inp, values, self.catalog, self.reflex, self.single),
            fixture_encode=encode, fixture_decode=decode, preview=inp.utterance,
        ))
        if res.output is not None:
            validated = post_validate(res.output, self.catalog, values)
            if self.single:
                validated.facts = fact_checker.post_validate(res.output.facts, inp.passages, self.catalog, inp.promo,
                                                             inp.utterance)
            res.output = validated
        return res


# ---- rule-based fallback for unit tests ----------------------------------------------------------

_CORRECTION = re.compile(r"\b(correct that|my mistake|sorry|let me correct)\b", re.IGNORECASE)


def rule_based_compliance(inp: JudgeInput, values: dict, catalog: Catalog, reflex: Reflex) -> dict:
    seen, violations = set(), []
    for h in reflex.scan(inp.utterance):
        if h.rule_id in seen:
            continue
        seen.add(h.rule_id)
        violations.append({"span": h.phrase, "rule_id": h.rule_id, "severity": h.severity, "is_negated": h.negated,
                           "is_quoted": h.quoted, "say_instead": say_instead_fallback(catalog, inp.on_air)})
    corrects = [a["alert_id"] for a in values["active_alerts_json"]] if _CORRECTION.search(inp.utterance) else []
    return {"compliance": {"violations": violations}, "correction": {"corrects_alert_ids": corrects}, "reason": "rule-based"}


def rule_based_context(inp: JudgeInput, catalog: Catalog) -> dict:
    nxt = catalog.next_product(inp.on_air)
    t = inp.utterance.lower()
    switch = {"is_transition": False, "is_quote": False, "target_product_id": None, "confidence": "low"}
    if nxt and catalog.product_by_alias(t) == nxt and re.search(r"\b(show you|next up|now let)\b", t):
        switch = {"is_transition": True, "is_quote": False, "target_product_id": nxt, "confidence": "high"}
    elif re.search(r"\bback to\b", t) and catalog.product_by_alias(t) == inp.on_air:
        switch = {"is_transition": True, "is_quote": False, "target_product_id": inp.on_air, "confidence": "high"}
    return {
        "answer": {"utterance_type": "correction" if _CORRECTION.search(inp.utterance) else "product_talk",
                   "matched_group_id": None, "is_answer": False, "consistent_with_suggested": False},
        "prompter": {"covered_point_ids": [], "covered_cue_ids": [], "switch": switch},
        "reason": "rule-based",
    }


def rule_based_judge(inp: JudgeInput, values: dict, catalog: Catalog, reflex: Reflex, single: bool) -> dict:
    out = rule_based_compliance(inp, values, catalog, reflex) | rule_based_context(inp, catalog)
    if single:
        out["facts"] = {"claims": [], "reason": "rule-based"}
    return out
