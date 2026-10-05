"""Speech-to-Text (DEV_SPEC §10, verified in docs/VERIFIED.md item 4).

`GoogleV2Stt` streams 16 kHz mono LINEAR16 to Speech-to-Text V2 (`chirp_3`, regional endpoint),
restarts the stream before the 5-minute limit (D-145: a warm standby stream takes over at a pause; else
the audio after the last final result is re-sent, "bridging"), and turns each final result's end offset
into a server timestamp: the arrival time of the audio at that offset. chirp_3 returns no interim results (VERIFIED §4.10).
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from ..clock import Clock
from ..config import Settings

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
BYTES_PER_MS = SAMPLE_RATE * 2 // 1000  # 16-bit mono
STREAM_LIMIT_MS = 240_000  # hard restart, well before the 5-minute stream limit
SOFT_RESTART_MS = 180_000  # after this, restart right after the next final result (a natural pause)
PREWARM_MS = 165_000  # D-145: open the standby stream this long into the live one
SWITCH_MARGIN_MS = 300  # standby results ending this close after the switch point are still the old stream's
SPEECH_PEAK = 1_000  # 16-bit peak above which a frame counts as speech (log only)
BRIDGE_MAX_MS = 5_000  # re-send at most this much unfinalized audio into the new stream
MAX_CHUNK_BYTES = 15_360  # smallest documented per-request audio limit
MAX_PHRASES = 500  # chirp_3 allows up to 1,000; fewer entries degrade less (VERIFIED §4.5)


@dataclass
class SttResult:
    text: str
    is_final: bool
    speech_end_at: int | None  # server time of the end of the speech, from the result end offset
    received_at: int


@dataclass
class _Chunk:
    offset_ms: float  # start of this chunk in the current stream's audio
    duration_ms: float
    arrival_ms: int  # server time the chunk arrived (end of its audio)
    data: bytes


@dataclass
class _StreamState:
    chunks: list[_Chunk] = field(default_factory=list)
    audio_ms: float = 0.0
    last_final_ms: float = 0.0  # end offset of the last final result

    def add(self, data: bytes, arrival_ms: int) -> None:
        dur = len(data) / BYTES_PER_MS
        self.chunks.append(_Chunk(self.audio_ms, dur, arrival_ms, data))
        self.audio_ms += dur

    def time_at(self, offset_ms: float) -> int | None:
        for c in self.chunks:
            if c.offset_ms <= offset_ms <= c.offset_ms + c.duration_ms:
                return int(c.arrival_ms - (c.offset_ms + c.duration_ms - offset_ms))
        return self.chunks[-1].arrival_ms if self.chunks else None

    def tail_after(self, offset_ms: float, max_ms: float = BRIDGE_MAX_MS) -> list[_Chunk]:
        """Audio after the last final result, capped to the most recent `max_ms` (D-071)."""
        start = max(offset_ms, self.audio_ms - max_ms)
        return [c for c in self.chunks if c.offset_ms + c.duration_ms > start]


def phrases_from_glossary(glossary: dict | None, limit: int = MAX_PHRASES) -> list[str]:
    """Terms and spoken forms of the confirmed glossary as phrase hints (§10.3)."""
    out: list[str] = []
    for t in (glossary or {}).get("terms", []):
        for p in [t.get("term", ""), *t.get("spoken_forms", [])]:
            p = p.strip()
            if p and len(p) <= 100 and p.lower() not in {x.lower() for x in out}:
                out.append(p)
    return out[:limit]


class GoogleV2Stream:
    def __init__(self, stt: "GoogleV2Stt", phrases: list[str], language: str | None = None) -> None:
        self._stt = stt
        self._phrases = phrases
        self._language = language
        self._audio: asyncio.Queue[tuple[bytes, int] | None] = asyncio.Queue()
        self._results: asyncio.Queue[SttResult | Exception | None] = asyncio.Queue()
        self._closed = False
        self.restarts = 0
        self._task = asyncio.create_task(self._run(), name="stt-stream")

    async def write(self, pcm: bytes) -> None:
        if not self._closed:
            await self._audio.put((pcm, self._stt.clock.now_ms()))

    async def close(self) -> None:
        if not self._closed:
            self._closed = True
            await self._audio.put(None)
        try:
            await asyncio.wait_for(self._task, timeout=5)
        except (TimeoutError, asyncio.CancelledError):
            self._task.cancel()

    async def results(self) -> AsyncIterator[SttResult]:
        while True:
            item = await self._results.get()
            if item is None:
                return
            if isinstance(item, Exception):
                raise item
            yield item

    async def _run(self) -> None:
        """D-145: one distributor feeds the live stream and, from PREWARM_MS, a warm standby stream. At the
        first final after SOFT_RESTART_MS (a pause) the standby takes over: its results up to that final's end
        are dropped (the old stream reported them) and the old stream is closed. No standby ready, a hard
        limit without a recent final, or a stream error: the old restart that re-sends the audio after the
        last final ("bridge")."""
        errors = 0
        cur = self._lane([], active=True)
        nxt: _Lane | None = None
        try:
            while True:
                item = await self._audio.get()
                if item is None:
                    for lane in (cur, nxt):
                        if lane is not None:
                            lane.feed.put_nowait(None)
                    await asyncio.gather(*(lane.task for lane in (cur, nxt) if lane is not None),
                                         return_exceptions=True)
                    break
                if cur.task.done():  # the live stream failed: restart it with the bridge
                    errors = errors + 1 if cur.task.result() == "error" else 0
                    if errors > 5:
                        raise RuntimeError("speech stream failed repeatedly")
                    if errors:
                        await asyncio.sleep(min(2.0, 0.2 * errors))  # audio waits in the queue meanwhile
                    cur = self._restart(cur, "error")
                for lane in (cur, nxt):
                    if lane is not None:
                        lane.feed.put_nowait(item)
                st = cur.state
                if nxt is not None and nxt.task.done():
                    nxt = None  # the standby failed; a new one opens below
                if nxt is None and st.audio_ms >= PREWARM_MS:
                    nxt = self._lane([], active=False)
                soft = st.audio_ms >= SOFT_RESTART_MS and st.last_final_ms >= SOFT_RESTART_MS
                if soft or st.audio_ms >= STREAM_LIMIT_MS:
                    switch_at = st.time_at(st.last_final_ms)
                    if (nxt is not None and soft and not nxt.results and st.audio_ms < STREAM_LIMIT_MS):
                        # D-160 (local show replay): a standby that has returned nothing yet took 4.5 s for its
                        # first result after taking over; the live stream goes on until the next final
                        if not nxt.waited:
                            nxt.waited = True
                            log.info("speech stream switch waits: the standby has returned no result after %.0f s",
                                     nxt.state.audio_ms / 1000)
                    elif nxt is not None and soft and switch_at is not None and nxt.started_at <= switch_at:
                        nxt.emit_after, nxt.active, nxt.activated = switch_at, True, time.monotonic()
                        cur.emit_before = switch_at  # its audio is cut here: a fragment it finalizes later is not reported
                        cur.feed.put_nowait(None)
                        self.restarts += 1
                        nxt.number = self.restarts
                        log.info("speech stream switch #%d to the warm stream after %.0f s of audio "
                                 "(standby had %.0f s, %d results)", self.restarts, st.audio_ms / 1000,
                                 nxt.state.audio_ms / 1000, nxt.results)
                        cur, nxt = nxt, None
                    else:
                        cur = self._restart(cur, "limit")
        except Exception as e:  # noqa: BLE001 - surfaced to the consumer
            log.exception("speech stream stopped")
            await self._results.put(e)
        finally:
            await self._results.put(None)

    def _lane(self, bridge: list[_Chunk], *, active: bool) -> "_Lane":
        lane = _Lane(active=active, started_at=self._stt.clock.now_ms())
        lane.task = asyncio.create_task(self._one_stream(lane, bridge), name="stt-lane")
        return lane

    def _restart(self, cur: "_Lane", why: str) -> "_Lane":
        """The old restart: close the stream, open a new one with the audio after its last final."""
        cur.feed.put_nowait(None)
        bridge = cur.state.tail_after(cur.state.last_final_ms)
        self.restarts += 1
        # proof-plan §2: every restart with its cause, so a slow final can be matched to it in the logs
        log.info("speech stream restart #%d (%s) after %.0f s of audio; re-sending %d ms",
                 self.restarts, why, cur.state.audio_ms / 1000, sum(c.duration_ms for c in bridge))
        lane = self._lane(bridge, active=True)
        lane.activated = time.monotonic()
        lane.number = self.restarts
        return lane

    async def _one_stream(self, lane: "_Lane", bridge: list[_Chunk]) -> str:
        """Run one StreamingRecognize call fed by `lane.feed`. Returns 'closed' or 'error'."""
        from google.api_core import exceptions as gexc

        cs = self._stt.types
        state = lane.state

        async def requests():
            yield self._stt.first_request(self._phrases, self._language)
            for c in bridge:  # re-send audio after the previous stream's last final result
                state.add(c.data, c.arrival_ms)
                yield cs.StreamingRecognizeRequest(audio=c.data)
            while True:
                item = await lane.feed.get()
                if item is None:
                    return
                data, arrival = item
                if lane.active and lane.first_speech is None and _is_speech(data):
                    lane.first_speech = time.monotonic()
                for i in range(0, len(data), MAX_CHUNK_BYTES):
                    part = data[i:i + MAX_CHUNK_BYTES]
                    state.add(part, arrival)
                    yield cs.StreamingRecognizeRequest(audio=part)

        try:
            responses = await self._stt.client().streaming_recognize(requests=requests())
            async for resp in responses:
                for r in resp.results:
                    lane.results += 1
                    alt = r.alternatives[0].transcript.strip() if r.alternatives else ""
                    end_ms = r.result_end_offset.total_seconds() * 1000 if r.result_end_offset else None
                    end_at = state.time_at(end_ms) if end_ms is not None else None
                    if r.is_final and end_ms is not None:
                        state.last_final_ms = end_ms
                    skip = ("standby" if not lane.active else "empty" if not alt
                            else "before switch" if lane.emit_after is not None and end_at is not None
                            and end_at <= lane.emit_after + SWITCH_MARGIN_MS
                            else "after switch" if lane.emit_before is not None
                            and (end_at is None or end_at > lane.emit_before) else "")
                    if r.is_final:
                        log.debug("stt lane %s final end_at=%s emit_after=%s %s: %s", id(lane) % 1000, end_at,
                                  lane.emit_after, skip or "emitted", alt)
                    if skip:
                        continue  # a standby listens without reporting; earlier speech was the old stream's
                    if lane.activated is not None and not lane.reported:
                        lane.reported = True
                        speech = (f"; first speech audio {(lane.first_speech - lane.activated) * 1000:.0f} ms after"
                                  if lane.first_speech is not None else "")
                        log.info("speech stream #%d first result %.0f ms after it took over%s", self.restarts,
                                 (time.monotonic() - lane.activated) * 1000, speech)
                    if r.is_final:
                        now = self._stt.clock.now_ms()
                        if end_at is not None:  # D-157: a slow final, matched to its stream and a switch
                            log.info("stt final %d ms after speech end, stream #%d", now - end_at, lane.number)
                        await self._results.put(SttResult(alt, True, end_at, now))
                    else:
                        await self._results.put(SttResult(alt, False, None, self._stt.clock.now_ms()))
        except (gexc.GoogleAPICallError, gexc.RetryError) as e:
            log.warning("speech stream error (%s)", e)
            return "error"
        return "closed"


@dataclass(eq=False)
class _Lane:
    """One StreamingRecognize call: its audio feed, offsets, and whether it reports results (D-145)."""
    active: bool
    started_at: int  # server time its first audio arrives (about)
    feed: asyncio.Queue = field(default_factory=asyncio.Queue)
    state: _StreamState = field(default_factory=_StreamState)
    task: asyncio.Task | None = None
    emit_after: int | None = None  # results ending at or before this server time are the old stream's
    emit_before: int | None = None  # replaced: only results ending by this server time are still its own
    activated: float | None = None  # monotonic time it took over
    first_speech: float | None = None
    reported: bool = False
    number: int = 0  # D-157: restarts count when it took over, for the per-final log
    results: int = 0  # D-157: results it returned, also while standing by
    waited: bool = False  # D-160: a switch already waited for its first result (logged once)


def _is_speech(pcm: bytes) -> bool:
    """A frame louder than background noise (16-bit samples), for the takeover log only."""
    samples = memoryview(pcm).cast("h") if len(pcm) % 2 == 0 else memoryview(pcm[:-1]).cast("h")
    return max((abs(x) for x in samples), default=0) > SPEECH_PEAK


class GoogleV2Stt:
    name = "google_v2"

    def __init__(self, settings: Settings, clock: Clock) -> None:
        self.settings = settings
        self.clock = clock
        self._client = None
        from google.cloud.speech_v2.types import cloud_speech

        self.types = cloud_speech

    def client(self):
        if self._client is None:
            from google.api_core.client_options import ClientOptions
            from google.cloud import speech_v2

            endpoint = f"{self.settings.STT_LOCATION}-speech.googleapis.com"
            self._client = speech_v2.SpeechAsyncClient(client_options=ClientOptions(api_endpoint=endpoint))
        return self._client

    def first_request(self, phrases: list[str], language: str | None = None):
        cs = self.types
        s = self.settings
        adaptation = None
        if phrases and s.STT_PHRASE_HINTS_ENABLED:
            adaptation = cs.SpeechAdaptation(phrase_sets=[cs.SpeechAdaptation.AdaptationPhraseSet(
                inline_phrase_set=cs.PhraseSet(phrases=[{"value": p} for p in phrases]))])
        config = cs.RecognitionConfig(
            explicit_decoding_config=cs.ExplicitDecodingConfig(
                encoding=cs.ExplicitDecodingConfig.AudioEncoding.LINEAR16, sample_rate_hertz=SAMPLE_RATE,
                audio_channel_count=1),
            # D-142: STT_LANGUAGE overrides; else the session pack's chirp_3 code
            language_codes=[s.STT_LANGUAGE or language or "en-US"], model=s.STT_MODEL,
            features=cs.RecognitionFeatures(enable_automatic_punctuation=True),
            adaptation=adaptation,
        )
        features = cs.StreamingRecognitionFeatures(
            interim_results=True,
            endpointing_sensitivity=cs.StreamingRecognitionFeatures.EndpointingSensitivity.ENDPOINTING_SENSITIVITY_SHORT,
        )
        return cs.StreamingRecognizeRequest(
            recognizer=f"projects/{s.GCP_PROJECT}/locations/{s.STT_LOCATION}/recognizers/_",
            streaming_config=cs.StreamingRecognitionConfig(config=config, streaming_features=features),
        )

    def open(self, phrases: list[str], language: str | None = None) -> GoogleV2Stream:
        return GoogleV2Stream(self, phrases, language)


def make_stt(settings: Settings, clock: Clock) -> GoogleV2Stt | None:
    """None for STT_PROVIDER=mock: audio is disabled, transcripts come from injection (§10.4)."""
    return GoogleV2Stt(settings, clock) if settings.STT_PROVIDER == "google_v2" else None
