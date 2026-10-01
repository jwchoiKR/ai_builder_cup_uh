"""Confirmed Setup state is frozen into the next session (DEV_SPEC §8.15, §12.7)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

from .conftest import make_settings


def test_confirmed_points_and_glossary_apply_from_the_next_session():
    app = create_app(make_settings())
    with TestClient(app) as c:
        before = c.post("/api/sessions").json()
        assert before["glossary_version"] == 0 and before["prompter_points"] == {}
        body = {"products": {"cream_hydra_barrier": {
            "glossary": [{"term": "DAON LAB", "kind": "brand", "spoken_forms": ["day-on lab"],
                          "source_section": "Product overview", "include": True}],
            "prompter_points": [
                {"text": "Light gel-cream that absorbs fast.", "action": "replace", "point_id": "cr-p1"},
                {"text": "Airless pump tube.", "action": "add"},
            ],
        }}}
        r = c.post("/api/setup/glossary/confirm", json=body)
        assert r.status_code == 200, r.text
        after = c.post("/api/sessions").json()
        assert after["glossary_version"] == 1
        points = after["prompter_points"]["cream_hydra_barrier"]
        assert points[0]["point_id"] == "cr-p1" and points[0]["text"] == "Light gel-cream that absorbs fast."
        assert any(p["point_id"] == "cr-x1" and not p["required"] for p in points)
        c.post(f"/api/sessions/{after['session_id']}/start")
        prompter = c.get(f"/api/sessions/{after['session_id']}/state").json()["prompter"]
        assert prompter["points"][0]["text"] == "Light gel-cream that absorbs fast."
        assert prompter["required_total"] == 3  # required flags never change through Setup
        old = c.get(f"/api/sessions/{before['session_id']}/state").json()["prompter"]
        assert old["product_id"] is None  # the earlier session was never started; nothing leaks
