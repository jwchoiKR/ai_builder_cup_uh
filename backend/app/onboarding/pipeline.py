"""Onboarding steps 1-3 as one call, used by the API and by scripts/eval_onboarding.py (the same app path)."""
from __future__ import annotations

from pathlib import Path

from ..providers.llm import LLMClient
from .files import media_type, model_part, store
from .read import read_product
from .checks import check_items, summary
from .record import OnboardingResult
from .release import release_pack


async def onboard_files(llm: LLMClient, root: Path, draft_id: str, files: list[tuple[str, bytes]], *,
                        hints: str = "", session_id: str | None = None, base_pack=None, verify_mode: str = "full",
                        **read_kw) -> OnboardingResult:
    stored = [store(root, draft_id, name, data) for name, data in files]
    parts = [model_part(name, data) for name, data in files]
    result = await read_product(llm, parts, hints=hints, session_id=session_id, **read_kw)
    result.files = [{"name": s.name, "sha256": s.sha256, "media_type": media_type(s.name), "bytes": s.size}
                    for s in stored]
    # D-236: what a person must check (VERIFY_MODE), with the law pack the show would get
    law = None
    if base_pack is not None:
        try:
            pack = release_pack(base_pack, result.record, "rel_check_v1", root)
            law = f"{len(pack.rules.rules)} rules" if pack.rules.rules else "no law checks"
        except Exception as e:  # noqa: BLE001 - the show cannot be built: a check item of its own
            law = f"not buildable: {e}"
    result.verify_mode = verify_mode
    result.checks = check_items(result, verify_mode, law=law, caution_pass_only=result.caution_pass_added)
    result.check_summary = summary(result.checks)
    return result
