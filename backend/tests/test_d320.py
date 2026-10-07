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
    """A final for every frame that starts with b"SAY:" (unless deaf, or the line says "(unheard)"), timed by the
    session clock, which each 100 ms frame moves on as real time would."""

    def __init__(self, deaf: bool, clock) -> None:
        self.deaf, self.clock, self.frames, self.closed = deaf, clock, 0, False
        self.q: asyncio.Queue = asyncio.Queue()

    async def write(self, pcm: bytes) -> None:
        self.frames += 1
        now = self.clock.advance(td.FRAME_MS)
        text = pcm[4:].rstrip(b"\x00").decode() if pcm.startswith(b"SAY:") else ""
        if text and not self.deaf and "(unheard)" not in text:
            await self.q.put(SttResult(text, True, now, now))

    async def close(self) -> None:
        self.closed = True
        await self.q.put(None)

    async def results(self):
        while (item := await self.q.get()) is not None:
            yield item


class _Stt:
    def __init__(self, deaf: bool = False) -> None:
        self.deaf, self.opened, self.streams, self.clock = deaf, [], [], None

    def open(self, phrases, language=None):
        self.opened.append(language)
        self.streams.append(_Stream(self.deaf, self.clock))
        return self.streams[-1]


class _Tts:
    """Writes a WAV whose samples spell b"SAY:<text>", where the real one would hold speech."""

    def __init__(self, fail: bool = False, delay: float = 0.0) -> None:
        self.fail, self.delay, self.made = fail, delay, []

    async def wav(self, text: str) -> str:
        await asyncio.sleep(self.delay)
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
    if stt is not None:
        stt.clock = rt.ctx.clock
    rt.ctx.stt = stt
    return rt


async def test_d320_a_spoken_line_goes_through_speech_to_text():
    rt = await _rt(_Stt())
    try:
        voice = await td._voice(rt, ["Hi everyone, welcome!"], _Tts())
        assert voice is not None and rt.ctx.stt.opened == ["en-US"]
        assert await voice.say("Hi everyone, welcome!")
        [t] = await _transcripts(rt, 1)
        assert (t.source, t.text) == ("mic", "Hi everyone, welcome!")  # the mic's path
        assert voice.lines[0].outcome == "stt"
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


async def test_d322_a_late_final_after_the_fallback_is_dropped(monkeypatch):
    """One outcome per line: once the line went in as text, its late final is not judged again."""
    monkeypatch.setattr(td, "FALLBACK_S", 0.05)
    rt = await _rt(_Stt(deaf=True))
    try:
        voice = await td._voice(rt, [], _Tts())
        assert await voice.say("Sorry, let me correct that.")
        [t] = await _transcripts(rt, 1)
        assert t.source == "injected" and voice.lines[0].outcome == "text"
        line = voice.lines[0]
        await voice.stream.q.put(SttResult("Sorry, let me correct that.", True, line.start_ms + 50, line.end_ms))
        await asyncio.sleep(0.2)
        assert len(await rt.ctx.store.query(rt.path("transcripts"), Transcript)) == 1
        await voice.close()
    finally:
        await close_env(rt)


async def test_d322_a_final_from_another_line_does_not_stop_a_fallback(monkeypatch):
    monkeypatch.setattr(td, "FALLBACK_S", 0.3)
    rt = await _rt(_Stt())
    try:
        voice = await td._voice(rt, [], _Tts())
        assert await voice.say("First line (unheard).")
        assert await voice.say("Second line, heard.")
        found = await _transcripts(rt, 2)
        assert sorted((t.source, t.text) for t in found) == [("injected", "First line (unheard)."),
                                                              ("mic", "Second line, heard.")]
        assert [x.outcome for x in voice.lines] == ["text", "stt"]
        await voice.close()
    finally:
        await close_env(rt)


async def test_d322_slow_speech_goes_in_as_text(monkeypatch):
    monkeypatch.setattr(td, "SAY_TTS_S", 0.05)
    rt = await _rt(_Stt())
    try:
        voice = await td._voice(rt, [], _Tts(delay=0.5))
        assert not await voice.say("Hi")  # the caller injects it
        await voice.close()
    finally:
        await close_env(rt)


async def test_d322_an_early_end_stops_the_scene_and_its_voice():
    rt = await _rt(_Stt())
    try:
        drive = asyncio.create_task(td.play(rt, _Tts()))
        for _ in range(40):
            if rt.sid in td.voice_sessions:
                break
            await asyncio.sleep(0.05)
        assert rt.sid in td.voice_sessions  # the voice holds the session's speech-to-text
        await rt.end()  # the operator ends the show at once
        await asyncio.wait_for(drive, 3)
        assert rt.sid not in td.voice_sessions and rt.ctx.stt.streams[0].closed
    finally:
        await close_env(rt)


def test_d322_the_mic_waits_while_the_voice_holds_the_session():
    import json

    from fastapi.testclient import TestClient

    from app.main import create_app

    from .helpers import make_settings

    app = create_app(make_settings())
    app.state.ctx.stt = _Stt()
    with TestClient(app) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        td.voice_sessions.add(sid)
        try:
            with client.websocket_connect(f"/api/sessions/{sid}/audio") as ws:
                msg = json.loads(ws.receive_text())
            assert msg["state"] == "error" and "AI voice" in msg["message"]
        finally:
            td.voice_sessions.discard(sid)
