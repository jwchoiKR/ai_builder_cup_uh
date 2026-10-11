"""The Demo Console's AI lines: host lines or viewer comments written by the model for the show's products; nothing is
sent to the show until the console injects or posts them."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

from .helpers import make_settings, product_show
from .judge_fakes import ScriptedBackend
from .test_d358 import CODE


def test_generate_writes_lines_for_the_show_s_products_and_sends_nothing():
    backend = ScriptedBackend()
    backend.outputs[("demo_generate", "comments|price questions")] = {"lines": ["Mina: How much?", " ", "Jo: Vegan?"]}
    app = create_app(make_settings(), llm_backend=backend)
    with TestClient(app) as c:
        key = product_show(app.state.ctx, {"brand": "Kelmar", "product_name": "Joint Ease", "currency": "SGD",
                                           "variants": [{"label": "", "list_price": "30.00", "live_price": "25.00"}],
                                           "points": [{"text": "Supports joint comfort.", "required": True}]},
                           [("kelmar_code.pdf", CODE)])
        sid = c.post("/api/sessions", json={"release_id": key}).json()["session_id"]
        r = c.post(f"/api/sessions/{sid}/demo/generate",
                   json={"kind": "comments", "count": 5, "instruction": "price questions"})
        assert r.status_code == 200, r.text
        assert r.json() == {"lines": ["Mina: How much?", "Jo: Vegan?"]}
        assert c.get(f"/api/sessions/{sid}/state?role=operator").json().get("comments", []) == []
        assert c.post(f"/api/sessions/{sid}/demo/generate", json={"kind": "other"}).status_code == 400
