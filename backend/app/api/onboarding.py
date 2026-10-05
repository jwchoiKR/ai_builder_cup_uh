"""Onboarding jobs (P0 step 1, docs/research/onboarding-spec.md): upload one product's files, read them in the
background with the same pipeline as scripts/eval_onboarding.py, and poll for the record."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel

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


async def _read_files(files: list[UploadFile]) -> list[tuple[str, bytes]]:
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
    return data


@router.post("/jobs")
async def create_job(files: list[UploadFile] = File(...), hints: str = Form(""),
                     ctx: AppContext = Depends(get_ctx)) -> dict:
    data = await _read_files(files)
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


class ApproveBody(BaseModel):
    record: dict | None = None  # D-224: the operator's edited record; None approves the read record as it is
    translations: dict | None = None  # D-233: the translations with the operator's per-line review


@router.post("/jobs/{job_id}/approve")
async def approve_job(job_id: str, body: ApproveBody | None = None, ctx: AppContext = Depends(get_ctx)) -> dict:
    """D-218: the approved record becomes an immutable release. D-224: the approval screen may send an edited record;
    it is validated and normalised like a read one (a value without evidence is dropped)."""
    from pydantic import ValidationError

    from ..onboarding.read import normalise
    from ..onboarding.record import ProductRecord
    from ..onboarding.release import release_pack, save_release

    job = _jobs.get(job_id)
    if job is None or job["status"] != "done":
        raise ActionError(409, "job_not_ready", f"onboarding job {job_id} has no record to approve")
    try:
        record = ProductRecord.model_validate((body.record if body and body.record else None) or job["result"]["record"])
    except ValidationError as e:
        raise ActionError(400, "invalid_record", str(e)[:400]) from None
    record, _ = normalise(record)
    # D-232: host-facing lines in every language the market offers, translated now (never live), marked for review
    from ..onboarding.translate import translate_record

    translations = (body.translations if body and body.translations is not None
                    else await translate_record(ctx.llm, record, [x.lang for x in ctx.pack.market.languages]))
    try:  # the show must be buildable in this server's market before the release is saved
        pack = release_pack(ctx.pack, record, "rel_check_v1", ctx.settings.onboarding_path, translations)
    except Exception as e:  # noqa: BLE001
        raise ActionError(409, "release_not_buildable", str(e)) from None
    warnings = [] if pack.rules.rules else [
        f"no law pack for {record.category} in {ctx.pack.market.market}: only brand-level checks run"]
    for lang, t in translations.items():
        lines = [*t.get("approved_claims", []), *t.get("cautions", []), *t.get("avoid_saying", [])]
        left = sum(1 for x in lines if not (isinstance(x, dict) and x.get("reviewed")))
        if left:
            warnings.append(f"{left} machine-translated lines in {lang} not reviewed: shown to the host marked, "
                            "never auto-posted")
    if record.language.split("-")[0] != ctx.pack.lang and ctx.pack.lang not in translations:
        warnings.append(f"no approved wording in {ctx.pack.lang}: alerts will have no replacement line")
    live = _live_summary(pack, record)  # D-231: what will happen live, in plain words
    return {"release_id": save_release(ctx.settings.onboarding_path, record, job_id, translations),
            "warnings": warnings, "live": live, "translations": translations}


def _live_summary(pack, record) -> dict:
    """D-231/D-234: what the show will get, in plain words."""
    rules = pack.rules
    law = (f"{len(rules.rules)} rules from {rules.policy_id}" if rules.rules else "no law checks for this category")
    p = pack.products.products[0]
    return {"law": law, "law_rules": len(rules.rules), "cautions": len(record.cautions),
            "approved_claims": len(record.approved_claims), "not_approved_claims": len(record.not_approved_claims),
            "promos": len(pack.promos.promos),
            "promo_lines": [f"{x.title}" + (f" · {pack.products.currency_symbol}{x.promo_prices[p.product_id]:.2f}"
                                            if x.promo_prices.get(p.product_id) else "") for x in pack.promos.promos],
            "price": f"{pack.products.currency_symbol}{p.live_price:.2f} live, "
                     f"{pack.products.currency_symbol}{p.list_price:.2f} list"}


@router.post("/jobs/{job_id}/preview")
async def preview_job(job_id: str, body: ApproveBody | None = None, ctx: AppContext = Depends(get_ctx)) -> dict:
    """D-233/D-234: before approval: the host-facing lines translated into the market's languages (for review) and
    what the show would get (rules applied, price, offers)."""
    from ..onboarding.read import normalise
    from ..onboarding.record import ProductRecord
    from ..onboarding.release import release_pack
    from ..onboarding.translate import translate_record

    job = _jobs.get(job_id)
    if job is None or job["status"] != "done":
        raise ActionError(409, "job_not_ready", f"onboarding job {job_id} has no record")
    record, _ = normalise(ProductRecord.model_validate((body.record if body and body.record else None)
                                                       or job["result"]["record"]))
    translations = await translate_record(ctx.llm, record, [x.lang for x in ctx.pack.market.languages])
    try:
        live = _live_summary(release_pack(ctx.pack, record, "rel_check_v1", ctx.settings.onboarding_path,
                                          translations), record)
    except Exception as e:  # noqa: BLE001
        live = {"error": str(e)}
    return {"translations": translations, "live": live}


@router.post("/lawpacks/jobs")
async def create_lawpack_job(files: list[UploadFile] = File(...), market: str = Form(...), category: str = Form(...),
                             ctx: AppContext = Depends(get_ctx)) -> dict:
    """D-229: regulator documents in, rule records with evidence out (approve with /jobs/{id}/approve-lawpack)."""
    from ..onboarding.files import model_part, store
    from ..onboarding.lawpack import read_lawpack

    data = await _read_files(files)
    job_id = "law_" + uuid.uuid4().hex[:12]
    _jobs[job_id] = {"job_id": job_id, "status": "queued", "files": [n for n, _ in data], "result": None, "error": None,
                     "market": market.upper(), "category": category}

    async def run() -> None:
        async with _running:
            _jobs[job_id]["status"] = "reading"
            try:
                for name, body in data:
                    store(ctx.settings.onboarding_path, job_id, name, body)
                rec, notes, secs = await read_lawpack(ctx.llm, [model_part(n, b) for n, b in data],
                                                      market=market.upper(), category=category)
                _jobs[job_id].update(status="done", result={"record": rec.model_dump(mode="json"), "notes": notes,
                                                            "seconds": secs})
            except Exception as e:  # noqa: BLE001 - reported on the job
                log.exception("law pack job %s failed", job_id)
                _jobs[job_id].update(status="failed", error=f"{type(e).__name__}: {e}")

    ctx.scheduler.spawn(run(), name=f"lawpack:{job_id}")
    return {"job_id": job_id, "status": "queued"}


@router.post("/jobs/{job_id}/approve-lawpack")
async def approve_lawpack(job_id: str, body: ApproveBody | None = None, ctx: AppContext = Depends(get_ctx)) -> dict:
    from pydantic import ValidationError

    from ..onboarding.lawpack import LawPackRecord, normalise_pack, save_lawpack

    job = _jobs.get(job_id)
    if job is None or job["status"] != "done" or "market" not in job:
        raise ActionError(409, "job_not_ready", f"law pack job {job_id} has no record to approve")
    try:
        rec = LawPackRecord.model_validate((body.record if body and body.record else None) or job["result"]["record"])
    except ValidationError as e:
        raise ActionError(400, "invalid_record", str(e)[:400]) from None
    rec, _ = normalise_pack(rec)
    return {"pack_id": save_lawpack(ctx.settings.onboarding_path, job["market"], rec, job_id)}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = _jobs.get(job_id)
    if job is None:
        raise ActionError(404, "job_not_found", f"onboarding job {job_id} not found")
    return job
