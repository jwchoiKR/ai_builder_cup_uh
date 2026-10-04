"""Experimental Jev gates; no production orchestration or implicit network calls.

Wire schema: https://docs.typesafe.ai/api (answers[id] = {type: noul, noul: number}).
"""
from __future__ import annotations

import asyncio
import math
import os
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

SPECIALISTS = ("compliance", "facts", "context")
ROUTER_DEADLINE_MS = 500  # p95 was ~300 ms from Seoul; 300 timed out 6/79
REPO_DIR = Path(__file__).resolve().parents[3]
QUESTIONS = {
    "compliance": {
        "type": "noul",
        "instructions": "Does this utterance need an advertising compliance judgment?",
        "criteria": {
            "true": "An affirmative cosmetic advertising claim about treating or preventing disease "
                    "or acne; permanent effects; modifying physiological function, cells or collagen; "
                    "reversing ageing or removing wrinkles or scars; cellulite, slimming, fat loss "
                    "or swelling; numbing; antimicrobial effects; safety or suitability for pregnant, "
                    "breastfeeding, infant or disease-vulnerable groups; comparative or superlative "
                    "claims; absolute safety; acting like medicine; whitening or changing skin colour; "
                    "or a correction or retraction of an active compliance alert.",
            "false": "No such claim or correction. Negated claims, quoted claims, greetings and chatter.",
        },
    },
    "facts": {
        "type": "noul",
        "instructions": "Does this utterance state a checkable product fact?",
        "criteria": {
            "true": "A product fact, right or wrong: price, set price, promotion, ingredient or amount, "
                    "volume, test result, usage, texture, fragrance, packaging, origin, shelf life, "
                    "or a restated fact resolving an "
                    "active fact alert. Numbers can be spelled out; facts need not contain numbers.",
            "false": "No checkable product fact: greetings, chatter, or a question without a fact.",
        },
    },
    "context": {
        "type": "noul",
        "instructions": "Does this utterance need viewer-question, prompter or product-switch tracking?",
        "criteria": {
            "true": "Answers or reads an open viewer question; covers an on-air product prompter "
                    "point (listed in prompter_points); names a product transition, including a quoted transition that must be "
                    "recognized as not a switch; or continues about the target product while a "
                    "switch is counting.",
            "false": "None of these tracking events. Greetings or unrelated chatter.",
        },
    },
}


def _env(name: str) -> str | None:
    if name in os.environ:
        return os.environ[name]
    return dotenv_values(REPO_DIR / ".env").get(name)


def get_threshold() -> float:
    """Reject invalid experiment configuration instead of silently changing its meaning."""
    raw = _env("JEV_THRESHOLD")
    try:
        value = float(raw) if raw is not None else 0.05
    except (TypeError, ValueError):
        raise ValueError("JEV_THRESHOLD must be a finite number from 0 to 1") from None
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("JEV_THRESHOLD must be a finite number from 0 to 1")
    return value


def build_state(case: dict, product_name: str, points: list[str] | tuple[str, ...] = ()) -> dict:
    ctx = case.get("context") or {}
    previous = ctx.get("recent_transcript") or []
    switch = ctx.get("switch_state") or {}
    return {
        "on_air_product": product_name,
        "prompter_points": list(points),
        "utterance": case["utterance"],
        "previous_line": previous[-1] if previous else None,
        "active_compliance_alerts": bool(ctx.get("active_alerts")),
        "active_fact_alerts": bool(ctx.get("active_fact_alerts")),
        "open_questions": [q["canonical_question"] for q in ctx.get("open_questions", [])],
        "switch_counting": switch.get("status") == "counting",
        "switch_target": switch.get("target_product_id"),
    }


def routing_overrides(case: dict, reflex) -> tuple[dict[str, bool], list[str]]:
    ctx = case.get("context") or {}
    reasons = []
    checks = (
        ("compliance:reflex", bool(reflex.scan(case["utterance"]))),
        ("compliance:active_alert", bool(ctx.get("active_alerts"))),
        ("facts:active_alert", bool(ctx.get("active_fact_alerts"))),
        ("context:open_questions", bool(ctx.get("open_questions"))),
        ("context:switch_counting", (ctx.get("switch_state") or {}).get("status") == "counting"),
    )
    forced = dict.fromkeys(SPECIALISTS, False)
    for reason, applies in checks:
        if applies:
            forced[reason.split(":", 1)[0]] = True
            reasons.append(reason)
    return forced, reasons


def apply_route(probs: dict | None, threshold: float, forced: dict) -> dict[str, bool]:
    return {name: bool(probs is None or forced.get(name, False) or probs[name] >= threshold)
            for name in SPECIALISTS}


def _probabilities(payload: object) -> dict[str, float]:
    if not isinstance(payload, dict) or not isinstance(payload.get("answers"), dict):
        raise ValueError("Missing answers")
    result = {}
    for name in SPECIALISTS:
        answer = payload["answers"].get(name)
        if not isinstance(answer, dict) or answer.get("type") != "noul":
            raise ValueError("Missing or incorrectly typed answer")
        probability = answer.get("noul")
        if (type(probability) not in (int, float) or not math.isfinite(probability)
                or not 0 <= probability <= 1):
            raise ValueError("Invalid probability")
        result[name] = float(probability)
    return result


class JevRouter:
    def __init__(self, *, api_key: str | None = None, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._key = api_key if api_key is not None else _env("OPENROUTER_API_KEY")
        self._client = httpx.AsyncClient(transport=transport, timeout=ROUTER_DEADLINE_MS / 1000,
                                       limits=httpx.Limits(max_keepalive_connections=20))
        self._warm_result: tuple[dict[str, float] | None, int, str] | None = None
        self._warm_lock = asyncio.Lock()

    async def _request(self, state: dict, deadline: float) -> tuple[dict[str, float] | None, int, str]:
        started = time.perf_counter()
        probs, status = None, "error"
        try:
            if not self._key:
                raise ValueError("Missing API key")
            async with asyncio.timeout(deadline):
                response = await self._client.post(
                    "https://openrouter.ai/api/v1/systemone",
                    headers={"Authorization": f"Bearer {self._key}"},
                    json={"model": "typesafe/jev-1.13", "state": state, "questions": QUESTIONS,
                          "provider": {"data_collection": "deny"}}, timeout=deadline,
                )
                response.raise_for_status()
                probs = _probabilities(response.json())
                status = "ok"
        except (TimeoutError, httpx.TimeoutException):
            status = "timeout"
        except (httpx.HTTPError, ValueError, TypeError, OverflowError):
            pass  # Do not log exception text: HTTP exceptions may include credentials or state.
        return probs, round((time.perf_counter() - started) * 1000), status

    async def route(self, state: dict) -> tuple[dict[str, float] | None, int, str]:
        return await self._request(state, ROUTER_DEADLINE_MS / 1000)

    async def warm_up(self) -> tuple[dict[str, float] | None, int, str]:
        """One unscored request; callers await this before starting timed evaluations."""
        async with self._warm_lock:
            if self._warm_result is None:
                self._warm_result = await self._request({"utterance": "Hello."}, 10.0)
        return self._warm_result

    async def aclose(self) -> None:
        await self._client.aclose()
