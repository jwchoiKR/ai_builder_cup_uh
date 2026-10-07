"""Judge test drive (D-238): a bundled fictional sample product is onboarded, approved with one click, and a short
scene plays on its show: a risky line and its spoken correction, a comment burst answered by AI with a citation, a
sensitive question the host answers aloud, a viewer's purchase for the AI PD. Built from the session's own catalog,
so nothing in it names a shipped product. Guarded by a rate cap.
D-320: the host's lines are spoken (Cloud TTS) into the session's speech-to-text stream, so the judge hears the host
and sees the real captions, alerts and latency; a line with no final falls back to text.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

SAMPLE_DIR = "onboarding_dev/p1_lumen_serum"  # fictional brand, every format incl. a label photo (D-216)
MAX_PER_HOUR = 6
_starts: list[float] = []
_running: set[str] = set()


class TestDriveBusy(Exception):
    pass


def allow_start(now: float | None = None) -> None:
    """At most MAX_PER_HOUR test drives per hour and one at a time per process (spend cap)."""
    now = now or time.time()
    _starts[:] = [t for t in _starts if now - t < 3600]
    if _running or len(_starts) >= MAX_PER_HOUR:
        raise TestDriveBusy("the test drive is busy; try again in a few minutes")
    _starts.append(now)


def sample_files(data_path: Path) -> list[tuple[str, bytes]]:
    folder = data_path / SAMPLE_DIR
    return [(p.name, p.read_bytes()) for p in sorted(folder.iterdir()) if p.is_file()]


def cache_key(files: list[tuple[str, bytes]]) -> str:
    return hashlib.sha256(b"".join(hashlib.sha256(b).digest() for _, b in files)).hexdigest()[:16]


def load_cached(root: Path, key: str) -> dict | None:
    path = root / "testdrive_cache" / f"{key}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def save_cached(root: Path, key: str, result: dict) -> None:
    folder = root / "testdrive_cache"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{key}.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    from ..onboarding.storage import persisted

    persisted(folder / f"{key}.json")  # D-263


def scene(rt) -> list[tuple[float, str, str, str]]:
    """(seconds from start, kind, author, text) for this session's product. Kinds: host, comment."""
    cat = rt.catalog
    p = cat.get_product(cat.order[0])
    word = p.name.split()[-1].lower() if p.name else "product"
    claim = (p.approved_claims[0] if p.approved_claims else "it feels light on the skin").rstrip(".*†")
    return [
        (0.0, "host", "Host", f"Hi everyone, welcome! Today we are looking at the {p.name}."),
        (5.0, "host", "Host", f"Honestly, this {word} erases wrinkles completely, guaranteed for everyone."),
        (12.0, "host", "Host", f"Sorry, let me correct that. {claim}."),
        (17.0, "comment", "Mei", "how much is it?"),
        (17.8, "comment", "Raj", "price pls"),
        (18.6, "comment", "Ana", "how much is this one?"),
        (21.0, "comment", "Siti", "can I use it while pregnant?"),
        (38.0, "host_answer", "Host", "Siti asked about pregnancy."),  # then the verified draft, read aloud
        (46.0, "comment", "Tom", "Just bought two, so excited!!"),
        (75.0, "end", "", ""),
    ]


FRAME_MS = 100  # as the browser mic sends
FRAME_BYTES = 16_000 * 2 * FRAME_MS // 1000
FALLBACK_S = 6.0  # no final this long after a line's audio ends: the line goes in as text
SYNTH_WAIT_S = 5.0  # the host lines' speech is made before the scene starts (about 1 s for five lines)


@dataclass
class _Line:
    key: str
    text: str
    pcm: bytes
    started: float = 0.0
    done: asyncio.Event = field(default_factory=asyncio.Event)


class Voice:
    """D-320: the host's lines as speech in the session's speech-to-text stream, paced as a mic is (100 ms frames,
    silence between lines), so their finals take the normal path to the judges. The browser plays each line's audio
    when its streaming starts (event `testdrive.audio`)."""

    def __init__(self, rt, tts, stream) -> None:
        self.rt, self.tts, self.stream = rt, tts, stream
        self.queue: asyncio.Queue[_Line] = asyncio.Queue()
        self.finals: list[float] = []  # when each final came (monotonic)
        self.closed = False
        self.tasks = [rt.spawn(self._pump(), name=f"testdrive-voice:{rt.sid}"),
                      rt.spawn(self._listen(), name=f"testdrive-stt:{rt.sid}")]

    async def say(self, text: str) -> bool:
        """Queues the line's speech; False when it cannot be made (the caller injects the text)."""
        from ..providers.tts import path_of, pcm_of

        try:
            key = await self.tts.wav(text)
            line = _Line(key, text, pcm_of(path_of(key).read_bytes()))
        except Exception as e:  # noqa: BLE001
            log.warning("testdrive tts failed (%s): %r", e, text[:80])
            return False
        self.queue.put_nowait(line)
        self.rt.spawn(self._watch(line), name=f"testdrive-watch:{self.rt.sid}")
        return True

    async def _pump(self) -> None:
        silence = b"\x00" * FRAME_BYTES
        frames: list[bytes] = []
        line: _Line | None = None
        due = time.monotonic()
        while not self.closed:
            if not frames and line is not None:
                line.done.set()
                line = None
            if not frames and not self.queue.empty():
                line = self.queue.get_nowait()
                frames = [line.pcm[i:i + FRAME_BYTES] for i in range(0, len(line.pcm), FRAME_BYTES)]
                line.started = time.monotonic()
                await self.rt.emit("testdrive.audio", {"url": f"/api/testdrive/audio/{line.key}.wav",
                                                       "text": line.text, "duration_ms": len(line.pcm) // 32})
            await self.stream.write(frames.pop(0) if frames else silence)
            due += FRAME_MS / 1000
            await asyncio.sleep(max(0.0, due - time.monotonic()))

    async def _listen(self) -> None:
        from .runtime import ActionError

        async for r in self.stream.results():
            if not r.is_final:
                continue
            self.finals.append(time.monotonic())
            try:
                t = await self.rt.utterances.submit(r.text, source="mic", speech_end_at=r.speech_end_at)
                log.info("testdrive stt final %s %s: %r", self.rt.sid, t.transcript_id, r.text[:100])
            except ActionError as e:  # the show ended
                log.info("testdrive stt final not judged (%s)", e.message)

    async def _watch(self, line: _Line) -> None:
        await line.done.wait()
        await asyncio.sleep(FALLBACK_S)
        if not self.closed and not any(t >= line.started for t in self.finals):
            log.info("testdrive stt fallback %s: %r", self.rt.sid, line.text[:80])
            await self.rt.inject_transcript(line.text, scenario="testdrive")

    async def close(self) -> None:
        self.closed = True
        await self.stream.close()
        for t in self.tasks:
            t.cancel()


async def _voice(rt, lines: list[str], tts=None) -> Voice | None:
    """The scene's voice, its host lines made first; None without speech-to-text (STT_PROVIDER=mock) or on failure."""
    from ..api.audio_ws import stream_setup
    from ..providers.tts import Tts

    stt = getattr(rt.ctx, "stt", None)
    if stt is None:
        return None
    tts = tts or Tts()
    jobs = [asyncio.ensure_future(tts.wav(x)) for x in lines]
    for j in jobs:
        j.add_done_callback(lambda f: f.cancelled() or f.exception())  # a failed line is retried when said
    if jobs:  # a line not made in time keeps going and is ready (or made) when said
        await asyncio.wait(jobs, timeout=SYNTH_WAIT_S)
    try:
        phrases, language = await stream_setup(rt.ctx, rt)
        return Voice(rt, tts, stt.open(phrases, language))
    except Exception as e:  # noqa: BLE001 - the scene plays as text
        log.warning("testdrive voice off for %s: %s", rt.sid, e)
        return None


async def play(rt, tts=None) -> None:
    """Runs the scene on the live session in real time, then ends it (the reset)."""
    from .comments import submit_comment

    _running.add(rt.sid)
    steps = scene(rt)
    voice = await _voice(rt, [text for _, kind, _, text in steps if kind == "host"], tts)
    t0 = time.monotonic()
    try:
        for at, kind, author, text in steps:
            wait = at - (time.monotonic() - t0)
            if wait > 0:
                await asyncio.sleep(wait)
            if kind == "host":
                if not (voice and await voice.say(text)):
                    await rt.inject_transcript(text, scenario="testdrive")
            elif kind == "host_answer":
                # the host answers the waiting question aloud with its verified draft, so the answer is posted
                draft = None
                for g in await rt.groups():
                    if g.route == "HOST" and g.answer_id and g.published_message_id is None:
                        a = await rt.get_answer(g.answer_id)
                        if a is not None and a.verified:
                            draft = a.text
                            break
                line = f"{text} {draft}" if draft else text
                if not (voice and await voice.say(line)):  # spoken as made at this moment
                    await rt.inject_transcript(line, scenario="testdrive")
            elif kind == "comment":
                await submit_comment(rt, author_id=f"td_{author.lower()}", author_name=author, text=text,
                                     source="script", scenario="testdrive")
            else:
                await rt.end()
    except Exception:  # noqa: BLE001 - a test drive never takes the service down
        log.exception("test drive %s stopped", rt.sid)
    finally:
        if voice is not None:
            await voice.close()
        _running.discard(rt.sid)
