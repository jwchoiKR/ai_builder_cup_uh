"""D-327: the eval hook `phrases_for_release` returns exactly the speech hints the live stream sends (production's
base hints: the brief glossary, then the brand, product and ingredient names). D-435: the record-names mode and the
boost are gone. Made-up products only."""
from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from app.api.audio_ws import phrases_for_release
from app.onboarding.read import normalise
from app.onboarding.record import ProductRecord
from app.onboarding.release import product_key

from .judge_fakes import ScriptedBackend
from .test_audio_ws import FakeStt
from .test_onboarding import EV, _record

RECORD = _record(
    brand="Quillon", product_name="Kelpa Night Serum", short_names=["kelpa serum"],
    qualified_results=[{"statement": "31 of 33 panellists at Brindle Panel Group saw smoother skin in 4 weeks.",
                        "numbers": ["31", "33", "4"], "provenance": "third_party_lab",
                        "qualifier": "tested by Tessel Quay Labs (report TQ-2291)", "evidence": EV}],
    key_facts=[{"text": "Made in Korea. Certified under ISO 22716.", "evidence": EV},
               {"text": "Light gel texture.", "evidence": EV}])


def test_d327_the_eval_hook_returns_what_the_stream_sends(tmp_path):
    from app.main import create_app

    from .helpers import make_settings

    rid = f"rel_{product_key(normalise(ProductRecord.model_validate(RECORD))[0])}_v1"
    backend = ScriptedBackend()
    backend.outputs[("onboarding_read", "spec.txt")] = RECORD
    backend.fail("brief_agent", rid)
    app = create_app(make_settings(ONBOARDING_DIR=str(tmp_path)), llm_backend=backend)
    with TestClient(app) as c:
        job = c.post("/api/onboarding/jobs", files=[("files", ("spec.txt", b"hello", "text/plain"))]).json()["job_id"]
        for _ in range(100):
            if c.get(f"/api/onboarding/jobs/{job}").json()["status"] == "done":
                break
            time.sleep(0.02)
        assert c.post(f"/api/onboarding/jobs/{job}/approve", json={}).json()["release_id"] == rid
        sid = c.post("/api/sessions", json={"release_id": rid}).json()["session_id"]
        app.state.ctx.stt = FakeStt()
        with c.websocket_connect(f"/api/sessions/{sid}/audio") as ws:
            assert json.loads(ws.receive_text())["phrases"] > 0
        [sent] = app.state.ctx.stt.opened
        ctx = app.state.ctx
        assert phrases_for_release(ctx, rid) == sent == phrases_for_release(ctx, rid, mode="base")
    assert "Tessel Quay Labs" not in sent  # a test result's lab name is not a base hint
    assert sent[0] == "Quillon"
