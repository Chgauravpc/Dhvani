"""Real STT via Sarvam's hosted Saaras model -- phase-2b spec section A.

Hosted, so unlike `WhisperSTT` there is no local model and no GPU/CPU
device choice. VAD-gated and single-shot, exactly like `WhisperSTT`: audio
accumulates until the caller's iterator ends (`is_last=True`), then one API
call produces one final `Transcript`.

**Verified against the real installed `sarvamai` package (0.1.34), not
assumed from docs** -- phase-2b spec section A.1 has the full writeup;
the two facts that mattered most for correctness:

- **`mode`, not `model`, selects transcribe vs. translate.**
  `client.speech_to_text.transcribe(..., mode=...)` is the one call for
  both; `mode="transcribe"` returns text in the source language,
  `mode="translate"` returns English. F2's entity matching needs the
  source-language text, so `mode="transcribe"` is hardcoded here, never
  exposed as a constructor option -- there is no correct reason for a
  caller of this class to ask for the translating mode.
- **Failures raise `sarvamai.core.ApiError` (and subclasses) once a
  response comes back with a bad status, but a transport-level failure
  (connection refused, timeout) raises a plain `httpx.HTTPError` instead**
  -- confirmed by reading `speech_to_text/raw_client.py`: it only wraps
  the former, and never catches `httpx`'s own exceptions. Both are mapped
  to `ProviderError` here.
"""

from __future__ import annotations

import io
import os
import wave
from collections.abc import AsyncIterator

import httpx
from sarvamai import AsyncSarvamAI
from sarvamai.core import ApiError

from dhvani.clock import Clock
from dhvani.providers.base import ProviderError
from dhvani.telemetry.span import FINAL_TRANSCRIPT, TurnTrace
from dhvani.types import AudioChunk, Stage, Transcript

DEFAULT_MODEL = "saaras:v3"


def _encode_wav(pcm: bytes, sample_rate: int) -> bytes:
    """16-bit mono PCM -> WAV bytes via the stdlib `wave` module -- no new
    dependency needed, per phase-2b spec section A.2."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return buffer.getvalue()


class SarvamSTT:
    """Sarvam (Saaras) speech-to-text behind the Phase 0 `STTProvider`
    protocol, unchanged -- a drop-in for `WhisperSTT` wherever a
    `STTProvider` is expected."""

    name = "sarvam"

    def __init__(
        self,
        model: str,
        clock: Clock,
        api_key: str | None = None,
        language_code: str | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        key = api_key if api_key is not None else os.environ.get("SARVAM_API_KEY")
        if not key:
            raise ProviderError("SARVAM_API_KEY is not set and no api_key was passed")
        self._client = AsyncSarvamAI(api_subscription_key=key, timeout=timeout_s)
        self._model = model
        self._language_code = language_code
        self._clock = clock

    async def stream(
        self, audio: AsyncIterator[AudioChunk], *, trace: TurnTrace
    ) -> AsyncIterator[Transcript]:
        async with trace.aspan(Stage.STT, self.name):
            pcm_parts: list[bytes] = []
            sample_rate = 16000
            async for chunk in audio:
                pcm_parts.append(chunk.pcm)
                sample_rate = chunk.sample_rate

            pcm = b"".join(pcm_parts)
            if not pcm:
                trace.mark(FINAL_TRANSCRIPT)
                yield Transcript(text="", is_final=True)
                return

            wav_bytes = _encode_wav(pcm, sample_rate)
            try:
                response = await self._client.speech_to_text.transcribe(
                    file=("audio.wav", wav_bytes, "audio/wav"),
                    model=self._model,
                    mode="transcribe",
                    language_code=self._language_code,
                )
            except (ApiError, httpx.HTTPError) as exc:
                raise ProviderError(f"Sarvam speech-to-text request failed: {exc}") from exc

            trace.mark(FINAL_TRANSCRIPT)
            yield Transcript(
                text=response.transcript,
                is_final=True,
                language=response.language_code,
            )
