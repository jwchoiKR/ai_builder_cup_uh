"""D-427 (user, 10/10): law and brand packs without Gemini. An uploaded regulation PDF is stored as it is, with no
model call; the compliance judge reads it as an original. In a multi-release show each product keeps its own packs'
PDFs. Fictional packs and releases."""
from __future__ import annotations

import pytest

from app.agents.originals import originals_for
from app.onboarding.files import store
from app.onboarding.lawpack import LawPackRecord, save_brandpack, save_lawpack
from app.onboarding.release import product_key, save_release
from app.pipelines.runtime import create_session

from .helpers import make_ctx, make_settings, text_pdf
from .judge_fakes import ScriptedBackend, close_env, speak
from .test_onboarding import _record

CODE = text_pdf("Kelmar Supplement Code\n2.1 A supplement must not be presented as curing disease.\n")


class _Backend(ScriptedBackend):
    def __init__(self):
        super().__init__()
        self.requests = []

    async def generate(self, req, timeout_ms):
        self.requests.append(req)
        return await super().generate(req, timeout_ms)


@pytest.mark.originals
async def test_d427_an_uploaded_law_pack_pdf_reaches_the_judge_with_no_model_call(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    backend = _Backend()
    backend.outputs[("onboarding_read", "supp.txt")] = _record(category="food_supplement", product_name="Joint Caps")
    with TestClient(create_app(make_settings(ONBOARDING_DIR=str(tmp_path)), llm_backend=backend)) as c:
        law = c.post("/api/onboarding/lawpacks/jobs", data={"market": "SG", "category": "food_supplement"},
                     files=[("files", ("kelmar_code.pdf", CODE, "application/pdf"))]).json()
        assert law["status"] == "done"  # at once: nothing reads the files
        pack_id = c.post(f"/api/onboarding/jobs/{law['job_id']}/approve-lawpack", json={}).json()["pack_id"]
        assert backend.requests == [] and backend.calls == []
        j = c.post("/api/onboarding/jobs", files=[("files", ("supp.txt", b"spec", "text/plain"))]).json()["job_id"]
        for _ in range(200):
            if c.get(f"/api/onboarding/jobs/{j}").json()["status"] in ("done", "failed"):
                break
        release_id = c.post(f"/api/onboarding/jobs/{j}/approve", json={}).json()["release_id"]
    assert not any(r.agent == "lawpack_read" for r in backend.requests)

    llm = _Backend()
    ctx = make_ctx(backend=llm, ONBOARDING_DIR=str(tmp_path))
    s = await create_session(ctx, "", release_id=release_id)
    rt = await ctx.runtimes.get(s.session_id)
    await rt.start()
    await ctx.scheduler.advance(5000)
    try:
        assert rt.pack.rules.pack_ids == [pack_id] and rt.pack.rules.rules == []
        await speak(rt, "This tub has sixty capsules.")
        req = [r for r in llm.requests if r.agent == "compliance_judge"][-1]
        assert "kelmar_code.pdf" in req.user_message and (CODE, "application/pdf") in req.cache_parts
    finally:
        await close_env(rt)


async def test_d427_a_multi_release_show_keeps_each_product_s_own_pack_pdfs(tmp_path):
    from .test_clean_base import clean_data, kettle
    from .test_multi_release import cream

    onb = tmp_path / "onb"
    save_lawpack(onb, "SG", LawPackRecord(covers=["kitchen_appliance"]), "jlaw")
    store(onb, "jlaw", "kettle_code.pdf", text_pdf("3 No claim of safety for children."))
    save_brandpack(onb, "Lumen", LawPackRecord(covers=["brand:Lumen"]), "jbrand")
    store(onb, "jbrand", "lumen_brand.pdf", text_pdf("1 Never say the cream heals."))
    ids = [save_release(onb, cream(), "job_c"), save_release(onb, kettle(), "job_k")]
    ctx = make_ctx(backend=ScriptedBackend(), DATA_DIR=str(clean_data(tmp_path)), ONBOARDING_DIR=str(onb))
    s = await create_session(ctx, "", release_ids=ids)
    rt = await ctx.runtimes.get(s.session_id)
    try:
        cream_id, kettle_id = product_key(cream()), product_key(kettle())
        names = lambda pids: {d.name for d in originals_for(rt.catalog, onb, pids)[0]}  # noqa: E731
        assert "lumen_brand.pdf" in names([cream_id]) and "kettle_code.pdf" not in names([cream_id])
        assert names([kettle_id]) == {"kettle_code.pdf"}
        assert names([cream_id, kettle_id]) == names([cream_id]) | {"kettle_code.pdf"}
    finally:
        await close_env(rt)
