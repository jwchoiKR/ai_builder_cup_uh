"""Helpers the eval scripts share (D-435: moved here from run_eval.py when its legacy-judge eval was retired)."""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.clock import SystemClock  # noqa: E402
from app.config import REPO_DIR, get_settings  # noqa: E402
from app.ids import Ids  # noqa: E402
from app.models.session import QuestionGroup  # noqa: E402
from app.providers.llm import LLMClient, RecordingBackend, VertexBackend  # noqa: E402

EVAL_DIR = REPO_DIR / "docs" / "eval"


def load_cases(name: str) -> list[dict]:
    path = get_settings().data_path / "eval" / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, max(0, round(q * (len(s) - 1))))]


def latency_line(values: list[int]) -> str:
    if not values:
        return "n/a"
    return f"p50 {statistics.median(values):.0f} ms · p95 {pct(values, 0.95):.0f} ms · max {max(values)} ms (n={len(values)})"


def make_client(record: bool) -> tuple[LLMClient, object]:
    settings = get_settings()
    backend = VertexBackend(settings.GCP_PROJECT, settings.LLM_LOCATION,
                            context_cache=settings.LLM_CONTEXT_CACHE,
                            cache_ttl_sec=settings.LLM_CONTEXT_CACHE_TTL_SEC)
    if record:
        backend = RecordingBackend(backend)
    clock = SystemClock()
    return LLMClient(backend, settings, clock, Ids(clock, deterministic=False)), backend


def _group(g: dict, now: int) -> QuestionGroup:
    return QuestionGroup(group_id=g["group_id"], product_id=g.get("product_id"), intent=g["intent"],
                         condition_slots=g.get("condition_slots") or {}, canonical_question=g["canonical_question"],
                         member_comment_ids=[], unique_author_ids=[], first_at=now, last_at=now, route="HOST",
                         route_reason="eval", status="ready")


def _norm_value(v: str | None) -> str:
    import re

    # "+45%" is the same value as "45%" (holdout H052)
    return " ".join(re.sub(r"\+(?=\d)", "", (v or "").lower()).replace("ml", " ml").split())


def _same_value(got: str | None, want: str) -> bool:
    from app.logic.verify import number_set

    return _norm_value(got) == _norm_value(want) or (
        number_set(got or "") == number_set(want) and set(_norm_value(want).split()) - set(number_set(want))
        <= set(_norm_value(got).split()) | {"s$"})
