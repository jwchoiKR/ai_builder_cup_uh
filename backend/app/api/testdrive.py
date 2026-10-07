"""Judge test drive (D-238): one button on the deployed link. A bundled fictional sample product is onboarded (read
once, then reused), approved with one visible click, and a short scene plays on its show. Rate-capped."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from ..context import AppContext, get_ctx
from ..pipelines import testdrive as td
from ..pipelines.runtime import ActionError, create_session
from ..providers import tts
from .errors import ApiError
from .onboarding import ApproveBody, approve_job, done_job, start_job

router = APIRouter(prefix="/testdrive")


@router.post("/start")
async def start(ctx: AppContext = Depends(get_ctx)) -> dict:
    try:
        td.allow_start()
    except td.TestDriveBusy as e:
        raise ActionError(429, "testdrive_busy", str(e)) from None
    files = td.sample_files(ctx.settings.data_path)
    key = td.cache_key(files)
    root = ctx.settings.onboarding_path
    cached = td.load_cached(root, key)
    job = done_job(files, cached) if cached else start_job(
        ctx, files, on_done=lambda out: td.save_cached(root, key, out))
    td.admit(job["job_id"])
    return {"job_id": job["job_id"], "status": job["status"], "files": [n for n, _ in files], "cached": bool(cached)}


@router.get("/audio/{name}")
async def audio(name: str) -> FileResponse:
    """D-320: a host line's speech, as the scene streams it into speech-to-text."""
    path = tts.path_of(name.removesuffix(".wav")) if name.endswith(".wav") else None
    if path is None:
        raise ApiError(404, "no_audio", "no such line audio")
    return FileResponse(path, media_type="audio/wav")


@router.post("/{job_id}/go")
async def go(job_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    """The approval click: approve the read as it is (translations as read), start the show, play the scene.
    D-322: only for the job its /start admitted, once, and one drive at a time (the spend cap)."""
    try:
        td.claim(job_id)
    except td.TestDriveBusy as e:
        raise ActionError(429, "testdrive_busy", str(e)) from None
    try:
        approved = await approve_job(job_id, ApproveBody(), ctx)
        s = await create_session(ctx, "testdrive", release_id=approved["release_id"])
        rt = await ctx.runtimes.get(s.session_id)
        await rt.start()
    except BaseException:
        td.release(job_id)  # D-323: the job can be tried again
        raise

    async def drive() -> None:
        try:
            await td.play(rt)
        finally:
            td.finish(job_id)

    ctx.scheduler.spawn(drive(), name=f"testdrive:{s.session_id}")
    return {"session_id": s.session_id, **approved}
