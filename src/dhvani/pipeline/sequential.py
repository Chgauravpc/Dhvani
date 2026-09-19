"""The deliberately sequential baseline runner."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from dhvani.clock import Clock
from dhvani.config import LatencyBudget
from dhvani.providers.base import LLMProvider, STTProvider, TTSProvider
from dhvani.telemetry.span import USER_SPEECH_END, TurnTrace
from dhvani.types import AudioChunk, Message


@dataclass(frozen=True, slots=True)
class TurnResult:
    """Result of one full turn through the sequential pipeline."""

    transcript: str
    response_text: str
    audio: list[AudioChunk]
    trace: TurnTrace


class SequentialRunner:
    """Deliberately sequential: STT completes, then LLM completes, then TTS.

    No overlap. Exists to validate the telemetry end to end, and to be the
    baseline number the Phase 1 overlapped runner must beat. Do not optimize.
    """

    def __init__(
        self,
        stt: STTProvider,
        llm: LLMProvider,
        tts: TTSProvider,
        clock: Clock,
        budget: LatencyBudget,
    ) -> None:
        self._stt = stt
        self._llm = llm
        self._tts = tts
        self._clock = clock
        self._budget = budget

    async def run_turn(self, audio: AsyncIterator[AudioChunk]) -> TurnResult:
        trace = TurnTrace(self._clock)
        trace.mark(USER_SPEECH_END)

        final_transcript = ""
        async for transcript in self._stt.stream(audio, trace=trace):
            if transcript.is_final:
                final_transcript = transcript.text

        messages = [Message(role="user", content=final_transcript)]
        response_parts: list[str] = []
        async for delta in self._llm.stream(messages, trace=trace):
            if delta.text:
                response_parts.append(delta.text)
        # Concatenated directly, matching a real streaming LLMProvider: each
        # delta already carries its own whitespace, the same invariant
        # OverlappedRunner relies on.
        response_text = "".join(response_parts)

        async def full_response() -> AsyncIterator[str]:
            yield response_text

        audio_chunks = [chunk async for chunk in self._tts.stream(full_response(), trace=trace)]

        return TurnResult(
            transcript=final_transcript,
            response_text=response_text,
            audio=audio_chunks,
            trace=trace,
        )
