"""D-145: the warm standby stream takes over at a final after SOFT_RESTART_MS, without lost or repeated words."""
from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace

from app.providers import stt as stt_mod
from app.providers.stt import GoogleV2Stream

FRAME = b"\x00\x10" * 1600  # 100 ms of 16-bit audio, loud enough to count as speech
WORD_MS = 1000  # the fake recognizer says one numbered word per second of audio, final at its end


class Clock:
    def __init__(self):
        self.t = 0

    def now_ms(self):
        return self.t


class FakeSpeech:
    """streaming_recognize: a final "w<n>" for each second of the stream's own audio (offsets per stream)."""

    def __init__(self):
        self.streams = 0

    async def streaming_recognize(self, requests):
        self.streams += 1
        out: asyncio.Queue = asyncio.Queue()

        async def pump():
            audio_ms = 0.0
            async for req in requests:
                if getattr(req, "audio", None):
                    audio_ms += len(req.audio) / 32
                    while audio_ms >= (pump.n + 1) * WORD_MS:
                        pump.n += 1
                        await out.put(SimpleNamespace(results=[SimpleNamespace(
                            is_final=True, alternatives=[SimpleNamespace(transcript=f"w{pump.n}")],
                            result_end_offset=timedelta(milliseconds=pump.n * WORD_MS))]))
            await out.put(None)
        pump.n = 0
        asyncio.create_task(pump())

        async def responses():
            while (item := await out.get()) is not None:
                yield item
        return responses()


class FakeStt:
    def __init__(self):
        self.clock = Clock()
        self.speech = FakeSpeech()
        self.types = SimpleNamespace(StreamingRecognizeRequest=lambda audio=None, **_: SimpleNamespace(audio=audio))

    def client(self):
        return self.speech

    def first_request(self, phrases, language=None):
        return SimpleNamespace(audio=None)


async def test_the_standby_takes_over_without_lost_or_repeated_words(monkeypatch):
    monkeypatch.setattr(stt_mod, "PREWARM_MS", 3_000)
    monkeypatch.setattr(stt_mod, "SOFT_RESTART_MS", 5_000)
    monkeypatch.setattr(stt_mod, "STREAM_LIMIT_MS", 9_000)
    fake = FakeStt()
    stream = GoogleV2Stream(fake, [])
    finals: list[tuple[str, int]] = []

    async def read():
        async for r in stream.results():
            if r.is_final:
                finals.append((r.text, r.speech_end_at))
    reader = asyncio.create_task(read())
    for _ in range(120):  # 12 s of audio
        fake.clock.t += 100
        await stream.write(FRAME)
        await asyncio.sleep(0)
    await asyncio.sleep(0.05)
    await stream.close()
    await reader
    assert fake.speech.streams >= 2 and stream.restarts >= 1
    ends = [at for _, at in finals]
    assert ends == sorted(ends) and len(set(ends)) == len(ends)  # no word twice, in order
    gaps = [b - a for a, b in zip(ends, ends[1:])]
    # the standby counts words from its own start, so its grid is shifted: no gap of a whole word or more
    assert max(gaps) < 2 * WORD_MS


async def test_without_a_standby_the_old_bridged_restart_still_works(monkeypatch):
    monkeypatch.setattr(stt_mod, "PREWARM_MS", 99_000)  # never ready
    monkeypatch.setattr(stt_mod, "SOFT_RESTART_MS", 5_000)
    monkeypatch.setattr(stt_mod, "STREAM_LIMIT_MS", 9_000)
    fake = FakeStt()
    stream = GoogleV2Stream(fake, [])
    texts: list[str] = []

    async def read():
        async for r in stream.results():
            texts.append(r.text)
    reader = asyncio.create_task(read())
    for _ in range(80):
        fake.clock.t += 100
        await stream.write(FRAME)
        await asyncio.sleep(0)
    await asyncio.sleep(0.05)
    await stream.close()
    await reader
    assert fake.speech.streams >= 2 and stream.restarts >= 1 and len(texts) >= 6
