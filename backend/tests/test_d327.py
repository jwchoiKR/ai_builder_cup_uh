"""D-327: STT_HINTS=record adds each on-show release's own names and sizes (record) to the speech hints, after the
brief glossary and the base names, under the same cap; STT_HINT_BOOST puts one boost on the phrase set. The eval
hook `phrases_for_release` returns exactly what the live stream sends. Made-up products only."""
from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from app.api.audio_ws import phrases_for_release, record_terms
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


def test_d327_record_terms():
    r, _ = normalise(ProductRecord.model_validate(RECORD))
    terms = record_terms(r)
    assert terms[:3] == ["Quillon", "Kelpa Night Serum", "kelpa serum"]
    for t in ("P 30", "Tessel Quay Labs", "TQ-2291", "Brindle Panel Group", "30 ml", "Korea", "ISO 22716"):
        assert t in terms, t
    assert not any(t.isdigit() or "S$" in t or "36" in t for t in terms)  # no prices or bare numbers
    assert "Light gel texture." not in terms and "Light" not in terms  # no sentences, no sentence-start words
    assert len({t.lower() for t in terms}) == len(terms)


@pytest.mark.parametrize("mode", ["base", "record"])
def test_d327_the_eval_hook_returns_what_the_stream_sends(tmp_path, mode):
    from app.main import create_app

    from .helpers import make_settings

    rid = f"rel_{product_key(normalise(ProductRecord.model_validate(RECORD))[0])}_v1"
    backend = ScriptedBackend()
    backend.outputs[("onboarding_read", "spec.txt")] = RECORD
    backend.fail("brief_agent", rid)
    app = create_app(make_settings(ONBOARDING_DIR=str(tmp_path), STT_HINTS=mode, STT_RISK_HINTS=True),
                     llm_backend=backend)
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
        assert phrases_for_release(ctx, rid) == sent
        assert phrases_for_release(ctx, rid, mode="record" if mode == "base" else "base") != sent
    assert ("Tessel Quay Labs" in sent) is (mode == "record")
    assert sent[0] == "Quillon"


def test_d327_the_boost_goes_on_the_phrase_set():
    from app.clock import SystemClock
    from app.providers.stt import GoogleV2Stt

    from .helpers import make_settings

    def boost(value):
        stt = GoogleV2Stt(make_settings(GCP_PROJECT="p", STT_HINT_BOOST=value), SystemClock())
        return stt.first_request(["Tessel Quay"]).streaming_config.config.adaptation.phrase_sets[0] \
            .inline_phrase_set.boost

    assert boost("") == 0 and boost("10") == 10


@pytest.mark.parametrize("value", ["loud", "25"])
def test_d327_a_bad_boost_fails_at_startup(value):
    from pydantic import ValidationError

    from .helpers import make_settings

    with pytest.raises(ValidationError):
        make_settings(STT_HINT_BOOST=value)
