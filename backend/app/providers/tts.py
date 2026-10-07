"""Cloud Text-to-Speech for the judge test drive's host voice (D-320). One call per line text, cached on disk by the
hash of voice and text: 16 kHz mono 16-bit WAV, which the STT stream takes and the browser plays."""
from __future__ import annotations

import hashlib
import io
import re
import tempfile
import wave
from pathlib import Path

VOICE = "en-US-Chirp3-HD-Leda"  # a clear female voice; 5 lines in parallel took about 1.1 s (probe 10/7)
CACHE = Path(tempfile.gettempdir()) / "live-studio-tts"
KEY = re.compile(r"^[0-9a-f]{16}$")


def key_of(text: str) -> str:
    return hashlib.sha256(f"{VOICE}\n{text}".encode()).hexdigest()[:16]


def path_of(key: str) -> Path | None:
    """The cached WAV of a key, or None (also for anything that is not a key)."""
    p = CACHE / f"{key}.wav"
    return p if KEY.match(key) and p.is_file() else None


def pcm_of(wav_bytes: bytes) -> bytes:
    with wave.open(io.BytesIO(wav_bytes)) as w:
        return w.readframes(w.getnframes())


class Tts:
    def __init__(self) -> None:
        self._client = None

    async def wav(self, text: str) -> str:
        """The cache key of this text's WAV, made on the first call."""
        key = key_of(text)
        if path_of(key) is None:
            from google.cloud import texttospeech as tts

            if self._client is None:
                self._client = tts.TextToSpeechAsyncClient()
            r = await self._client.synthesize_speech(
                input=tts.SynthesisInput(text=text),
                voice=tts.VoiceSelectionParams(language_code="en-US", name=VOICE),
                audio_config=tts.AudioConfig(audio_encoding=tts.AudioEncoding.LINEAR16, sample_rate_hertz=16_000))
            CACHE.mkdir(parents=True, exist_ok=True)
            part = CACHE / f"{key}.part"
            part.write_bytes(r.audio_content)  # LINEAR16 comes with its WAV header
            part.replace(CACHE / f"{key}.wav")
        return key
