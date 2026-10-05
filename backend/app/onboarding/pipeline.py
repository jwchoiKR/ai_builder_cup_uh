"""Onboarding steps 1-3 as one call, used by the API and by scripts/eval_onboarding.py (the same app path)."""
from __future__ import annotations

from pathlib import Path

from ..providers.llm import LLMClient
from .files import media_type, model_part, store
from .read import read_product
from .record import OnboardingResult


async def onboard_files(llm: LLMClient, root: Path, draft_id: str, files: list[tuple[str, bytes]], *,
                        hints: str = "", session_id: str | None = None, **read_kw) -> OnboardingResult:
    stored = [store(root, draft_id, name, data) for name, data in files]
    parts = [model_part(name, data) for name, data in files]
    result = await read_product(llm, parts, hints=hints, session_id=session_id, **read_kw)
    result.files = [{"name": s.name, "sha256": s.sha256, "media_type": media_type(s.name), "bytes": s.size}
                    for s in stored]
    return result
