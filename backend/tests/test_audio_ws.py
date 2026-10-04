"""Audio WebSocket and STT stream bookkeeping (DEV_SPEC §10), with a fake speech provider."""
from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient

from app.main import create_app
from app.providers.stt import BYTES_PER_MS, SttResult, _StreamState, phrases_from_glossary

from .conftest import make_settings


class FakeStream:
    """Turns every 'utterance' frame (bytes starting with b'SAY:') into a final result."""

    def __init__(self) -> None:
        self.q: asyncio.Queue = asyncio.Queue()
        self.written = 0

    async def write(self, pcm: bytes) -> None:
        self.written += len(pcm)
        if pcm.startswith(b"SAY:"):
            await self.q.put(SttResult(pcm[4:].decode(), True, 123, 456))

    async def close(self) -> None:
        await self.q.put(None)

    async def results(self):
        while (item := await self.q.get()) is not None:
            yield item


class FakeStt:
    name = "fake"

    def __init__(self) -> None:
        self.opened: list[list[str]] = []

    def open(self, phrases, language=None):
        self.opened.append(phrases)
        return FakeStream()


def test_mic_finals_go_to_the_utterance_pipeline():
    app = create_app(make_settings())
    app.state.ctx.stt = FakeStt()
    with TestClient(app) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        client.post(f"/api/sessions/{sid}/start")
        with client.websocket_connect(f"/api/sessions/{sid}/audio") as ws:
            status = json.loads(ws.receive_text())
            assert status == {"type": "status", "state": "listening", "phrases": status["phrases"]}
            assert status["phrases"] > 5  # glossary phrase hints were sent
            ws.send_bytes(b"\x00" * 3200)
            ws.send_bytes(b"SAY:It's a lightweight gel-cream, so it absorbs really quickly.")
            final = json.loads(ws.receive_text())
            assert final["type"] == "final" and final["transcript_id"]
        state = client.get(f"/api/sessions/{sid}/state", params={"role": "operator"}).json()
        [t] = state["transcripts"]
        assert t["source"] == "mic" and t["speech_end_at"] == 123
        assert "DAON LAB" in app.state.ctx.stt.opened[0]


def test_mock_stt_rejects_audio():
    app = create_app(make_settings())  # STT_PROVIDER=mock -> ctx.stt is None
    with TestClient(app) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        with client.websocket_connect(f"/api/sessions/{sid}/audio") as ws:
            msg = json.loads(ws.receive_text())
            assert msg["state"] == "error" and "STT_PROVIDER=mock" in msg["message"]


def test_stream_state_maps_offsets_to_arrival_times():
    st = _StreamState()
    for i in range(5):  # five 100 ms chunks arriving at 1000, 1100, ... (end of each chunk's audio)
        st.add(b"\x00" * (100 * BYTES_PER_MS), 1000 + 100 * i)
    assert st.audio_ms == 500
    assert st.time_at(250) == 1150  # 50 ms before the end of the 3rd chunk (arrival 1200)
    assert st.time_at(500) == 1400
    st.last_final_ms = 220
    assert [c.offset_ms for c in st.tail_after(st.last_final_ms)] == [200, 300, 400]
    assert [c.offset_ms for c in st.tail_after(0, max_ms=150)] == [300, 400]  # bridge capped to recent audio


def test_phrases_from_glossary_dedupes_and_limits():
    g = {"terms": [{"term": "DAON LAB", "spoken_forms": ["day-on lab", "daon lab"]},
                   {"term": "niacinamide", "spoken_forms": ["nia-sin-a-mide"]}]}
    assert phrases_from_glossary(g) == ["DAON LAB", "day-on lab", "niacinamide", "nia-sin-a-mide"]
    assert len(phrases_from_glossary(g, limit=2)) == 2
