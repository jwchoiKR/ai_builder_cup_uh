"""D-332: /demo/current gives every screen opened without ?session the current demo show: the newest demo show that
has not ended, else a new one. An ended show or another show (a release show, a test drive) is never picked."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

from .helpers import make_settings


def test_d332_demo_current_skips_ended_and_other_shows():
    with TestClient(create_app(make_settings())) as c:
        demo = c.post("/api/sessions").json()["session_id"]  # the shipped run-sheet: a demo show
        assert c.get("/api/demo/current").json()["session_id"] == demo
        c.post(f"/api/sessions/{demo}/start")
        c.post(f"/api/sessions/{demo}/end")
        fresh = c.get("/api/demo/current").json()  # the only demo show ended: a new one
        assert fresh["session_id"] != demo and fresh["status"] == "ready"
        assert c.get("/api/demo/current").json()["session_id"] == fresh["session_id"]  # and it stays the current one
