"""Sarvam realtime streaming STT behind the `STTProvider` protocol (3B-9).

Streams 8 kHz mu-law to Sarvam's realtime WebSocket (`speech_to_text_realtime_streaming`)
while the caller is still talking, with **server-side VAD endpointing**. The first
`transcript.final` is the turn's transcript. The provider records every server event with a
monotonic timestamp in `events` (reset per call) so a harness can split the endpoint wait
from the transcription wait: `vad.speech_end` is when Sarvam decided the user stopped, and
`transcript.final` when the text arrived.

Verified on the live endpoint (`results/preflight_3b-9.json`): the server resolves the model
to `saaras:v4`; `mulaw` at `sample_rate=8000` is accepted; events are `session.begin`,
`vad.speech_start`, `transcript.partial`, `vad.speech_end`, `transcript.final`. The SDK's
`send_realtime_audio_input` needs a model (`RealtimeAudioInput`), not a dict.
"""

from __future__ import annotations

import asyncio
import base64
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx
from sarvamai import AsyncSarvamAI
from sarvamai.core import ApiError
from sarvamai.types.realtime_audio_input import RealtimeAudioInput

from dhvani.audio import mulaw
from dhvani.clock import Clock
from dhvani.providers.base import ProviderError
from dhvani.telemetry.span import FINAL_TRANSCRIPT, TurnTrace
from dhvani.types import AudioChunk, Stage, Transcript

SAMPLE_RATE_HZ = 8_000


class SarvamRealtimeSTT:
    name = "sarvam-realtime"

    def __init__(
        self,
        clock: Clock,
        *,
        api_key: str | None = None,
        language_code: str = "hi-IN",
        silence_duration_ms: int = 500,
        timeout_s: float = 20.0,
    ) -> None:
        key = api_key if api_key is not None else os.environ.get("SARVAM_API_KEY")
        if not key:
            raise ProviderError("SARVAM_API_KEY is not set and no api_key was passed")
        self._client = AsyncSarvamAI(api_subscription_key=key)
        self._clock = clock
        self._language_code = language_code
        self._silence_ms = silence_duration_ms
        self._timeout_s = timeout_s
        self.events: list[tuple[str, int]] = []

    async def stream(
        self, audio: AsyncIterator[AudioChunk], *, trace: TurnTrace
    ) -> AsyncIterator[Transcript]:
        self.events = []
        text = ""
        async with trace.aspan(Stage.STT, self.name):
            try:
                async with self._client.speech_to_text_realtime_streaming.connect(
                    language_code=self._language_code,
                    encoding="mulaw",
                    sample_rate=str(SAMPLE_RATE_HZ),
                    endpointing="vad",
                    silence_duration_ms=str(self._silence_ms),
                ) as sock:

                    async def send() -> None:
                        async for chunk in audio:
                            if chunk.sample_rate != SAMPLE_RATE_HZ:
                                raise ProviderError(
                                    f"expected 8 kHz audio, got {chunk.sample_rate}"
                                )
                            payload = base64.b64encode(mulaw.encode(chunk.pcm)).decode("ascii")
                            await sock.send_realtime_audio_input(RealtimeAudioInput(audio=payload))

                    sender = asyncio.create_task(send())
                    try:
                        async with asyncio.timeout(self._timeout_s):
                            async for raw in sock:
                                message: Any = raw
                                name = str(getattr(message, "event", type(message).__name__))
                                self.events.append((name, self._clock.now_ns()))
                                if name == "error":
                                    raise ProviderError(f"Sarvam realtime error: {message}")
                                if name == "transcript.final" and message.text:
                                    text = str(message.text)
                                    break
                    finally:
                        sender.cancel()
                        await asyncio.gather(sender, return_exceptions=True)
            except (ApiError, httpx.HTTPError, TimeoutError, OSError) as exc:
                raise ProviderError(f"Sarvam realtime request failed: {exc!r}") from exc
            trace.mark(FINAL_TRANSCRIPT)
            yield Transcript(text=text, is_final=True, language=self._language_code)

    def event_time_ns(self, name: str) -> int | None:
        """Timestamp of the first event called `name` in the last call, if any."""
        return next((t for n, t in self.events if n == name), None)
