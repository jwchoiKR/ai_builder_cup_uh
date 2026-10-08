from __future__ import annotations

import asyncio
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from app.main import create_app

from .conftest import make_settings


@pytest.fixture
def client():
    with TestClient(create_app(make_settings())) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["providers"] == {"llm": "mock", "stt": "mock", "store": "memory", "retriever": "local"}
    assert body["models"]["fast"] == {"id": "gemini-3.5-flash-lite", "thinking": "MINIMAL"}
    assert body["models"]["quality"] == {"id": "gemini-3.8-flash", "thinking": "MEDIUM"}
    assert body["prompts"]["utterance_judge"] == "utterance_judge_v3"


def test_catalog(client):
    body = client.get("/api/catalog").json()
    cream = next(p for p in body["products"] if p["product_id"] == "cream_hydra_barrier")
    assert cream["live_price_display"] == "S$36.00" and cream["list_price_display"] == "S$48.00"
    sale = next(p for p in body["promos"] if p["promo_id"] == "promo_time_sale_10")
    assert sale["promo_prices_display"]["set_cream_ampoule"] == "S$55.80"
    assert body["set_offers"][0]["live_price_display"] == "S$62.00"
    assert body["set_offers"][0]["short_name"] == "Cream + Ampoule set"  # D-085


def test_create_session(client):
    r = client.post("/api/sessions", json={})
    assert r.status_code == 201
    s = r.json()
    assert s["session_id"] == "ses_000001" and s["status"] == "ready"
    assert s["runsheet_id"] == "daon_skincare_demo" and s["title"] == "DAON LAB · Skincare session"
    assert s["settings_snapshot"]["HOST_TOP_N"] == 6 and s["switch"]["status"] == "idle"
    assert client.post("/api/sessions").status_code == 201  # body optional


def test_errors_use_the_spec_shape(client):
    r = client.post("/api/sessions", json={"runsheet_id": "nope"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "unknown_runsheet"
    r = client.get("/api/sessions/ses_missing/events")
    assert r.status_code == 404 and r.json()["error"]["code"] == "session_not_found"
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = client.post("/api/sessions", json={"runsheet_id": 5})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_sse_over_http_replays_and_resumes_with_last_event_id():
    """Real uvicorn server: persisted events replay, Last-Event-ID resumes, live events stream."""
    app = create_app(make_settings())
    ctx = app.state.ctx
    ctx.sse_heartbeat_sec = 0.2
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    loop_holder: dict = {}

    def run() -> None:
        loop = asyncio.new_event_loop()
        loop_holder["loop"] = loop
        loop.run_until_complete(server.serve())

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}/api"
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        sid = httpx.post(f"{base}/sessions").json()["session_id"]

        def emit(type_: str, payload: dict) -> None:
            asyncio.run_coroutine_threadsafe(ctx.bus.emit(sid, type_, payload), loop_holder["loop"]).result(5)

        emit("cue.updated", {"n": 1})
        emit("cue.updated", {"n": 2})

        def read_events(headers: dict, want: int, after_connect=None) -> list[tuple[str, str]]:
            got: list[tuple[str, str]] = []
            with httpx.stream("GET", f"{base}/sessions/{sid}/events", params={"role": "operator"}, headers=headers,
                              timeout=5) as r:
                assert r.status_code == 200
                assert r.headers["content-type"].startswith("text/event-stream")
                current_id = None
                for line in r.iter_lines():
                    if line.startswith("id: "):
                        current_id = line[4:]
                    elif line.startswith("data: ") and current_id:
                        got.append((current_id, line[6:]))
                        if after_connect and len(got) == 1:
                            after_connect()
                        if len(got) == want:
                            break
            return got

        assert read_events({}, 2) == [("1", '{"n":1}'), ("2", '{"n":2}')]
        resumed = read_events({"Last-Event-ID": "1"}, 2, after_connect=lambda: emit("cue.updated", {"n": 3}))
        assert resumed == [("2", '{"n":2}'), ("3", '{"n":3}')]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_show_mode_is_chosen_at_creation_and_defaults_to_solo(client):
    """D-111: solo or team, chosen when the session is created."""
    solo = client.post("/api/sessions").json()
    team = client.post("/api/sessions", json={"show_mode": "team"}).json()
    assert (solo["show_mode"], team["show_mode"]) == ("solo", "team")
    assert client.post("/api/sessions", json={"show_mode": "duo"}).status_code == 422


def test_driver_sessions_never_delete_other_sessions(client):
    """D-139: two drivers share one service; /demo/sessions deletes nothing (/demo/reset drops the latest)."""
    a = client.post("/api/demo/sessions", json={"assistant": False}).json()
    client.post(f"/api/sessions/{a['session_id']}/start")
    b = client.post("/api/demo/sessions", json={}).json()
    assert a["assistant"] is False and b["assistant"] is True
    assert client.get(f"/api/sessions/{a['session_id']}/state?role=operator").status_code == 200
    c = client.post(f"/api/sessions/{b['session_id']}/demo/comments", json={"author": "Amy", "text": "how much?"})
    assert c.status_code == 201 and c.json()["source"] == "script"
