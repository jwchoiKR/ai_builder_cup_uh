"""Scripted LLM backend and output builders for utterance-path tests (no Vertex, no fixtures)."""
from __future__ import annotations

import asyncio
import json

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
