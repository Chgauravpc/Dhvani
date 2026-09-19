"""Real STT via faster-whisper (CTranslate2), CPU by default.

Not a native streaming model -- see phase-1 spec section 2. This provider
buffers whatever audio the caller feeds it (the endpointer decides when that
stream ends, by closing the iterator at end-of-utterance) and transcribes
the whole utterance once, in a worker thread so the event loop isn't
blocked. No `FIRST_PARTIAL` mark is emitted in this design.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import numpy as np
from faster_whisper import WhisperModel

from dhvani.clock import Clock
from dhvani.telemetry.span import FINAL_TRANSCRIPT, TurnTrace
from dhvani.types import AudioChunk, Stage, Transcript

EXPECTED_SAMPLE_RATE = 16000


class WhisperSTT:
    name = "faster-whisper"

    def __init__(
        self,
        model_size: str,
        clock: Clock,
        device: str = "cpu",
        compute_type: str = "int8",
        language: str | None = None,
    ) -> None:
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
        self._clock = clock
        self._language = language

    async def stream(
        self, audio: AsyncIterator[AudioChunk], *, trace: TurnTrace
    ) -> AsyncIterator[Transcript]:
        async with trace.aspan(Stage.STT, self.name):
            pcm_parts: list[bytes] = []
            async for chunk in audio:
                if chunk.sample_rate != EXPECTED_SAMPLE_RATE:
                    raise ValueError(
                        f"WhisperSTT expects {EXPECTED_SAMPLE_RATE}Hz audio, "
                        f"got {chunk.sample_rate}Hz"
                    )
                pcm_parts.append(chunk.pcm)

            pcm = b"".join(pcm_parts)
            if not pcm:
                trace.mark(FINAL_TRANSCRIPT)
                yield Transcript(text="", is_final=True)
                return

            samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
            text, language = await asyncio.to_thread(self._transcribe, samples)
            trace.mark(FINAL_TRANSCRIPT)
            yield Transcript(text=text, is_final=True, language=language)

    def _transcribe(self, samples: np.typing.NDArray[np.float32]) -> tuple[str, str | None]:
        segments, info = self._model.transcribe(samples, language=self._language)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return text, info.language
