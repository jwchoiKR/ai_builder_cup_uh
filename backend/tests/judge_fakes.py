"""Scripted LLM backend and output builders for utterance-path tests (no Vertex, no fixtures)."""
from __future__ import annotations

import asyncio
import json

from app.agents.originals import citation_rule_id
from app.models.agent_io import ComplianceOutput, ContextOutput, FactCheckOutput, JudgeSingleOutput, UtteranceJudgeOutput
from app.models.session import Event
from app.providers.llm import LLMError, RawReply

from .helpers import live_runtime, make_ctx

CREAM, AMPOULE = "cream_hydra_barrier", "ampoule_deep_hydration"
# JUDGE_MODE=split3 (D-099): a script, delay or failure keyed "utterance_judge" covers both split judges.
JUDGE = "utterance_judge"
SPLIT_PARTS = {"compliance_judge": (ComplianceOutput, ("compliance", "correction")),
               "context_judge": (ContextOutput, ("answer", "prompter"))}
PRICE_PASSAGE = "DL-CR-01#key-facts#live-broadcast-price"
PRICE_QUOTE = "Live broadcast price: S$36.00"

# D-434 (temporary, removed with the rules-JSON path): the demo market's original and the section an old rule id's
# verdict cites on the production (originals) path. An id that is not here is refused, never guessed.
ASEAN_DOC = "asean_cosmetic_claims_guideline_appendix_iii_2007.pdf"
OLD_RULE_SECTIONS = {
    "ASEAN-2D-DISEASE": "2.d", "ASEAN-2D-VULNERABLE": "2.d.vi", "ASEAN-2E-PERMANENT": "2.e",
    "ASEAN-3-SKIN-AGEING": "3 (anti-ageing)", "ASEAN-3-SKIN-ACNE": "3 (acne)",
    "ASEAN-3-SKIN-ANTIMICROBIAL": "3 (antimicrobial)", "ASEAN-3-SKIN-SCARS": "3 (scars)",
    "ASEAN-3-SKIN-NUMBING": "3 (numbing)", "ASEAN-3-SKIN-BODY": "3 (body)",
}


ADAPTER_ERRORS: list[str] = []  # D-434: checked after every test (tests/conftest.py)


def _refuse(why: str):
    ADAPTER_ERRORS.append(why)
    raise AssertionError(why)


def rid(old_rule_id: str) -> str:
    """D-434: the alert rule id the production path gives an old rule id's verdict (citation_rule_id)."""
    return citation_rule_id(ASEAN_DOC, OLD_RULE_SECTIONS[old_rule_id])


def cited(old_rule_id: str) -> str:
    """D-434: the citation the production verdict for an old rule id carries ("<document>#<section>")."""
    return f"{ASEAN_DOC}#{OLD_RULE_SECTIONS[old_rule_id]}"


def _cites(model) -> bool:
    """The production compliance output (D-358: cited verdicts, ComplianceOutputO and its with_* variants)."""
    return "citation" in json.dumps(model.model_json_schema())


def to_cited(part: dict, model) -> dict:
    """D-434: a scripted compliance part in the rules shape, as the production judge answers it: each violation cites
    the original section its old rule id maps to; validated by the request's own output model. A part already in the
    production shape (every violation cited) is returned as scripted."""
    if all("citation" in v for v in part["compliance"]["violations"]) and "rule_id" not in json.dumps(part):
        return part
    violations = []
    for v in part["compliance"]["violations"]:
        if "citation" not in v:
            if v["rule_id"] not in OLD_RULE_SECTIONS:
                _refuse(f"D-434: no production citation for the old rule id {v['rule_id']!r}")
            v = {"citation": cited(v["rule_id"]), "quote": "scripted section text", "span": v["span"],
                 "is_negated": v["is_negated"], "is_quoted": v["is_quoted"], "say_instead": v["say_instead"],
                 **{k: v[k] for k in ("product_id", "same_as") if k in v}}
        violations.append(v)
    schema = json.dumps(model.model_json_schema())
    if '"same_as"' in schema:
        violations = [{"same_as": None, **v} for v in violations]
    out = {"compliance": {"violations": violations}, "correction": part["correction"], "reason": part["reason"]}
    if '"alert_checks"' in schema:
        out = {"alert_checks": part.get("alert_checks", []), **out}
    return model.model_validate(out).model_dump(mode="json")


def violation(rule_id: str, span: str = "the claim", *, negated: bool = False, quoted: bool = False,
              severity: str = "HIGH", say: str = "Say this instead.") -> dict:
    return {"span": span, "rule_id": rule_id, "severity": severity, "is_negated": negated, "is_quoted": quoted,
            "say_instead": say}


def judge_output(*, violations=(), corrects=(), utterance_type="product_talk", matched=None, is_answer=False,
                 consistent=False, covered=(), cues=(), transition=False, quote=False, target=None,
                 confidence="low", reason="scripted") -> dict:
    return UtteranceJudgeOutput.model_validate({
        "compliance": {"violations": list(violations)},
        "correction": {"corrects_alert_ids": list(corrects)},
        "answer": {"utterance_type": utterance_type, "matched_group_id": matched, "is_answer": is_answer,
                   "consistent_with_suggested": consistent},
        "prompter": {"covered_point_ids": list(covered), "covered_cue_ids": list(cues),
                     "switch": {"is_transition": transition, "is_quote": quote, "target_product_id": target,
                                "confidence": confidence}},
        "reason": reason,
    }).model_dump(mode="json")


def claim(field: str, verdict: str, *, product_id: str = CREAM, stated: str = "x", correct: str | None = None,
          passage_id: str | None = None, quote: str | None = None, span: str = "span") -> dict:
    return {"span": span, "field": field, "product_id": product_id, "stated_value": stated, "verdict": verdict,
            "correct_value": correct, "passage_id": passage_id, "quote": quote}


def price_contradiction(stated: str = "S$32") -> dict:
    return claim("price", "contradicted", stated=stated, correct="S$36.00", passage_id=PRICE_PASSAGE, quote=PRICE_QUOTE)


def _source_sentences(user_message: str) -> list[tuple[str, str]]:
    """The SOURCE sentence ids and texts the fact checker's request numbers (D-296)."""
    import re

    return [(i, json.loads(f'"{t}"')) for i, t in re.findall(r'\["(S\d+)",\s*"((?:[^"\\]|\\.)*)"\]', user_message)]


def _evidence(sentences: list[tuple[str, str]], *values: str | None) -> list[str]:
    """The first SOURCE sentence that holds one of these values (the right value, then the quote): its id."""
    for v in values:
        if v:
            key = v.casefold().strip(" .")
            found = [i for i, t in sentences if key and key in t.casefold()]
            if found:
                return found[:1]
    return []


def to_v5(out: dict, model, user_message: str) -> dict:
    """D-434: a scripted fact check in the old claim shape, as the production fact checker answers it (v5: a stance
    per claim, evidence by SOURCE sentence id, the relation); validated by the request's own output model."""
    if all("stance" in c for c in out.get("claims", [])):
        return out
    sentences = _source_sentences(user_message)
    relation = {"contradicted": "contradicts", "supported": "consistent", "not_in_sources": "not_in_documents"}
    claims = []
    for c in out["claims"]:
        rel = relation[c["verdict"]]
        ev = (_evidence(sentences, c.get("correct_value"), c.get("quote")) if rel == "contradicts"
              else _evidence(sentences, c.get("quote"), c.get("stated_value")) if rel == "consistent" else [])
        claims.append({"span": c["span"], "stance": c.get("stance", "HOST_ASSERTS"), "product_id": c["product_id"],
                       "field": c["field"], "stated_value": c["stated_value"], "evidence": ev,
                       "source_value": c.get("correct_value"), "relation": rel, "correct_value": c.get("correct_value"),
                       "say": c.get("say"), **({"same_as": c["same_as"]} if "same_as" in c else {})})
    schema = json.dumps(model.model_json_schema())
    if '"same_as"' in schema:
        claims = [{"same_as": None, **c} for c in claims]
    data = {"claims": claims}
    if '"note_checks"' in schema:
        data = {"note_checks": out.get("note_checks", []), **data}
    return model.model_validate(data).model_dump(mode="json")


def split_part(agent: str, data: dict) -> dict:
    """The compliance_judge or context_judge part of a full judge output."""
    model, keys = SPLIT_PARTS[agent]
    return model.model_validate({k: data[k] for k in keys} | {"reason": data["reason"]}).model_dump(mode="json")


class ScriptedBackend:
    """Returns scripted outputs keyed by (agent, primary text); otherwise the agent's rule-based
    fallback (triage, composer), so comments still flow. `judge(...)` scripts the UtteranceJudge;
    in split3 the compliance and context judges each return their part of it."""

    name = "scripted"

    def __init__(self) -> None:
        self.outputs: dict[tuple[str, str], dict] = {}
        self.delays: dict[tuple[str, str], float] = {}
        self.errors: set[tuple[str, str]] = set()
        self.calls: list[tuple[str, str]] = []
        self.expects: dict[str, bool] = {}  # D-335: the context judge's expects_resolution per line
        self.named: dict[str, bool] = {}  # D-351: moving_to_next_named per line (default: the transition flag)

    def judge(self, text: str, named: bool | None = None, **kw) -> None:
        self.outputs[("utterance_judge", text)] = judge_output(**kw)
        if named is not None:
            self.named[text] = named

    def single(self, text: str, *, claims=(), **kw) -> None:
        data = judge_output(**kw) | {"facts": {"claims": list(claims), "reason": "scripted"}}
        self.outputs[("judge_single", text)] = JudgeSingleOutput.model_validate(data).model_dump(mode="json")

    def facts(self, text: str, *claims: dict, delay: float = 0.0, fixed=()) -> None:
        """`fixed`: D-363, the handles (F1, F2 ...) of the active fact notes this line fixes."""
        self.outputs[("fact_checker", text)] = FactCheckOutput.model_validate(
            {"claims": list(claims), "reason": "scripted"}).model_dump(mode="json") | {
            "note_checks": [{"handle": h, "fixed_by_this_line": True} for h in fixed]}
        if delay:
            self.delays[("fact_checker", text)] = delay

    def fail(self, agent: str, text: str) -> None:
        self.errors.add((agent, text))

    def _alias(self, agent: str, text: str, table) -> tuple[str, str]:
        key = (agent, text)
        if agent in SPLIT_PARTS and key not in table:
            return (JUDGE, text)
        return key

    async def generate(self, req, timeout_ms):
        key = (req.agent, req.mock_primary_text)
        self.calls.append(key)
        delay_key = self._alias(*key, self.delays)
        if delay_key in self.delays:
            await asyncio.sleep(self.delays[delay_key])
        if self._alias(*key, self.errors) in self.errors:
            raise LLMError("scripted failure")
        if key in self.outputs:
            out = self.outputs[key]
            if req.agent == "compliance_judge" and _cites(req.output_model):
                out = to_cited(out, req.output_model)
            if req.agent == "fact_checker" and '"stance"' in json.dumps(req.output_model.model_json_schema()):
                out = to_v5(out, req.output_model, req.user_message)
            if req.agent in ("utterance_judge", "judge_single") and "prompter" in out:  # D-419: as the split path
                sw_model = req.output_model.model_fields["prompter"].annotation.model_fields["switch"].annotation
                if "moving_to_next_named" in sw_model.model_fields:
                    out = json.loads(json.dumps(out))
                    sw = out["prompter"]["switch"]
                    sw.setdefault("moving_to_next_named", self.named.get(req.mock_primary_text, sw["is_transition"]))
            return RawReply(json.dumps(out), model_version="scripted")
        if req.agent in SPLIT_PARTS:
            data = self.outputs.get((JUDGE, req.mock_primary_text)) or judge_output()
            part = split_part(req.agent, data)
            if req.agent == "compliance_judge" and _cites(req.output_model):
                part = to_cited(part, req.output_model)
            if "expects_resolution" in getattr(req.output_model, "model_fields", {}):  # D-335 QUESTION_HOLD
                part = {"expects_resolution": self.expects.get(req.mock_primary_text, False), **part}
            if "prompter" in part:  # D-351 SWITCH_MODE=immediate: the switch verdict says whether the line names it
                sw_model = req.output_model.model_fields["prompter"].annotation.model_fields["switch"].annotation
                if "moving_to_next_named" in sw_model.model_fields:
                    sw = part["prompter"]["switch"]
                    sw["moving_to_next_named"] = self.named.get(req.mock_primary_text, sw["is_transition"])
            return RawReply(json.dumps(part), model_version="scripted")
        if req.agent in ("utterance_judge", "judge_single"):
            # Unscripted sentences: a neutral verdict (no reflex-derived violations).
            data = judge_output()
            if req.agent == "judge_single":
                data["facts"] = {"claims": [], "reason": "scripted"}
            return RawReply(json.dumps(data), model_version="scripted")
        if req.mock_fallback is not None:
            out = req.mock_fallback(req)
            if out is not None:
                return RawReply(json.dumps(out), model_version="fallback")
        raise LLMError("no script")

    async def warm_up(self, model, timeout_ms):
        return None

    async def aclose(self):
        return None


async def make_env(**settings):
    backend = ScriptedBackend()
    ctx = make_ctx(backend=backend, **settings)
    rt = await live_runtime(ctx)
    return rt, backend


async def close_env(rt) -> None:
    rt.ctx.runtimes.shutdown()
    rt.ctx.scheduler.shutdown()


async def speak(rt, text: str, *, wait: bool = True, scene: str = "default"):
    t = await rt.inject_transcript(text, scenario=scene)
    if wait:
        await rt.ctx.scheduler.idle()
    return t


async def events(rt, type_: str | None = None) -> list[Event]:
    evs = await rt.ctx.store.query(rt.path("events"), Event, order_by="seq")
    return [e for e in evs if type_ is None or e.type == type_]


async def advance(rt, ms: int) -> None:
    await rt.ctx.scheduler.advance(ms)
