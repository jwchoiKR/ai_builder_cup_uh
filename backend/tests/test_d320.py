"""D-320: the judge test drive speaks the host's lines (Cloud TTS) into the session's speech-to-text stream, paced as
a mic is, so the finals take the normal path; the browser gets each line's audio when its streaming starts. A line
with no final within FALLBACK_S after its audio goes in as text; no speech-to-text or no speech means text, as before.
Also: every event type the backend emits is one the browser subscribes to."""
from __future__ import annotations

import asyncio
import io
import re
import wave
from pathlib import Path

import pytest

from app.models.session import Transcript
from app.pipelines import testdrive as td
from app.providers import tts as tts_mod
from app.providers.stt import SttResult

from .judge_fakes import close_env, events


class _Stream:
    """A final for every frame that starts with b"SAY:" (unless deaf); counts the frames written."""

    def __init__(self, deaf: bool) -> None:
        self.deaf, self.frames = deaf, 0
        self.q: asyncio.Queue = asyncio.Queue()

    async def write(self, pcm: bytes) -> None:
        self.frames += 1
        if pcm.startswith(b"SAY:") and not self.deaf:
            await self.q.put(SttResult(pcm[4:].rstrip(b"\x00").decode(), True, 123, 456))

    async def close(self) -> None:
        await self.q.put(None)

    async def results(self):
        while (item := await self.q.get()) is not None:
            yield item


class _Stt:
    def __init__(self, deaf: bool = False) -> None:
        self.deaf, self.opened = deaf, []

    def open(self, phrases, language=None):
        self.opened.append(language)
        return _Stream(self.deaf)


class _Tts:
    """Writes a WAV whose samples spell b"SAY:<text>", where the real one would hold speech."""

    def __init__(self, fail: bool = False) -> None:
        self.fail, self.made = fail, []

    async def wav(self, text: str) -> str:
        if self.fail:
            raise RuntimeError("tts down")
        key = tts_mod.key_of(text)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16_000)
            data = b"SAY:" + text.encode()
            w.writeframes(data + b"\x00" * (len(data) % 2))
        tts_mod.CACHE.mkdir(parents=True, exist_ok=True)
        (tts_mod.CACHE / f"{key}.wav").write_bytes(buf.getvalue())
        self.made.append(text)
        return key


async def _transcripts(rt, n: int, timeout: float = 3.0) -> list[Transcript]:
    for _ in range(int(timeout / 0.05)):
        found = await rt.ctx.store.query(rt.path("transcripts"), Transcript)
        if len(found) >= n:
            return found
        await asyncio.sleep(0.05)
    return await rt.ctx.store.query(rt.path("transcripts"), Transcript)


@pytest.fixture(autouse=True)
def _cache(tmp_path, monkeypatch):
    monkeypatch.setattr(tts_mod, "CACHE", tmp_path / "tts")


async def _rt(stt):
    from .helpers import live_runtime, make_ctx

    rt = await live_runtime(make_ctx())
    rt.ctx.stt = stt
    return rt


async def test_d320_a_spoken_line_goes_through_speech_to_text():
    rt = await _rt(_Stt())
    try:
        voice = await td._voice(rt, ["Hi everyone, welcome!"], _Tts())
        assert voice is not None and rt.ctx.stt.opened == ["en-US"]
        assert await voice.say("Hi everyone, welcome!")
        [t] = await _transcripts(rt, 1)
        assert (t.source, t.text, t.speech_end_at) == ("mic", "Hi everyone, welcome!", 123)  # the mic's path
        [ev] = await events(rt, "testdrive.audio")
        assert re.fullmatch(r"/api/testdrive/audio/[0-9a-f]{16}\.wav", ev.payload["url"])
        assert ev.payload["text"] == "Hi everyone, welcome!"
        await voice.close()
    finally:
        await close_env(rt)


async def test_d320_no_final_falls_back_to_text(monkeypatch, caplog):
    monkeypatch.setattr(td, "FALLBACK_S", 0.05)
    caplog.set_level("INFO", logger="app.pipelines.testdrive")
    rt = await _rt(_Stt(deaf=True))
    try:
        voice = await td._voice(rt, [], _Tts())
        assert await voice.say("Sorry, let me correct that.")
        [t] = await _transcripts(rt, 1)
        assert (t.source, t.text) == ("injected", "Sorry, let me correct that.")
        assert any("testdrive stt fallback" in r.getMessage() for r in caplog.records)
        await voice.close()
    finally:
        await close_env(rt)


async def test_d320_no_speech_means_text():
    rt = await _rt(None)  # STT_PROVIDER=mock
    try:
        assert await td._voice(rt, ["Hi"], _Tts()) is None
    finally:
        await close_env(rt)
    rt = await _rt(_Stt())
    try:
        voice = await td._voice(rt, ["Hi"], _Tts(fail=True))  # the voice still opens; each line says False
        assert voice is not None and not await voice.say("Hi")
        await voice.close()
    finally:
        await close_env(rt)


def test_d320_the_audio_endpoint_serves_only_cached_keys(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    from .helpers import make_settings

    key = asyncio.run(_Tts().wav("Hello there."))
    with TestClient(create_app(make_settings())) as c:
        r = c.get(f"/api/testdrive/audio/{key}.wav")
        assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
        assert c.get("/api/testdrive/audio/0123456789abcdef.wav").status_code == 404
        assert c.get("/api/testdrive/audio/..%2Fsecret.wav").status_code == 404


def test_d320_every_emitted_event_type_is_subscribed_by_the_browser():
    """D-298 line.check and D-306 verify.* were emitted but the browser never listened (fixed with D-320)."""
    root = Path(__file__).resolve().parents[2]
    emitted = set()
    for p in (root / "backend" / "app").rglob("*.py"):
        emitted |= set(re.findall(r'emit\(\s*"([a-z_.]+)"', p.read_text(encoding="utf-8")))
    listed = set(re.findall(r'^\s+"([a-z_.]+)",', (root / "frontend/src/app/sse.ts").read_text(encoding="utf-8"), re.M))
    assert emitted - listed == set()
