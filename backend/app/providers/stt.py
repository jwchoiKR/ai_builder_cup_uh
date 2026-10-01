"""Speech-to-Text (DEV_SPEC §10, verified in docs/VERIFIED.md item 4).

`GoogleV2Stt` streams 16 kHz mono LINEAR16 to Speech-to-Text V2 (`chirp_3`, regional endpoint),
restarts the stream before the 5-minute limit and re-sends the audio after the last final result
("bridging"), and turns each final result's end offset into a server timestamp: the arrival time
of the audio at that offset. chirp_3 returns no interim results (VERIFIED §4.10).
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from ..clock import Clock
from ..config import Settings

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
BYTES_PER_MS = SAMPLE_RATE * 2 // 1000  # 16-bit mono
STREAM_LIMIT_MS = 240_000  # hard restart, well before the 5-minute stream limit
SOFT_RESTART_MS = 180_000  # after this, restart right after the next final result (a natural pause)
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
    def __init__(self, stt: "GoogleV2Stt", phrases: list[str]) -> None:
        self._stt = stt
        self._phrases = phrases
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
        bridge: list[_Chunk] = []
        errors = 0
        try:
            while not self._closed or bridge:
                state = _StreamState()
                ended = await self._one_stream(state, bridge)
                if ended == "closed":
                    break
                if ended == "error":
                    errors += 1
                    if errors > 5:
                        raise RuntimeError("speech stream failed repeatedly")
                    await asyncio.sleep(min(2.0, 0.2 * errors))
                else:
                    errors = 0
                self.restarts += 1
                bridge = state.tail_after(state.last_final_ms)
        except Exception as e:  # noqa: BLE001 - surfaced to the consumer
            log.exception("speech stream stopped")
            await self._results.put(e)
        finally:
            await self._results.put(None)

    async def _one_stream(self, state: _StreamState, bridge: list[_Chunk]) -> str:
        """Run one StreamingRecognize call. Returns 'closed', 'limit' or 'error'."""
        from google.api_core import exceptions as gexc

        cs = self._stt.types
        reason = {"value": "closed"}

        async def requests():
            yield self._stt.first_request(self._phrases)
            for c in bridge:  # re-send audio after the previous stream's last final result
                state.add(c.data, c.arrival_ms)
                yield cs.StreamingRecognizeRequest(audio=c.data)
            while True:
                if state.audio_ms >= STREAM_LIMIT_MS or (
                        state.audio_ms >= SOFT_RESTART_MS and state.last_final_ms >= SOFT_RESTART_MS):
                    reason["value"] = "limit"
                    return
                item = await self._audio.get()
                if item is None:
                    reason["value"] = "closed"
                    return
                data, arrival = item
                for i in range(0, len(data), MAX_CHUNK_BYTES):
                    part = data[i:i + MAX_CHUNK_BYTES]
                    state.add(part, arrival)
                    yield cs.StreamingRecognizeRequest(audio=part)

        try:
            responses = await self._stt.client().streaming_recognize(requests=requests())
            async for resp in responses:
                for r in resp.results:
                    alt = r.alternatives[0].transcript.strip() if r.alternatives else ""
                    end_ms = r.result_end_offset.total_seconds() * 1000 if r.result_end_offset else None
                    if r.is_final:
                        if end_ms is not None:
                            state.last_final_ms = end_ms
                        if alt:
                            await self._results.put(SttResult(alt, True, state.time_at(end_ms) if end_ms is not None else None,
                                                              self._stt.clock.now_ms()))
                    elif alt:
                        await self._results.put(SttResult(alt, False, None, self._stt.clock.now_ms()))
        except (gexc.GoogleAPICallError, gexc.RetryError) as e:
            log.warning("speech stream error (%s), restarting", e)
            return "error"
        return reason["value"]


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

    def first_request(self, phrases: list[str]):
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
            language_codes=[s.STT_LANGUAGE], model=s.STT_MODEL,
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

    def open(self, phrases: list[str]) -> GoogleV2Stream:
        return GoogleV2Stream(self, phrases)


def make_stt(settings: Settings, clock: Clock) -> GoogleV2Stt | None:
    """None for STT_PROVIDER=mock: audio is disabled, transcripts come from injection (§10.4)."""
    return GoogleV2Stt(settings, clock) if settings.STT_PROVIDER == "google_v2" else None
