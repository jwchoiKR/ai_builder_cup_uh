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
