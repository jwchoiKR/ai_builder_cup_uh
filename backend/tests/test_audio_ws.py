"""Audio WebSocket and STT stream bookkeeping (DEV_SPEC §10), with a fake speech provider."""
from __future__ import annotations

import asyncio
import json

import pytest
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
        self.languages: list[str | None] = []

    def open(self, phrases, language=None):
        self.opened.append(phrases)
        self.languages.append(language)
        return FakeStream()


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


@pytest.mark.parametrize("given, setting, sent", [(None, "", "en-US"), (None, "ko-KR", "ko-KR"), ("ja-JP", "ko-KR", "ja-JP")])
def test_d316_the_recognizer_s_language_code(given, setting, sent):
    from app.clock import SystemClock
    from app.providers.stt import GoogleV2Stt

    stt = GoogleV2Stt(make_settings(STT_LANGUAGE=setting, GCP_PROJECT="p"), SystemClock())
    assert list(stt.first_request([], given).streaming_config.config.language_codes) == [sent]
