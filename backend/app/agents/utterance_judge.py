"""UtteranceJudge agent (DEV_SPEC §7.3): compliance, correction, answer linking, prompter and switch
in one call (`JUDGE_MODE=split`). `JUDGE_MODE=single` adds the fact check to the same call
(judge_single.md). The default `split3` cuts the same jobs into two calls (split_judges.py, D-099);
the input values, checks and rule-based fallbacks here are shared with it."""
from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from ..logic.catalog import Catalog
from ..logic import qualifier
from ..logic.grouping import normalise_question
from ..logic.reflex import Reflex
from ..models.agent_io import JudgeSingleOutput, UtteranceJudgeOutput, Violation
from ..models.data import Passage, Promo, PrompterPoint
from ..models.session import Alert, HostCue, QuestionGroup, SwitchState
from ..providers.llm import AgentResult, LLMClient, LLMRequest
from ..providers.prompts import PromptTemplate
from . import arms, fact_checker, inputs

log = logging.getLogger(__name__)

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


def _cdrop(v, why: str) -> None:
    """D-260: a judge's violation code drops is logged with its reason, and collected for the eval like fact drops."""
    from .fact_checker import DROPS

    log.info("compliance violation dropped by code: %s | rule=%s span=%r", why, v.rule_id, v.span)
    if (sink := DROPS.get()) is not None:
        sink.append({"reason": f"compliance: {why}", "field": v.rule_id, "stated": v.span, "correct": None,
                     "passage_id": None, "quote": None})


_GENERIC_QUALIFIER = frozenset({"test", "tested", "testing", "our", "own", "house", "in-house", "independent", "lab",
                                "laboratory", "study", "studies", "clinical", "certified", "certification", "results",
                                "result", "consumer", "panel", "participants", "approved", "labs", "laboratories",
                                "tests", "trial", "trials"})


def names_the_source(text: str, say: str, lex) -> bool:
    """D-244 L7: the qualifier of a result names its source ("tested by Kestrel Labs", "certified by the Vegan
    Society"); a line that names that source carries the qualifier, whatever words it uses around it."""
    m = re.search(r"\(([^()]*)\)\s*$", say)
    if m is None or lex.in_house.search(m.group(1)) or lex.is_qualified(m.group(1)):
        # D-250 (sealed run: "... in 22 adults" counted as naming the source of "in our in-house test with 22
        # adults"): our own test has no outside name to say; its qualifier is the words themselves
        return False
    source = {w for w in lex.content_words(m.group(1)) if w not in _GENERIC_QUALIFIER and not w.isdigit()}
    tokens = re.findall(r"\w[\w'-]*", m.group(1))
    if any(ch.lower() != ch.upper() for ch in m.group(1)):
        # D-250: in a script with capitals, the source is a name ("Kestrel Dermal Labs"), not "adults" or "hours"
        names = set(lex.content_words(" ".join(t for t in tokens[1:] if t[0].isupper())))
        source &= names
    # D-258 (candidate e41fcf4: "Testing confirmed SPF50+ PA++++" skipped the alert because the qualifier's capitalised
    # "PA" is also in the result): a word of the result itself never names its source; nor does the qualifier's
    # first word, capitalised only because it starts the phrase
    source -= set(lex.content_words(say[:m.start()]))
    return bool(source) and bool(source & set(lex.content_words(text)))


_ORG = re.compile(r"\b((?:[A-Z][\w&'-]*\s+){1,4})(?:Labs?|Laboratories|Laboratory|Institute|Clinic|University|"
                  r"Society|Centre|Center|Panel)\b")
# D-294 G5: more tester names: "... Testing", "... Research", "Institute of ...", and the capitalised name after
# "by" or "at" in the result ("tested by Quorvane Coating")
_ORG_MORE = re.compile(r"\b((?:[A-Z][\w&'-]*\s+){1,4})(?:Testing|Research)\b|\b(?:Institute|Centre|Center|University|"
                       r"Laborator(?:y|ies)|Society)\s+(?:of|for)\s+((?:[A-Z][\w&'-]*\s*){1,4})|"
                       r"\b(?:by|at)\s+(?:the\s+)?((?:[A-Z][\w&'-]*\s*){1,5})")
_PANEL = re.compile(r"\b(\d+)\s+(?:adults|participants|people|persons|women|men|users|volunteers|children|"
                    r"subjects|testers)\b", re.I)


def names_the_tester(text: str, say: str, lex, g5: bool = False) -> bool:
    """D-284 Q1E: besides D-244 L7's source in the qualifier, a line names who tested an outside test when it says
    the organisation the result names anywhere ("Brightwell Labs: no transfer ...", with Labs, Institute, Clinic,
    ...) or the panel ("20 adults") of a qualifier that is not ours. Our own test still needs our own words (D-250).
    D-294 G5: also a result with no qualifier in brackets, more name forms (`_ORG_MORE`), and the name's own first
    word ("Quorvane" of "Quorvane Coating Test Laboratory") when the result's statement does not use that word."""
    m = re.search(r"\(([^()]*)\)\s*$", say)
    qual = m.group(1) if m else (say if g5 else None)
    if qual is None or lex.in_house.search(qual) or lex.is_qualified(qual):
        return False
    low = text.lower()
    orgs = {" ".join(g.group(1).split()).lower() for g in _ORG.finditer(say)}
    if any(o and o in low for o in orgs):
        return True
    if g5:
        names = {" ".join(n.split()) for g in _ORG_MORE.finditer(say) for n in g.groups() if n}
        names |= {" ".join(g.group(1).split()) for g in _ORG.finditer(say)}
        rest = say
        for n in names:
            rest = rest.replace(n, " ")
        used = set(re.findall(r"[a-z]+", rest.lower()))
        firsts = {n.split()[0].lower() for n in names if n.split()}
        if any(re.search(rf"(?<!\w){re.escape(f)}", low) for f in firsts
               if len(f) >= 4 and f not in _GENERIC_QUALIFIER and f not in used):
            return True
    if m is None:
        return False
    panels = {p.group(1) for p in _PANEL.finditer(m.group(1))}
    return any(p.group(1) in panels for p in _PANEL.finditer(text))


NO_HIGH_KINDS = frozenset({"usage_instruction", "composition_fact"})  # D-297 CK


def _named_result(v, catalog: Catalog):
    """D-299: the recorded result a TEST-QUALIFIER verdict names by id (relation arm), or None."""
    rid = getattr(v, "qualified_result_id", None)
    return next((x for p in catalog.products for x in p.qualified_results if x.result_id == rid), None) if rid else None


def _caution_state(group: str, product, terms) -> bool:
    """D-299 CK: "Irritated skin? Go ahead and use it.": the group is a state a product caution names (irritation),
    not a group of the rule's own; the line reverses a caution, which is the fact checker's."""
    if product is None or not product.cautions or _holds_term(group, terms):
        return False
    stems = {w[:5] for w in re.findall(r"\w+", group.casefold()) if len(w) >= 5}
    return bool(stems & {w[:5] for c in product.cautions for w in re.findall(r"\w+", c.casefold())})


def _group_said(group: str, line: str, terms) -> bool:
    """D-298 CK: the judge's group is in the line or the previous final (a word of it, by its first five letters), or
    the line names a group of the rule's own ("kids", "everyone"); "absolutely no harmful effects" names none."""
    g, low = group.casefold().strip(), line.casefold()
    if g and g in low:  # any script: the judge copies the line's own words
        return True
    heard = {w[:5] for w in re.findall(r"\w+", low)}
    words = [w for w in re.findall(r"\w+", g) if len(w) > 2 and w not in ("the", "and", "with", "for")]
    return any(w[:5] in heard for w in words) or _holds_term(line, terms)


def _holds_term(text: str, terms) -> bool:
    """D-290 Q6: one of the terms starts a word of the text ("pregnan" holds "pregnant")."""
    low = text.lower()
    return any(re.search(r"(?<![a-z])" + re.escape(t.lower()), low) for t in terms)


# D-286 Q1T: test words that name no tester; and the hedges of a line that states its limits
_GENERIC_TEST = re.compile(r"\b(?:lab[- ]tested|laboratory[- ]tested|clinically (?:tested|proven)|dermatologically "
                           r"tested|scientifically proven|tests? (?:confirm|confirmed|show|showed|prove|proved)|"
                           r"testing (?:confirmed|showed)|proven)\b", re.I)
_HEDGE = re.compile(r"\b(?:may|might|can vary|results vary|individual results|up to|in some|not everyone)\b", re.I)
# D-291 Q3: a line that disclaims the claim itself ("these documents give no lab result that supports a no-side-effects
# claim", "we cannot claim that", "there is no evidence it cures colds")
_DISCLAIMED = re.compile(r"\b(?:no|not any|without)\s+(?:\w+\s+){0,2}(?:results?|evidence|data|studies|study|proof)\s+"
                         r"(?:that\s+|which\s+|to\s+)?(?:supports?|shows?|backs?|proves?)\b|\b(?:cannot|can't|can not|"
                         r"don't|do not|won't|will not)\s+(?:claim|say|promise)\b", re.I)
# D-286 Q3: a denied guarantee ("we can't guarantee", "it guarantees no individual result"), never "not only"
_GUARANTEE = re.compile(r"\b(?:guarantee[sd]?|promise[sd]?)\b", re.I)
_DENIED = re.compile(r"\b(?:no|not(?! only)|never|cannot|can't|don't|doesn't|won't)\s+(?:\w+\s+){0,2}"
                     r"(?:guarantee|promise)|\b(?:guarantee[sd]?|promise[sd]?)\s+no\s+(?:\w+\s+){0,2}"
                     r"(?:results?|outcomes?)\b", re.I)


def negated_caution(text: str, product, lex) -> str | None:
    """D-259 (sealed: "no need to stop using it when irritation occurs" got an unrelated approved claim to say): the
    product caution a line negates (most of the caution's words heard, and a negation in the line)."""
    if product is None or not product.cautions or not any(
            re.search(rf"(?<!\w){re.escape(n)}(?!\w)", text.lower()) for n in lex.negation_words):
        return None
    heard = lex.content_words(text)
    best = max(product.cautions, key=lambda c: lex.coverage(lex.claim_words(c), heard))
    return best if lex.coverage(lex.claim_words(best), heard) >= 0.5 else None


def approved_say(say: str, on_air, catalog: Catalog) -> str:
    """D-209 (full review P2): the say-instead line is approved wording, never the model's own sentence: the on-air
    product's approved claim or "say instead" wording that covers most of what the model suggested (the first
    approved claim when nothing overlaps), with its qualifier."""
    if on_air is None:
        return qualified_say(say, on_air, catalog)
    lex = catalog.lexicon
    cands = [spoken_claim(c) for c in catalog.approved_claims(on_air.product_id)] + [a.say for a in on_air.avoid_saying]
    if not cands:  # D-232: no approved wording in the show's language; never the model's own sentence
        return f"(no approved wording in {catalog.pack.lang})"
    said = lex.content_words(say or "")
    best = max(cands, key=lambda c: lex.coverage(lex.claim_words(c), said))
    words = lex.claim_words(best)
    # the model's sentence is kept only as a light rewording: no word the approved line lacks, most of its words
    light = bool(said) and all(any(lex.same(w, b) for b in words) for w in said) and lex.coverage(words, said) >= 0.8
    return qualified_say(say if light else best, on_air, catalog)


def say_instead_fallback(catalog: Catalog, product_id: str) -> str:
    """§8.4.3: the on-air product's first approved claim, with the in-house-test qualifier. D-273 (sealed pool 4: a
    release with no approved claim raised IndexError here, so a failed judge call lost the line's alert): the D-232
    line when there is none."""
    claims = catalog.approved_claims(product_id)
    return spoken_claim(claims[0]) if claims else f"(no approved wording in {catalog.pack.lang})"


LEAD_IN_MAX_WORDS = 8  # D-146: "In our in-house test," said as its own final


def validate_compliance(o, catalog: Catalog, values: dict, arm: str = "A", verify: bool | None = None):
    """In place, on any output with `compliance` and `correction`: drop unknown rules and alert ids
    that were not in the input; severity comes from the rule. D-187 arm B: the qualifier replacement is the
    in-house result the judge picked by id, and correction quotes of unknown alerts are dropped."""
    rules = catalog.pack.rules_by_id
    if "rules_compact_json" in values:  # D-279: a rule the line was not given (another category's) is no verdict
        offered = {r["rule_id"] for r in values["rules_compact_json"]}
        rules = {k: v for k, v in rules.items() if k in offered}
    text = values.get("utterance_text") or ""
    # D-105: a sentence that names our own test never breaks the test-qualifier rule
    # D-146 (sealed show replay): speech-to-text split "In our in-house test," from "skin hydration went up 38% ...";
    # a short lead-in final just before, naming our test and no number, qualifies this one
    prev = (values.get("last_two_final_transcripts_json") or [])[-1:]
    lead_in = (bool(prev) and catalog.lexicon.is_qualified(prev[0]) and not any(ch.isdigit() for ch in prev[0])
               and len(prev[0].split()) <= LEAD_IN_MAX_WORDS)
    qualified = catalog.lexicon.is_qualified(text) or lead_in
    # D-300 R2: with the verifier, the flagger keeps every verdict on a rule it was given (schema only); the
    # verifier decides what the code drops below decided
    from ..config import get_settings

    drops = not (get_settings().JUDGE_ARM in ("verify", "vote") if verify is None else verify)
    for v in o.compliance.violations:
        if v.rule_id not in rules:
            _cdrop(v, "unknown rule")
        elif v.rule_id == qualifier.RULE_ID and qualified and drops:
            _cdrop(v, "the line names our own test")
    o.compliance.violations = [v for v in o.compliance.violations if v.rule_id in rules
                               and not (v.rule_id == qualifier.RULE_ID and qualified and drops)]
    # D-148 (sealed show replay): STT made "Acne, um, no no," its own final and the judge flagged the word
    # "acne" (HIGH) before the host went on "we cannot say it treats acne". A final that is nothing but the
    # flagged word and fillers is a topic, not a claim.
    lex = catalog.lexicon
    said = [w for w in lex.content_words(text) if w not in lex.fillers]
    o.compliance.violations = [v for v in o.compliance.violations
                               if not (drops and len(said) == 1 and lex.content_words(v.span) == said)]
    for v in o.compliance.violations:
        if v.is_quoted and not v.is_negated and lex.affirms(text):
            # D-252 (sealed: "A viewer says 'it cures eczema', and yes, that is what it does" got no alert): a quote
            # the host endorses in the same line is the host's own claim
            v.is_quoted = False
    kept = []
    g5 = "G5" in fact_checker.fixes_of()
    tester_text = f"{prev[0]} {text}" if g5 and prev else text  # D-294 G5: the tester named in the previous final
    on_air_id = (values.get("current_product_json") or {}).get("product_id")
    on_air_product = catalog.get_product(on_air_id) if catalog.is_product(on_air_id) else None
    for v in o.compliance.violations:
        v.severity = rules[v.rule_id].severity
        # D-215 (full review P3): no code veto by word overlap with approved wording; the judge weighs it (prompt)
        if v.rule_id == qualifier.RULE_ID and arms.meaning_to_llm(arm):
            # D-187 arm B: the judge names the in-house result; code only checks the id exists
            rid = getattr(v, "qualified_result_id", None)
            r = next((x for p in catalog.products for x in p.qualified_results if x.result_id == rid), None)
            if r is None:
                continue
            v.say_instead = r.say
        elif v.rule_id == qualifier.RULE_ID:  # approved wording only, never the model's (D-105)
            on_air = catalog.get_product(values["current_product_json"]["product_id"])
            # D-299: the result the judge names by id ("complete coverage of every grey hair" states "100% of
            # assessed strands"); otherwise D-116's match by numbers and words
            r = _named_result(v, catalog) or qualifier.approved_replacement(
                text, on_air, [p for p in catalog.products if p is not on_air], catalog.lexicon,
                "G4" in fact_checker.fixes_of())
            if r is None and not drops:
                v.say_instead = approved_say(v.say_instead, on_air_product, catalog)
                kept.append(v)
                continue
            if r is None:
                _cdrop(v, "D-116: the line matches no test result")
                continue  # D-116: the sentence matches no in-house test result (an amount, price or volume)
            if not drops:
                v.say_instead = r.say
                kept.append(v)
                continue
            if names_the_source(text, r.say, catalog.lexicon):
                _cdrop(v, "D-244 L7: the line names the test's source")
                continue  # D-244 L7: the host named who ran the test or certified it: that is the qualifier
            if "Q1E" in fact_checker.fixes_of() and names_the_tester(tester_text, r.say, catalog.lexicon, g5):
                _cdrop(v, "D-284 Q1E: the line names the tester or its panel")
                continue
            v.say_instead = r.say
        else:
            # D-259: a line that negates one of the product's cautions is corrected by that caution, not by an
            # unrelated approved claim
            v.say_instead = (negated_caution(text, on_air_product, lex)
                             or approved_say(v.say_instead, on_air_product, catalog))
        kept.append(v)
    o.compliance.violations = kept
    fixes = fact_checker.fixes_of()
    if drops and fixes & {"Q6", "G4", "G7", "CK"}:
        fit = []
        for v in kept:
            r = rules[v.rule_id]
            kind = getattr(v, "claim_kind", None)
            if "CK" in fixes and kind and v.severity == "HIGH" and not v.is_negated:
                # D-297 CK: the judge's claim kind must be the rule's own element; a usage direction or a composition
                # fact is never a HIGH (a wrong one is the fact checker's). The word lists below are the fallback
                why = ("carries no HIGH" if kind in NO_HIGH_KINDS
                       else f"is not this rule's claim ({', '.join(r.claim_kinds)})" if r.claim_kinds and kind not in r.claim_kinds
                       else "names no group" if r.needs_group and not getattr(v, "group", None)
                       else "group not in line" if r.needs_group and not _group_said(
                           v.group, f"{prev[0] if prev else ''} {text}", r.required_terms)
                       else "group is a caution's state" if r.needs_group and _caution_state(
                           v.group, on_air_product, r.required_terms) else None)
                if why:
                    _cdrop(v, f"CK: {kind} {why} ({r.rule_id})")
                else:
                    fit.append(v)
                continue
            # D-294 G4: a test-result or evidence rule reads the previous final too (a result split over two finals)
            hay = f"{prev[0] if prev and r.terms_fix == 'G4' else ''} {text} {v.span or ''}"
            # D-295 G4: a test-result or evidence verdict stands on an evidence word or on a qualified result the
            # line is about by its words ("tear-free"); only a line with neither ("zinc at 2 percent") drops
            if (r.required_terms and r.terms_fix in fixes and not v.is_negated and not _holds_term(hay, r.required_terms)
                    and not (r.terms_fix == "G4" and (qualifier.matches_result(hay, catalog.products, lex)
                                                      or _named_result(v, catalog) is not None))):
                # D-290 Q6: the rule's own element is not in the line ("zero side effects" names no group, "the
                # best" says nothing permanent): the judge stretched a HIGH rule over another claim. D-294 G4: a bare
                # ingredient amount ("glycerin at two percent") states no test result and no evidence
                _cdrop(v, f"{r.terms_fix}: rule needs one of its terms ({r.rule_id}: {', '.join(r.required_terms[:4])}, ...)")
            elif ("G7" in fixes and r.direction_terms and not v.is_negated and _holds_term(hay, r.direction_terms)
                  and not _holds_term(hay, r.promise_terms)):
                # D-294 G7: "let the child brush alone" directs the group and promises it nothing; a wrong direction
                # is the fact checker's
                _cdrop(v, f"G7: a usage direction to the group with no promise ({r.rule_id})")
            else:
                fit.append(v)
        kept[:] = fit
    if drops and "Q3" in fixes:
        for v in kept:  # D-291: whatever the rule's source (market, law pack, brand pack)
            if not v.is_negated and (_DENIED.search(v.span or "") or _DISCLAIMED.search(text)
                                     or (_DENIED.search(text) and _GUARANTEE.search(v.span or ""))):
                log.info("compliance violation negated by code: D-286 Q3 a denied guarantee | rule=%s span=%r",
                         v.rule_id, v.span)
                v.is_negated = True  # D-286 Q3: "it guarantees no individual result" denies a guarantee
    if ("Q1T" in fixes and qualifier.RULE_ID in rules and on_air_product is not None
            and not any(v.rule_id == qualifier.RULE_ID for v in kept)):
        generic = _GENERIC_TEST.search(text)
        r = qualifier.approved_replacement(text, on_air_product, [p for p in catalog.products if p is not on_air_product],
                                           lex) if generic and not qualified and not _HEDGE.search(text) else None
        heard = {w for w in lex.content_words(text) if w.isdigit()} | lex.spoken_numbers(text)
        if (r is not None and heard & qualifier.result_numbers(r, lex)
                and not names_the_source(text, r.say, lex) and not names_the_tester(tester_text, r.say, lex, g5)):
            # D-286 Q1T: a result said with only a generic "lab-tested" and no tester gets its qualifier alert
            log.info("compliance violation added by code: D-286 Q1T a generic test word | span=%r", generic.group())
            kept.append(Violation(span=generic.group(), rule_id=qualifier.RULE_ID,
                                  severity=rules[qualifier.RULE_ID].severity, is_negated=False, is_quoted=False,
                                  say_instead=r.say))
    alert_ids = {a["alert_id"] for a in values["active_alerts_json"]}
    o.correction.corrects_alert_ids = [a for a in dict.fromkeys(o.correction.corrects_alert_ids) if a in alert_ids]
    if hasattr(o.correction, "quotes"):  # D-187 arm B
        o.correction.quotes = [q for q in o.correction.quotes if q.alert_id in alert_ids]
    return o


def validate_context(o, catalog: Catalog, values: dict):
    """In place, on any output with `answer` and `prompter`: drop group, point and cue ids that were
    not in the input, and an unknown switch target."""
    group_ids = {q["group_id"] for q in values["open_questions_json"]}
    if o.answer.matched_group_id is not None and o.answer.matched_group_id not in group_ids:
        o.answer.matched_group_id = None
        o.answer.is_answer = o.answer.consistent_with_suggested = False
    o.answer.also_answered_group_ids = (
        [g for g in dict.fromkeys(o.answer.also_answered_group_ids) if g in group_ids and g != o.answer.matched_group_id]
        if o.answer.matched_group_id is not None and o.answer.is_answer else [])
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


def judge_products(catalog: Catalog, inp: JudgeInput) -> set[str] | None:
    """D-279: in a multi-release show, the products this line can be about (None: one-product rules as before)."""
    if catalog.pack.rule_products is None:
        return None
    target = inp.switch.target_product_id if inp.switch.status in ("counting", "pending") else None
    return catalog.line_products(inp.on_air, target, [*inp.previous[-2:], inp.utterance])


def build_judge_values(catalog: Catalog, inp: JudgeInput, single: bool = False) -> dict:
    """Prompt values shared by the UtteranceJudge, judge_single and the split judges (D-099)."""
    values = {
        "current_product_json": inputs.current_product_json(catalog, inp.on_air),
        "run_sheet_compact_json": inputs.run_sheet_compact_json(catalog, inp.on_air),
        "approved_claims_of_current_product_json": inputs.approved_claims_of_current_product_json(catalog, inp.on_air),
        "rules_compact_json": inputs.rules_compact_json(catalog, judge_products(catalog, inp)),
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
        if ans.get("also_answered_group_ids"):
            ans["also_answered_group_ids"] = [GROUP_REF + group_q[g] if g in group_q else g
                                              for g in ans["also_answered_group_ids"]]
        corr = data.get("correction") or {}
        corr["corrects_alert_ids"] = [ALERT_REF + alert_span[a] if a in alert_span else a
                                      for a in corr.get("corrects_alert_ids", [])]
        return data

    def decode(data: dict) -> dict:
        ans = data.get("answer") or {}
        ref = ans.get("matched_group_id")
        if isinstance(ref, str) and ref.startswith(GROUP_REF):
            ans["matched_group_id"] = q_group.get(ref[len(GROUP_REF):])
        if ans.get("also_answered_group_ids"):
            ans["also_answered_group_ids"] = [
                g for g in (q_group.get(r[len(GROUP_REF):]) if isinstance(r, str) and r.startswith(GROUP_REF) else r
                            for r in ans["also_answered_group_ids"]) if g]
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
