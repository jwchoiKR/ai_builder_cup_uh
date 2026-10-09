"""D-339 (review H13/H14): a speech stream that heard speech, then a pause, and returned no final within STALL_MS
(COLD_STALL_MS before its first result) is restarted with its unfinalized audio re-sent, and the mic is told
"reconnecting"; a late but working stream is not restarted. When the show ends, the mic's stream is closed."""
from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from types import SimpleNamespace

from app.providers import stt as stt_mod
from app.providers.stt import GoogleV2Stream, SttStatus

SPEECH = b"\x00\x10" * 1600  # 100 ms, loud
SILENCE = b"\x00\x00" * 1600  # 100 ms


class Clock:
    def __init__(self):
        self.t = 0

    def now_ms(self):
        return self.t


class FakeSpeech:
    """Per stream (in opening order) a mode: "normal" gives a final "w<n>" for each second of its audio at that
    second's end; "dead_after:<ms>" does the same until that much audio, then never answers again; "late:<ms>" gives
    each final that much audio later."""

    def __init__(self, modes):
        self.modes, self.streams = list(modes), 0

    async def streaming_recognize(self, requests):
        mode = self.modes[min(self.streams, len(self.modes) - 1)]
        self.streams += 1
        out: asyncio.Queue = asyncio.Queue()
        kind, _, arg = mode.partition(":")
        limit = float(arg) if kind in ("dead_after", "hold_after") else float("inf")
        lag = float(arg) if kind == "late" else 0.0

        def final(n):
            return SimpleNamespace(results=[SimpleNamespace(
                is_final=True, alternatives=[SimpleNamespace(transcript=f"w{n}")],
                result_end_offset=timedelta(milliseconds=n * 1000))])

        async def pump():
            audio_ms, n = 0.0, 0
            async for req in requests:
                if getattr(req, "audio", None):
                    audio_ms += len(req.audio) / 32
                    while (n + 1) * 1000 <= min(audio_ms - lag, limit):
                        n += 1
                        await out.put(final(n))
            if kind == "hold_after":  # the held finals come in one late burst when the stream is closed
                while (n + 1) * 1000 <= audio_ms:
                    n += 1
                    await out.put(final(n))
            await out.put(None)
        asyncio.create_task(pump())

        async def responses():
            while (item := await out.get()) is not None:
                yield item
        return responses()


class FakeStt:
    def __init__(self, modes):
        self.clock = Clock()
        self.speech = FakeSpeech(modes)
        self.types = SimpleNamespace(StreamingRecognizeRequest=lambda audio=None, **_: SimpleNamespace(audio=audio))

    def client(self):
        return self.speech

    def first_request(self, phrases, language=None):
        return SimpleNamespace(audio=None)


async def _run(modes, frames):
    fake = FakeStt(modes)
    stream = GoogleV2Stream(fake, [])
    got: list = []

    async def read():
        async for r in stream.results():
            got.append(r)
    reader = asyncio.create_task(read())
    for f in frames:
        fake.clock.t += 100
        await stream.write(f)
        await asyncio.sleep(0)
    await asyncio.sleep(0.05)
    await stream.close()
    await reader
    return stream, fake, got


def _speech_then_pause(speech_ms: int, pause_ms: int) -> list[bytes]:
    return [SPEECH] * (speech_ms // 100) + [SILENCE] * (pause_ms // 100)


async def test_d339_a_stream_that_stops_answering_is_restarted_and_its_speech_re_sent(caplog):
    caplog.set_level("INFO", logger="app.providers.stt")
    stream, fake, got = await _run(["dead_after:1000", "normal"], _speech_then_pause(3000, 7000))
    assert stream.restarts == 1 and fake.speech.streams == 2
    assert [g.state for g in got if isinstance(g, SttStatus)][:1] == ["reconnecting"]
    finals = [g.text for g in got if not isinstance(g, SttStatus) and g.is_final]
    assert finals[0] == "w1" and len(finals) > 1  # the new stream re-heard the unfinalized speech
    assert any("restart #1 (stall)" in r.getMessage() for r in caplog.records)
    assert any("stt lane" in r.getMessage() and "bytes in" in r.getMessage() for r in caplog.records)


async def test_d339_a_late_but_working_stream_is_not_restarted():
    stream, fake, got = await _run(["late:3000"], _speech_then_pause(3000, 7000))
    assert stream.restarts == 0 and fake.speech.streams == 1
    assert not any(isinstance(g, SttStatus) for g in got)


async def test_d339_a_stream_silent_from_its_cold_start_is_restarted_once():
    frames = _speech_then_pause(2000, 9000) + [SILENCE] * 120  # a long pause after: no second stall restart
    stream, fake, got = await _run(["dead_after:0", "dead_after:0"], frames)
    assert stream.restarts == 1 and fake.speech.streams == 2  # cold limit; the stall lane waits for its first result


async def test_d339_late_finals_of_the_old_stream_are_not_reported_twice():
    """The old stream holds its finals and delivers them in a burst when the stall restart closes it; the new stream
    re-hears the same audio. Each stretch of audio is reported once."""
    stream, fake, got = await _run(["hold_after:1000", "normal"], _speech_then_pause(3000, 7000) + [SILENCE] * 30)
    assert stream.restarts == 1
    ends = [g.speech_end_at for g in got if not isinstance(g, SttStatus) and g.is_final]
    assert ends == sorted(ends) and len(set(ends)) == len(ends)  # in order, none twice


async def test_d339_late_audio_from_the_mic_shows_the_chip_without_a_restart():
    fake = FakeStt(["dead_after:1000"])
    stream = GoogleV2Stream(fake, [])
    stream.client_late_ms = 5_000  # the mic's marks say its audio arrives 5 s late
    got: list = []

    async def read():
        async for r in stream.results():
            got.append(r)
    reader = asyncio.create_task(read())
    for f in _speech_then_pause(3000, 9000):
        fake.clock.t += 100
        await stream.write(f)
        await asyncio.sleep(0)
    await asyncio.sleep(0.05)
    await stream.close()
    await reader
    assert stream.restarts == 0
    assert [g.state for g in got if isinstance(g, SttStatus)] == ["reconnecting"]  # once, no loop
