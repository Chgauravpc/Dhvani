"""The overlapped streaming runner and barge-in.

Unlike `SequentialRunner`, TTS starts on the first complete sentence the LLM
produces instead of waiting for the full response: the LLM runs as a
background task pushing sentences into a queue, and that queue -- wrapped as
an async iterator -- is exactly the `AsyncIterator[str]` `TTSProvider.stream`
already expects from Phase 0. No new provider-side contract is needed.

Streaming STT partials are deferred (phase-1 spec, open question 1), so the
LLM starts only once the final transcript is ready; the overlap this runner
adds over `SequentialRunner` is LLM-generation-concurrent-with-TTS-synthesis.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

from dhvani.clock import Clock
from dhvani.config import LatencyBudget
from dhvani.providers.base import LLMProvider, STTProvider, TTSProvider
from dhvani.safety.prompt_guard import strip_markdown_for_speech
from dhvani.telemetry.span import USER_SPEECH_END, TurnTrace
from dhvani.types import AudioChunk, Message

_SENTENCE_END_RE = re.compile(r"[.!?।]")
"""Matches ., !, ? and the Devanagari danda (U+0964)."""


def _split_ready_sentence(buffer: str) -> tuple[str | None, str]:
    """Split off the first complete sentence in `buffer`, if any.

    Returns `(sentence, remainder)`, or `(None, buffer)` if no
    sentence-ending punctuation has arrived yet.
    """
    match = _SENTENCE_END_RE.search(buffer)
    if match is None:
        return None, buffer
    end = match.end()
    return buffer[:end].strip(), buffer[end:].lstrip()


@dataclass(frozen=True, slots=True)
class TurnResult:
    """Result of one full turn through the overlapped pipeline."""

    transcript: str
    response_text: str
    audio: list[AudioChunk]
    trace: TurnTrace


class BargeInError(Exception):
    """Raised when the user starts speaking again while the agent is talking."""

    def __init__(self, trace: TurnTrace) -> None:
        super().__init__("user speech detected during playback")
        self.trace = trace


class OverlappedRunner:
    """Streams STT -> LLM -> TTS with LLM generation overlapping TTS synthesis.

    `SequentialRunner` is kept, unmodified, as the Phase 0 baseline this
    runner must beat.
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

    async def run_turn(
        self,
        audio: AsyncIterator[AudioChunk],
        *,
        barge_in: asyncio.Event | None = None,
    ) -> TurnResult:
        trace = TurnTrace(self._clock)
        trace.mark(USER_SPEECH_END)

        final_transcript = ""
        async for transcript in self._stt.stream(audio, trace=trace):
            if transcript.is_final:
                final_transcript = transcript.text

        messages = [Message(role="user", content=final_transcript)]
        sentence_queue: asyncio.Queue[str | None] = asyncio.Queue()
        response_parts: list[str] = []
        audio_chunks: list[AudioChunk] = []

        async def produce_sentences() -> None:
            buffer = ""
            try:
                async for delta in self._llm.stream(messages, trace=trace):
                    if not delta.text:
                        continue
                    buffer += delta.text
                    response_parts.append(delta.text)
                    sentence, buffer = _split_ready_sentence(buffer)
                    while sentence is not None:
                        await sentence_queue.put(strip_markdown_for_speech(sentence))
                        sentence, buffer = _split_ready_sentence(buffer)
                if buffer.strip():
                    await sentence_queue.put(strip_markdown_for_speech(buffer))
            finally:
                # Always unblock the TTS consumer, even on failure or
                # cancellation, so a broken LLM stream can't hang TTS forever.
                await sentence_queue.put(None)

        async def sentence_stream() -> AsyncIterator[str]:
            while True:
                item = await sentence_queue.get()
                if item is None:
                    return
                yield item

        async def consume_audio() -> None:
            async for chunk in self._tts.stream(sentence_stream(), trace=trace):
                audio_chunks.append(chunk)

        llm_task = asyncio.create_task(produce_sentences())
        tts_task = asyncio.create_task(consume_audio())

        if barge_in is not None:
            barge_in_task = asyncio.create_task(barge_in.wait())
            done, _pending = await asyncio.wait(
                {tts_task, barge_in_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if tts_task not in done:
                tts_task.cancel()
                llm_task.cancel()
                await asyncio.gather(tts_task, llm_task, return_exceptions=True)
                raise BargeInError(trace)
            barge_in_task.cancel()
            try:
                await barge_in_task
            except asyncio.CancelledError:
                pass

        await tts_task
        await llm_task

        return TurnResult(
            transcript=final_transcript,
            response_text="".join(response_parts),
            audio=audio_chunks,
            trace=trace,
        )
