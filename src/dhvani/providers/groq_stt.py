"""Hosted Whisper `large-v3` on Groq behind the `STTProvider` protocol (3B-20).

The reference arm for the F2/digit measurements: an open-weights multilingual
ASR much larger than the local `small`, with the **language forced** (`en` for
Svarah, `hi` for IndicVoices) so it cannot drift into another script. Like
`SarvamSTT` it is single-shot: audio accumulates until the iterator ends, then
one request produces one final `Transcript`. Temperature is fixed at 0.

Groq's free tier limits audio seconds per hour and per day as well as requests;
a 429 is retried after its `Retry-After` (up to `MAX_WAIT_S`), and the transcript
log makes a stopped run resumable, so nothing is ever scored from a failed call.
"""

from __future__ import annotations

import asyncio
import io
import os
import wave
from collections.abc import AsyncIterator

import groq

from dhvani.clock import Clock
from dhvani.providers.base import ProviderError
from dhvani.telemetry.span import FINAL_TRANSCRIPT, TurnTrace
from dhvani.types import AudioChunk, Stage, Transcript

DEFAULT_MODEL = "whisper-large-v3"
MAX_WAIT_S = 3700.0
MAX_TRIES = 8


def _encode_wav(pcm: bytes, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return buffer.getvalue()


class GroqSTT:
    name = "groq-whisper"

    def __init__(
        self,
        clock: Clock,
        *,
        language: str,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        key = api_key if api_key is not None else os.environ.get("GROQ_API_KEY")
        if not key:
            raise ProviderError("GROQ_API_KEY is not set and no api_key was passed")
        self._client = groq.AsyncGroq(api_key=key, timeout=timeout_s)
        self._model = model
        self._language = language
        self._clock = clock

    async def stream(
        self, audio: AsyncIterator[AudioChunk], *, trace: TurnTrace
    ) -> AsyncIterator[Transcript]:
        async with trace.aspan(Stage.STT, self.name):
            parts: list[bytes] = []
            sample_rate = 16000
            async for chunk in audio:
                parts.append(chunk.pcm)
                sample_rate = chunk.sample_rate
            pcm = b"".join(parts)
            if not pcm:
                trace.mark(FINAL_TRANSCRIPT)
                yield Transcript(text="", is_final=True)
                return
            wav = _encode_wav(pcm, sample_rate)
            text = await self._transcribe(wav)
            trace.mark(FINAL_TRANSCRIPT)
            yield Transcript(text=text, is_final=True, language=self._language)

    async def _transcribe(self, wav: bytes) -> str:
        last = ""
        for attempt in range(MAX_TRIES):
            try:
                response = await self._client.audio.transcriptions.create(
                    file=("audio.wav", wav),
                    model=self._model,
                    language=self._language,
                    response_format="json",
                    temperature=0.0,
                )
                return str(response.text)
            except groq.APIStatusError as exc:
                status = exc.status_code
                if status in (408, 429) or status >= 500:
                    last = f"HTTP {status}"
                    raw = exc.response.headers.get("retry-after")
                    wait = float(raw) if raw and raw.replace(".", "", 1).isdigit() else None
                    if wait is not None and wait > MAX_WAIT_S:
                        raise ProviderError(f"Groq asked to wait {wait:.0f}s: {exc}") from exc
                    await asyncio.sleep(wait if wait is not None else min(60.0, 2.0 * 2**attempt))
                    continue
                raise ProviderError(f"Groq speech-to-text request failed: {exc}") from exc
            except groq.APIConnectionError:
                last = "connection"
                await asyncio.sleep(min(60.0, 2.0 * 2**attempt))
        raise ProviderError(f"Groq speech-to-text gave up after {MAX_TRIES} tries ({last})")
