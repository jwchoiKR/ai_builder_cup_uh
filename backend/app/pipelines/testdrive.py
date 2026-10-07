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
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

SAMPLE_DIR = "onboarding_dev/p1_lumen_serum"  # fictional brand, every format incl. a label photo (D-216)
MAX_PER_HOUR = 6
ADMIT_S = 900  # D-322: an admitted start must reach /go within this long
_starts: list[float] = []
_admitted: dict[str, float] = {}  # job id -> when /start admitted it
_running: set[str] = set()  # the job ids of drives playing now


class TestDriveBusy(Exception):
    pass


def allow_start(now: float | None = None) -> None:
    """At most MAX_PER_HOUR test drives per hour and one at a time per process (spend cap). D-322: one at a time
    counts a start admitted and not yet played, too."""
    now = now or time.time()
    _starts[:] = [t for t in _starts if now - t < 3600]
    for job_id, at in list(_admitted.items()):
        if now - at > ADMIT_S:
            del _admitted[job_id]
    if _running or _admitted or len(_starts) >= MAX_PER_HOUR:
        raise TestDriveBusy("the test drive is busy; try again in a few minutes")
    _starts.append(now)


def admit(job_id: str, now: float | None = None) -> None:
    _admitted[job_id] = now or time.time()


def claim(job_id: str) -> None:
    """D-322: /go plays only a job its /start admitted, once, and never next to another drive."""
    if _running or _admitted.pop(job_id, None) is None:
        raise TestDriveBusy("start the test drive first, or wait for the one playing")
    _running.add(job_id)


def finish(job_id: str) -> None:
    _running.discard(job_id)


def release(job_id: str) -> None:
    """D-323: a /go that failed before the show started gives the job its admission back, so it can be retried."""
    _running.discard(job_id)
    admit(job_id)


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
        (21.0, "comment", "Sarah", "can I use it while pregnant?"),
        (38.0, "host_answer", "Host", "Sarah asked about pregnancy."),  # then the verified draft, read aloud
        (46.0, "comment", "Tom", "Just bought two, so excited!!"),
        (75.0, "end", "", ""),
    ]


FRAME_MS = 100  # as the browser mic sends
FRAME_BYTES = 16_000 * 2 * FRAME_MS // 1000
FALLBACK_S = 6.0  # no final this long after a line's audio ends: the line goes in as text
SYNTH_WAIT_S = 5.0  # the host lines' speech is made before the scene starts (about 1 s for five lines)
SAY_TTS_S = 4.0  # a line whose speech is not ready this long after it is due goes in as text
LATE_MS = 1500  # a final whose speech ended this long after a line's audio still belongs to that line
SPAN_WORDS = 0.6  # D-323: a final holding this share of an earlier line's words also covers that line
voice_sessions: set[str] = set()  # sessions whose speech-to-text the test drive's voice holds (the mic waits)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


@dataclass
class _Line:
    key: str
    text: str
    pcm: bytes
    start_ms: int = 0  # server time its audio started and ended streaming
    end_ms: int = 0
    outcome: str = "pending"  # then "stt" (its finals) or "text" (the fallback): never both
    done: asyncio.Event = field(default_factory=asyncio.Event)


class Voice:
    """D-320: the host's lines as speech in the session's speech-to-text stream, paced as a mic is (100 ms frames,
    silence between lines), so their finals take the normal path to the judges. The browser plays each line's audio
    when its streaming starts (event `testdrive.audio`). D-322: a final goes to the line whose audio it came from, and
    each line has one outcome, its finals or the text fallback; the voice holds the session's speech-to-text."""

    def __init__(self, rt, tts, stream) -> None:
        self.rt, self.tts, self.stream = rt, tts, stream
        self.queue: asyncio.Queue[_Line] = asyncio.Queue()
        self.lines: list[_Line] = []
        self.closed = False
        self.stop = asyncio.Event()  # D-323: set when the show ends, so a line waiting for its speech gives up
        voice_sessions.add(rt.sid)
        self.tasks: set[asyncio.Task] = set()
        for coro, name in ((self._pump(), "testdrive-voice"), (self._listen(), "testdrive-stt"),
                           (self._watch_end(), "testdrive-end")):
            self._own(coro, name)

    def warm(self, lines: list[str]) -> list[asyncio.Task]:
        """D-323: the scene's lines made ahead, as tasks the voice owns (cancelled when it closes)."""
        async def one(text: str) -> None:
            try:
                await self.tts.wav(text)
            except Exception as e:  # noqa: BLE001 - made again when the line is said
                log.warning("testdrive tts warm-up failed (%s): %r", type(e).__name__, text[:80])

        return [self._own(one(x), "testdrive-tts") for x in lines]

    async def say(self, text: str) -> bool:
        """Queues the line's speech; False when it cannot be made in time or the show ended (the caller injects the
        text)."""
        from ..providers.tts import path_of, pcm_of

        made = self._own(self.tts.wav(text), "testdrive-tts")
        stop = asyncio.ensure_future(self.stop.wait())
        try:
            await asyncio.wait({made, stop}, timeout=SAY_TTS_S, return_when=asyncio.FIRST_COMPLETED)
        finally:
            stop.cancel()
        if not made.done():
            made.cancel()
            log.warning("testdrive tts failed (%s): %r", "show ended" if self.stop.is_set() else "timeout", text[:80])
            return False
        try:
            key = made.result()
            line = _Line(key, text, pcm_of(path_of(key).read_bytes()))
        except Exception as e:  # noqa: BLE001
            log.warning("testdrive tts failed (%s): %r", type(e).__name__, text[:80])
            return False
        self.lines.append(line)
        self.queue.put_nowait(line)
        self._own(self._watch(line), "testdrive-watch")
        return True

    def _own(self, coro, name: str) -> asyncio.Task:
        task = self.rt.spawn(coro, name=f"{name}:{self.rt.sid}")
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def _watch_end(self) -> None:
        while not await _ended(self.rt):
            await asyncio.sleep(0.25)
        self.stop.set()

    async def _pump(self) -> None:
        silence = b"\x00" * FRAME_BYTES
        frames: list[bytes] = []
        line: _Line | None = None
        due = time.monotonic()
        while not self.closed:
            if not frames and line is not None:
                line.end_ms = self.rt.now()
                line.done.set()
                line = None
            if not frames and not self.queue.empty():
                line = self.queue.get_nowait()
                frames = [line.pcm[i:i + FRAME_BYTES] for i in range(0, len(line.pcm), FRAME_BYTES)]
                line.start_ms = self.rt.now()
                await self.rt.emit("testdrive.audio", {"url": f"/api/testdrive/audio/{line.key}.wav",
                                                       "text": line.text, "duration_ms": len(line.pcm) // 32})
            await self.stream.write(frames.pop(0) if frames else silence)
            due += FRAME_MS / 1000
            await asyncio.sleep(max(0.0, due - time.monotonic()))

    def _lines_of(self, speech_end_at: int | None, text: str) -> list[_Line]:
        """The lines this final's speech came from. Its last line: it started before the speech ended (one frame of
        grace: a frame is stamped at the end of its audio, D-323) and the speech ended before its audio did (plus
        LATE_MS); without a time, the last line that started. D-323: a final that also holds the words of the lines
        just before it ("A B" heard as one) covers those too, so none of them falls back to text and is judged
        twice."""
        started = [x for x in self.lines if x.start_ms]
        if speech_end_at is None:
            last = started[-1] if started else None
        else:
            last = next((x for x in reversed(started) if x.start_ms - FRAME_MS <= speech_end_at
                         and (not x.end_ms or speech_end_at <= x.end_ms + LATE_MS)), None)
        if last is None:
            return []
        heard = set(_words(text))
        out = [last]
        for x in reversed(started[:started.index(last)]):
            words = _words(x.text)
            if x.outcome == "text" or not words or sum(w in heard for w in words) / len(words) < SPAN_WORDS:
                break
            out.insert(0, x)
        return out

    async def _listen(self) -> None:
        from .runtime import ActionError

        async for r in self.stream.results():
            if not r.is_final:
                continue
            lines = self._lines_of(r.speech_end_at, r.text)
            if not lines or lines[-1].outcome == "text":
                log.info("testdrive stt final dropped %s (%s): %r", self.rt.sid,
                         "its line went in as text" if lines else "no line", r.text[:80])
                continue
            for line in lines:
                line.outcome = "stt"
            try:
                t = await self.rt.utterances.submit(r.text, source="mic", speech_end_at=r.speech_end_at)
                log.info("testdrive stt final %s %s: %r", self.rt.sid, t.transcript_id, r.text[:100])
            except ActionError as e:  # the show ended
                log.info("testdrive stt final not judged (%s)", e.message)

    async def _watch(self, line: _Line) -> None:
        await line.done.wait()
        await asyncio.sleep(FALLBACK_S)
        if line.outcome == "pending" and not self.closed:
            line.outcome = "text"  # before the await: a final arriving now is dropped
            log.info("testdrive stt fallback %s: %r", self.rt.sid, line.text[:80])
            await self.rt.inject_transcript(line.text, scenario="testdrive")

    async def close(self) -> None:
        """Stops the voice: every task it owns is cancelled and awaited, the stream closed, the mic free again."""
        self.closed = True
        voice_sessions.discard(self.rt.sid)
        tasks = list(self.tasks)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.stream.close()


async def _voice(rt, lines: list[str], tts=None) -> Voice | None:
    """The scene's voice, its host lines made first; None without speech-to-text (STT_PROVIDER=mock) or on failure."""
    from ..api.audio_ws import stream_setup
    from ..providers.tts import Tts

    stt = getattr(rt.ctx, "stt", None)
    if stt is None:
        return None
    voice_sessions.add(rt.sid)  # D-323: held from the drive's start, so a mic cannot slip in during the warm-up
    try:
        phrases, language = await stream_setup(rt.ctx, rt)
        voice = Voice(rt, tts or Tts(), stt.open(phrases, language))
    except Exception as e:  # noqa: BLE001 - the scene plays as text
        voice_sessions.discard(rt.sid)
        log.warning("testdrive voice off for %s: %s", rt.sid, e)
        return None
    if jobs := voice.warm(lines):  # a line not made in time keeps going and is ready (or made) when said
        await asyncio.wait(jobs, timeout=SYNTH_WAIT_S)
    return voice


async def _ended(rt) -> bool:
    return (await rt.load_session()).status == "ended"


async def play(rt, tts=None) -> None:
    """Runs the scene on the live session in real time, then ends it (the reset). D-322: a show ended early (by the
    operator) stops the scene and its voice at once."""
    from .comments import submit_comment

    steps = scene(rt)
    voice = await _voice(rt, [text for _, kind, _, text in steps if kind == "host"], tts)
    t0 = time.monotonic()
    try:
        for at, kind, author, text in steps:
            while (wait := at - (time.monotonic() - t0)) > 0:
                if await _ended(rt):
                    return
                await asyncio.sleep(min(wait, 1.0))
            if await _ended(rt):
                return
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
