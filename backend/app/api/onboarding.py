"""Onboarding jobs (P0 step 1, docs/research/onboarding-spec.md): upload one product's files, read them in the
background with the same pipeline as scripts/eval_onboarding.py, and poll for the record."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile

from ..context import AppContext, get_ctx
from ..onboarding.files import MAX_BYTES, UnsupportedFile
from ..onboarding.pipeline import onboard_files
from ..pipelines.runtime import ActionError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/onboarding")

MAX_FILES = 20
MAX_JOB_BYTES = 60 * 1024 * 1024
MAX_RUNNING = 2  # reads in flight per process: each is one long model call
_running = asyncio.Semaphore(MAX_RUNNING)
_jobs: dict[str, dict] = {}


@router.post("/jobs")
async def create_job(files: list[UploadFile] = File(...), hints: str = Form(""),
                     ctx: AppContext = Depends(get_ctx)) -> dict:
    if not files or len(files) > MAX_FILES:
        raise ActionError(400, "bad_files", f"send 1 to {MAX_FILES} files")
    data = []
    total = 0
    for f in files:
        body = await f.read(MAX_BYTES + 1)
        total += len(body)
        if len(body) > MAX_BYTES or total > MAX_JOB_BYTES:
            raise ActionError(413, "too_large", "a file or the job is too large")
        data.append((f.filename or "file", body))
    job_id = "onb_" + uuid.uuid4().hex[:12]
    _jobs[job_id] = {"job_id": job_id, "status": "queued", "files": [n for n, _ in data], "result": None, "error": None}

    async def run() -> None:
        async with _running:
            _jobs[job_id]["status"] = "reading"
            try:
                result = await onboard_files(ctx.llm, ctx.settings.onboarding_path, job_id, data,
                                             hints=hints[:500])
                out = result.model_dump(mode="json")
                (ctx.settings.onboarding_path / job_id / "result.json").write_text(
                    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
                _jobs[job_id].update(status="done", result=out)
            except UnsupportedFile as e:
                _jobs[job_id].update(status="failed", error=str(e))
            except Exception as e:  # noqa: BLE001 - reported on the job
                log.exception("onboarding job %s failed", job_id)
                _jobs[job_id].update(status="failed", error=f"{type(e).__name__}: {e}")

    ctx.scheduler.spawn(run(), name=f"onboarding:{job_id}")
    return {"job_id": job_id, "status": "queued"}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = _jobs.get(job_id)
    if job is None:
        raise ActionError(404, "job_not_found", f"onboarding job {job_id} not found")
    return job
