"""FactChecker agent (DEV_SPEC §7.4): checks product facts in one host sentence against the sheets."""
from __future__ import annotations

import contextvars
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from ..logic.catalog import Catalog
from ..logic.verify import number_set
from ..models.agent_io import (FactCheckOutput, FactClaim, FactRelationOutput, FactRelationOutputC,
                               FactRelationOutputH, FactRelationOutputV2, FactRelationOutputV5,
                               FactRelationOutputV7, with_note_checks, with_same_as)
from ..onboarding.numwords import numbers_in_text, plain as plain_number
from ..models.data import Passage, Promo
from ..models.session import SwitchState
from ..providers.llm import AgentResult, LLMClient, LLMRequest
from ..providers.prompts import PromptTemplate
from ..providers.retriever import Retriever
from . import inputs

log = logging.getLogger(__name__)

# D-406: sent only with a merged line's re-judgment (a line speech-to-text split)
MERGED_NOTE = (
    'UTTERANCE joins lines that speech-to-text split. `chain_handles` are the ACTIVE_FACT_NOTES entries '
    'raised from those lines. For each `contradicts` claim, `same_as` is the one of `chain_handles` whose '
    'wrong fact it repeats (the same fact from the split line), else null. Example: F1 is host_said "ten '
    'percent niacin"; UTTERANCE "So niacin is ten percent, and the tube is 30 ml." gives the niacin claim '
    '`same_as` "F1" and the tube claim null.')

CLAIMS_SECTION = "Approved on-air claims"
# D-250: the eval collects the drops of one case here (a list set by the caller; tasks inherit it)
DROPS: contextvars.ContextVar[list | None] = contextvars.ContextVar("fact_drops", default=None)


def _drop(c, why: str) -> None:
    """D-248 (sealed FR run: 3 of 4 right model corrections dropped in silence): code may overrule the model, but
    never silently; the reason is logged with the claim."""
    log.info("fact claim dropped by code: %s | field=%s stated=%r correct=%r passage=%s", why, c.field,
             c.stated_value, c.correct_value, c.passage_id)
    if (sink := DROPS.get()) is not None:
        sink.append({"reason": why, "field": c.field, "stated": c.stated_value, "correct": c.correct_value,
                     "passage_id": c.passage_id, "quote": c.quote})
    c.verdict = "not_in_sources"



PRICE_FIELDS = ("price", "set_price", "promo")


@dataclass
class FactInput:
    utterance: str
    on_air: str
    switch: SwitchState
    promo: Promo | None
    passages: list[Passage]
    previous: list[str] = field(default_factory=list)
    offers: list[Promo] = field(default_factory=list)  # D-149: running offers that change no price
    parts: list[str] = field(default_factory=list)  # D-167: the finals a merged utterance joins, oldest first
    recent: list[str] | None = None  # D-303 CONTEXT_WINDOW_MS: the finals of the window, in place of the last two
    session_id: str | None = None
    scenario: str = "default"
    notes: list = field(default_factory=list)  # D-363: the active fact notes, shown to the model by handle
    now: int | None = None  # D-403: when the input was built, for each note's age
    chain: list[str] = field(default_factory=list)  # D-410: a merged line's split lines (its notes' handles listed)


async def gather_fact_passages(
    retriever: Retriever,
    catalog: Catalog,
    prefetched: dict[str, list[Passage]],
    *,
    utterance: str,
    on_air: str,
    switch: SwitchState,
    search_timeout_ms: int,
    all_products: bool = False,
) -> list[Passage]:
    """Full sheets, retaining original citation IDs, without search or network prefetch.

    Keep the existing call signature for runtime/evaluation callers. Explicitly mentioned products
    remain available for comparisons, alongside the on-air product.
    Local uploaded sheets take precedence over the shipped catalog.
    """
    # D-304 JUDGE_PRODUCTS=all: every show product's sheet, no alias match
    others = set(catalog.order) if all_products else catalog.products_mentioned(utterance) - {on_air}
    if switch.previous_product_id:  # D-349: the product that just left the air, inside its window
        others.add(switch.previous_product_id)
    others.discard(on_air)
    out: dict[str, Passage] = {}
    local_sheets = getattr(retriever, "passages_of", None)
    for pid in [on_air, *sorted(others)]:
        sheet = (local_sheets(pid) if callable(local_sheets) else
                 [p for p in catalog.pack.passages if p.product_id == pid])
        for p in sheet:
            out.setdefault(p.passage_id, p)
    return list(out.values())


def fixes_of(value: str | None = None) -> frozenset[str]:
    """D-280: the switched-on fixes ("F1,F3"); None reads FACT_FIXES from the settings."""
    if value is None:
        from ..config import get_settings

        value = get_settings().FACT_FIXES
    return frozenset(x.strip().upper() for x in value.split(",") if x.strip())


_SENTENCE = re.compile(r"(?<=[.!?。！？])\s+")


def sentence_index(passages: Sequence[Passage]) -> tuple[list[dict], dict[str, tuple[Passage, str]]]:
    """D-296: SOURCE numbered sentence by sentence (a line, a table row, or a sentence of a line; "4.5 mL" stays whole),
    as the model sees it, and the id -> (passage, sentence) map code builds quotes from. The same passages give the
    same ids."""
    blocks, index, seen = [], {}, set()
    for p in passages:
        if p.passage_id in seen:
            continue
        seen.add(p.passage_id)
        sentences = []
        for line in p.text.splitlines():
            for s in _SENTENCE.split(line.strip()):
                if s.strip():
                    sid = f"S{len(index) + 1}"
                    index[sid] = (p, s.strip())
                    sentences.append([sid, s.strip()])
        blocks.append({"passage_id": p.passage_id, "product_id": p.product_id, "section": p.section,
                       "sentences": sentences})
    return blocks, index


def from_relation(out: FactRelationOutput, index: dict[str, tuple[Passage, str]], terms: set[str]) -> FactCheckOutput:
    """D-296: a relation verdict as a fact claim. `contradicts` is contradicted and `consistent` supported; the quote is
    the evidence sentences of the first cited passage, joined. A contradiction with no valid evidence id (a sentence,
    "promo" or a running offer's id) cannot alert; `uncertain` never alerts and is counted."""
    claims = []
    for r in out.claims:
        ev = [index[i] for i in r.evidence if i in index]
        verdict = {"contradicts": "contradicted", "consistent": "supported"}.get(r.relation, "not_in_sources")
        if getattr(r, "stance", None) == "REPORTS_OR_ASKS":  # D-331: the model's own stance; never checked or shown
            verdict = "not_in_sources"
            if r.relation == "contradicts" and (sink := DROPS.get()) is not None:
                sink.append({"reason": "reported or asked: not checked", "field": r.field, "stated": r.stated_value,
                             "correct": r.correct_value, "passage_id": None, "quote": None})
        p = ev[0][0] if ev else None
        c = FactClaim(span=r.span, field=r.field, product_id=r.product_id, stated_value=r.stated_value, verdict=verdict,
                      correct_value=r.correct_value, say=getattr(r, "say", None), same_as=getattr(r, "same_as", None),
                      passage_id=p.passage_id if p else None,
                      quote=" ".join(t for q, t in ev if q.passage_id == p.passage_id) if p else None)
        c._evidence = [i for i in r.evidence if i in index or i in terms]  # D-302: carried to the alert
        c._attributed = getattr(r, "attributed", "host")  # D-328
        c._cited = list(dict.fromkeys(q.passage_id for q, _ in ev))  # D-372: prompter items it ticks
        if verdict == "contradicted" and not ev and not set(r.evidence) & terms:
            # D-374: applied as given (no evidence passage, so no quote); logged only
            log.info("fact claim with no valid evidence id (%s): applied as given | field=%s stated=%r correct=%r",
                     ", ".join(r.evidence) or "none", r.field, r.stated_value, r.correct_value)
        elif r.relation == "uncertain":
            log.info("fact relation uncertain | field=%s stated=%r source=%r evidence=%s", r.field, r.stated_value,
                     getattr(r, "source_value", None), r.evidence)
            if (sink := DROPS.get()) is not None:
                sink.append({"reason": "relation uncertain", "field": r.field, "stated": r.stated_value,
                             "correct": r.correct_value, "passage_id": c.passage_id, "quote": c.quote}
                            | ({"source": r.source_value} if hasattr(r, "source_value") else {}))  # D-312
        claims.append(c)
    result = FactCheckOutput(claims=claims, reason="relation")
    result._previous_line = [x.model_dump() for x in getattr(out, "previous_line", [])]  # D-329/330
    return result


def _numbers(lex, t: str | None) -> set[str]:
    return (number_set(t or "") | lex.spoken_numbers(t or "") | {plain_number(v) for v in numbers_in_text(t or "")}
            | lex.times_numbers(t or ""))


def _product_numbers(lex, catalog: Catalog, pid: str, passages: Sequence[Passage]) -> set[str]:
    """D-299: every number the product's documents and record give: all its passages (not only the cited one: "the
    60-tablet tub" when the quote was the 30 pack), its sizes, variants, prices and key facts."""
    nums: set[str] = set()
    for p in (*passages, *catalog.pack.passages):
        if p.product_id == pid:
            nums |= _numbers(lex, p.text)
    if catalog.is_product(pid):
        prod = catalog.get_product(pid)
        for text in (prod.volume, f"{prod.live_price}", f"{prod.list_price}", *map(str, prod.key_facts.values()),
                     *(f"{v.label} {v.live_price} {v.list_price}" for v in prod.variants)):
            nums |= _numbers(lex, text)
    return nums


def as_given(out: FactCheckOutput, catalog: Catalog) -> FactCheckOutput:
    """D-389 (user): the model's claims are applied as given; no code check of values, quotes, evidence or wording.
    The one skip: a claim about a product that is not in the show (a set's price names its set), which cannot be
    applied; it is logged."""
    o = out.model_copy(deep=True)
    set_ids = {s.set_id for s in catalog.set_offers}
    for c in o.claims:
        if not catalog.is_product(c.product_id) and not (c.field in PRICE_FIELDS and c.product_id in set_ids):
            if c.verdict != "not_in_sources":
                log.info("fact claim skipped (cannot apply): product %r is not in the show | field=%s stated=%r",
                         c.product_id, c.field, c.stated_value)
            c.verdict = "not_in_sources"
    return o


class FactChecker:
    name = "fact_checker"

    def __init__(self, llm: LLMClient, prompt: PromptTemplate, catalog: Catalog) -> None:
        self.llm = llm
        self.prompt = prompt
        self.prompt_version = prompt.version
        self.model = llm.facts.model
        self.catalog = catalog
        # D-242 arm FR: how to read a release's record facts; D-247 arm FD: the release's files on top
        from . import arms
        settings = getattr(llm, "settings", None)
        mode = getattr(settings, "FACT_MODE", "sheet")
        self.mode = mode
        # D-296: the relation arm cites file sentences by id (RD), not by "file:<name>" and a copied quote (FD)
        self.relation = bool(getattr(settings, "FACT_RELATION", False))
        # D-302: VOTE_CONFIDENCE=self asks for a confidence per claim (a log field)
        self.confidence = getattr(settings, "VOTE_CONFIDENCE", "off") == "self"
        self.relation_model = FactRelationOutputC if self.confidence else FactRelationOutput
        if getattr(settings, "FACT_PROMPT", "v1") in ("v2", "v3", "v4"):  # D-312, D-313, D-325: source_value before relation (no confidence field)
            self.relation_model = FactRelationOutputV2
            if getattr(settings, "REPORTED_HOLD", False):  # D-328: whose words, and the previous line's fate
                self.relation_model = FactRelationOutputH
        if getattr(settings, "FACT_PROMPT", "v1") in ("v5", "v6", "v8"):  # D-331, D-333, D-347: a stance per claim
            self.relation_model = FactRelationOutputV5
        if getattr(settings, "FACT_PROMPT", "v1") == "v7":  # D-345: v5 plus stated_as_heard
            self.relation_model = FactRelationOutputV7
        layers = {"record": ["FR"], "docs": ["FR", "RD" if self.relation else "FD"]}.get(mode, [])
        addenda = arms._addenda(str(llm.prompts_path)) if layers else {}
        extras = [addenda.get((layer, self.name)) for layer in layers]
        self.fixes = fixes_of(getattr(settings, "FACT_FIXES", ""))  # D-280: the fixes' prompt lines (F1, F5)
        fix_addenda = arms._addenda(str(llm.prompts_path)) if self.fixes else {}
        extras += [fix_addenda.get((f, self.name)) for f in sorted(self.fixes)]
        if self.confidence:  # D-302
            extras.append(arms._addenda(str(llm.prompts_path)).get(("CONF", self.name)))
        if self.relation_model is FactRelationOutputH:  # D-328
            extras.append(arms._addenda(str(llm.prompts_path)).get(("HOLD", self.name)))
        if getattr(settings, "QUESTION_HOLD", False):  # D-335: marked question/answer pairs
            extras.append(arms._addenda(str(llm.prompts_path)).get(("PAIR", self.name)))
        self.conversation = bool(getattr(settings, "CONTEXT_JUDGE", False))  # D-334
        if self.conversation:
            extras.append(arms._addenda(str(llm.prompts_path)).get(("CTX", self.name)))
        if getattr(settings, "STT_AWARE", False):  # D-303
            extras.append(arms._addenda(str(llm.prompts_path)).get(("STT", self.name)))
        if getattr(llm, "prompts_path", None) is not None:  # D-363: fact notes by handle
            extras.append(arms._addenda(str(llm.prompts_path)).get(("NOTES", self.name)))
        self.system_instruction = "\n\n".join([prompt.system_instruction, *(x for x in extras if x)])
        lang = getattr(getattr(catalog, "pack", None), "lang", None)
        if lang:  # D-259: the host reads the correction aloud in the show's language
            self.system_instruction += (f"\n\nThe show's language is {lang}. Write `correct_value` in it (translate a "
                                        "value SOURCE writes in another language); keep `quote` verbatim.")
        # D-279: each product's release files (one release, or each release of a multi-release show)
        self.files: dict[str, tuple[tuple, tuple]] = {}
        releases = dict(getattr(getattr(catalog, "pack", None), "releases", None) or {})
        release_id = getattr(getattr(catalog, "runsheet", None), "runsheet_id", "")
        if not releases and release_id.startswith("rel_"):
            releases = {p.product_id: release_id for p in catalog.products}
        if mode == "docs":
            from ..onboarding.sources import release_sources

            self.files = {pid: release_sources(str(settings.onboarding_path), rid) for pid, rid in releases.items()}
        first = next(iter(self.files.values()), ((), ()))
        self.file_parts, self.file_passages = first  # the first product's (one-release shows, the eval)
        self.all_file_passages = tuple(x for _, ps in self.files.values() for x in ps)
        log.info("fact checker FACT_MODE=%s, release files sent: %d", mode,  # D-366
                 sum(len(parts) for parts, _ in self.files.values()))

    def _parts(self, on_air: str) -> tuple:
        return self.files.get(on_air, (self.file_parts,))[0]

    def _request(self, user: str, prefix: str, deadline_ms: int, session_id: str | None, parts: tuple = (),
                 output_model=None, **mock) -> LLMRequest:
        # D-247: with files, the cache holds the system instruction, the files and the product and full-sheet blocks
        # (the same on every line of a one-product release)
        return LLMRequest(
            agent=self.name, model=self.llm.facts.model, thinking_level=self.llm.facts.thinking_level,
            prompt_version=self.prompt_version, system_instruction=self.system_instruction,
            user_message=user,
            output_model=output_model or (self.relation_model if self.relation else FactCheckOutput),
            deadline_ms=deadline_ms, session_id=session_id,
            cache_prefix=prefix, cache_parts=parts,
            cache_ttl_sec=sum(i.planned_duration_sec for i in self.catalog.runsheet.items), **mock)

    async def warm_cache(self, inp: FactInput) -> None:
        """D-247: the files' context cache is made at session start (with the first line's static blocks), not on
        the first line."""
        if parts := self._parts(inp.on_air):
            _, prefix = self._render(inp)
            await self.llm.warm_cache(self._request(prefix, prefix, 60_000, inp.session_id, parts))

    def _source(self, inp: FactInput) -> list[Passage]:
        """D-296: what the relation arm numbers: the line's passages and the on-air product's file text. D-349: and
        the previous product's file text while it is in scope after a switch."""
        prev = inp.switch.previous_product_id
        return [*inp.passages, *self.files.get(inp.on_air, ((), self.file_passages))[1],
                *(self.files.get(prev, ((), ()))[1] if prev and prev != inp.on_air else ())]

    def _render(self, inp: FactInput) -> tuple[str, str]:
        user, prefix = self._render_template(inp)
        if self.conversation:  # D-334: the last 3 finals in one block, the last one checked
            from ..providers.prompts import render_value

            line = " / ".join(inp.parts) if len(inp.parts) > 1 else inp.utterance
            earlier = (inp.recent if inp.recent is not None else inp.previous)[-2:]
            block = f'<data name="CONVERSATION">{render_value("conversation_json", [*earlier, line])}</data>'
            user = re.sub(r'<data name="RECENT_TRANSCRIPT">.*?</data>\n?', "", user, flags=re.S)
            user = re.sub(r'<data name="UTTERANCE">.*?</data>', lambda _: block, user, flags=re.S)
            user = user.replace("Return the JSON fact check for UTTERANCE.",
                                "Return the JSON fact check for the last line of CONVERSATION.")
        return user, prefix

    def _render_template(self, inp: FactInput) -> tuple[str, str]:
        # D-361 FACT_MODE=prompter: nothing but the prompter snapshot (the passages) carries facts: the product block
        # names the product only, and the promo, offer and set blocks are empty (their prices are in the snapshot);
        # D-409: the v5 template has no such blocks any more (the older versions still take the empty values)
        shown = self.mode == "prompter"
        product = inputs.current_product_compact_json(self.catalog, inp.on_air)
        return self.prompt.render_cached({
            "current_product_compact_json": ({"product_id": product["product_id"], "name": product["name"]}
                                             if shown and product else product),
            "switch_context_json": inputs.switch_context_json(self.catalog, inp.switch, inp.on_air),
            "active_promo_json_or_null": None if shown else inputs.active_promo_json_or_null(self.catalog, inp.promo),
            "active_offers_json": [] if shown else inputs.active_offers_json(self.catalog, inp.offers),
            "set_offers_json": [] if shown else inputs.set_offers_json(self.catalog, inp.promo),
            "passages_json": (sentence_index(self._source(inp))[0] if self.relation
                              else inputs.passages_json(inp.passages)),
            "last_two_final_transcripts_json": inp.recent if inp.recent is not None else inp.previous[-2:],
            # D-167: a merged utterance shows where speech-to-text split it ("A / B")
            "utterance_text": inputs.utterance_text(" / ".join(inp.parts) if len(inp.parts) > 1 else inp.utterance),
        }, {"current_product_compact_json", "passages_json"})

    def _notes(self, inp: FactInput) -> tuple[str, dict[str, str]]:
        """D-363: the active fact notes as a data block of per-call handles (no ids sent), and the handle -> id map."""
        if not inp.notes:
            return "", {}
        handles = {f"F{i}": a.alert_id for i, a in enumerate(inp.notes, 1)}
        # D-364: the host's words and the source sentence say WHAT the note is about (panthenol vs niacinamide)
        # D-403: and how many seconds ago each was raised, so the model can tell a repeat from a new claim
        rows = [{"handle": h, "product_id": a.product_id, "field": a.field, "host_said": a.span,
                 "subject": a.quote, "stated_value": a.stated_value, "correct_value": a.correct_value,
                 "status": a.status, "raised_s_ago": max(0, (inp.now - a.created_at) // 1000) if inp.now else None}
                for h, a in zip(handles, inp.notes)]
        # D-410: the merged line is told which handles are its own chain's notes (same_as may name only those)
        chain = [h for h, a in zip(handles, inp.notes) if a.transcript_id in inp.chain]
        merged = ("\n" + inputs.data_block("MERGED_LINE", {"note": MERGED_NOTE, "chain_handles": chain})
                  if len(inp.parts) > 1 else "")
        return "\n" + inputs.data_block("ACTIVE_FACT_NOTES", rows) + merged, handles  # D-406: same_as when merged

    async def run(self, inp: FactInput, *, deadline_ms: int, **opts) -> AgentResult[FactCheckOutput]:
        user, prefix = self._render(inp)
        block, handles = self._notes(inp)
        base = self.relation_model if self.relation else FactCheckOutput
        res = await self.llm.call(self._request(
            user + block, prefix, deadline_ms, inp.session_id, self._parts(inp.on_air), **opts,
            output_model=(with_note_checks(with_same_as(base, "claims") if self.relation and len(inp.parts) > 1
                                           else base) if handles else base), mock_primary_text=inp.utterance,
            mock_scenario=inp.scenario,
            mock_fallback=lambda _: ({"claims": []} if self.relation
                                     else {"claims": [], "reason": "rule-based: no fact check"}), preview=inp.utterance,
        ))
        checks = list(getattr(res.output, "note_checks", []) or []) if res.output is not None else []
        res = self._validated(inp, res)
        if res.output is not None:  # D-363: the notes the model marked fixed, by handle; nothing else corrects a note
            unknown = [c.handle for c in checks if c.handle not in handles]
            res.output._corrects = list(dict.fromkeys(handles[c.handle] for c in checks
                                                      if c.fixed_by_this_line and c.handle in handles))
            for c in res.output.claims:  # D-403: the note a claim repeats, by handle, as its id
                if c.same_as is not None:
                    if c.same_as not in handles:
                        log.info("fact claim same_as %r is not a listed handle: a new claim (shown: %s)", c.same_as,
                                 sorted(handles))
                    c.same_as = handles.get(c.same_as)
            if handles or checks:
                log.info("fact notes call=%s line=%r notes=%s handles=%s answer=%s corrects=%s%s", res.call_id,
                         inp.utterance[:80], block.strip(), handles, [c.model_dump() for c in checks],
                         res.output._corrects, f" unknown handles dropped: {unknown}" if unknown else "")
        return res

    def _validated(self, inp: FactInput, res: AgentResult[FactCheckOutput]) -> AgentResult[FactCheckOutput]:
        if res.output is None:
            return res
        if self.relation:
            # D-331: claims per call and their stances, to compare prompt versions (over-extraction)
            stances = [getattr(c, "stance", None) for c in res.output.claims]
            log.info("fact claims %d %s: %r", len(stances), self.prompt_version,
                     {s: stances.count(s) for s in set(stances) if s})
            _, index = sentence_index(self._source(inp))
            terms = ({"promo"} if inp.promo is not None else set()) | {o.promo_id for o in inp.offers}
            res.output = from_relation(res.output, index, terms)
        else:
            for c in res.output.claims:  # D-247: "file:<name>#<locator>" names the file
                if c.passage_id and c.passage_id.startswith("file:"):
                    c.passage_id = c.passage_id.split("#", 1)[0]
        res.output = as_given(res.output, self.catalog)  # D-389
        return res
