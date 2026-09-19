"""Mock STT/LLM/TTS providers with declared, reproducible timing.

Timing is declared up front rather than measured, so tests assert exact
values instead of tolerances. Each mock also accepts `fail_after`: it
raises `ProviderError` once it has produced that many outputs, so failure
paths can be exercised without touching a real provider.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass

from dhvani.clock import Clock
from dhvani.providers.base import ProviderError
from dhvani.telemetry.span import (
    FINAL_TRANSCRIPT,
    FIRST_AUDIO_OUT,
    FIRST_LLM_TOKEN,
    FIRST_PARTIAL,
    TurnTrace,
)
from dhvani.types import AudioChunk, LLMDelta, Message, Stage, ToolCall, Transcript


@dataclass(frozen=True, slots=True)
class MockTiming:
    """Declared per-provider timing, in milliseconds."""

    ttfb_ms: float
    """Delay before the first output, measured from stream start."""
    per_unit_ms: float
    """Delay before each subsequent partial / token / audio chunk."""


def _check_fail(name: str, fail_after: int | None, emitted: int) -> None:
    if fail_after is not None and emitted > fail_after:
        raise ProviderError(f"{name} failing after {fail_after} outputs")


class MockSTT:
    """Emits each declared partial, then one final transcript."""

    name = "mock-stt"

    def __init__(
        self,
        partials: Sequence[str],
        final: str,
        timing: MockTiming,
        clock: Clock,
        fail_after: int | None = None,
    ) -> None:
        self._partials = partials
        self._final = final
        self._timing = timing
        self._clock = clock
        self._fail_after = fail_after

    async def stream(
        self, audio: AsyncIterator[AudioChunk], *, trace: TurnTrace
    ) -> AsyncIterator[Transcript]:
        async with trace.aspan(Stage.STT, self.name):
            emitted = 0
            for text in self._partials:
                delay_ms = self._timing.ttfb_ms if emitted == 0 else self._timing.per_unit_ms
                await self._clock.sleep(delay_ms / 1000)
                emitted += 1
                _check_fail(self.name, self._fail_after, emitted)
                if emitted == 1:
                    trace.mark(FIRST_PARTIAL)
                yield Transcript(text=text, is_final=False)

            delay_ms = self._timing.ttfb_ms if emitted == 0 else self._timing.per_unit_ms
            await self._clock.sleep(delay_ms / 1000)
            emitted += 1
            _check_fail(self.name, self._fail_after, emitted)
            trace.mark(FINAL_TRANSCRIPT)
            yield Transcript(text=self._final, is_final=True)


class MockLLM:
    """Emits `response` as whitespace-preserving tokens, then a final delta.

    Concatenating every yielded delta's text reproduces `response` exactly --
    the same invariant a real streaming chat-completions API guarantees, and
    one `OverlappedRunner` relies on directly (it reassembles sentences by
    concatenating deltas, the way a real LLMProvider's tokens would).

    If `tool_calls` is non-empty, those are emitted before the final delta.
    """

    name = "mock-llm"

    def __init__(
        self,
        response: str,
        timing: MockTiming,
        clock: Clock,
        tool_calls: Sequence[ToolCall] = (),
        fail_after: int | None = None,
    ) -> None:
        self._tokens = re.findall(r"\S+\s*", response)
        self._timing = timing
        self._clock = clock
        self._tool_calls = tool_calls
        self._fail_after = fail_after

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        trace: TurnTrace,
        tools: Sequence[Mapping[str, object]] = (),
    ) -> AsyncIterator[LLMDelta]:
        async with trace.aspan(Stage.LLM, self.name):
            emitted = 0
            for token in self._tokens:
                delay_ms = self._timing.ttfb_ms if emitted == 0 else self._timing.per_unit_ms
                await self._clock.sleep(delay_ms / 1000)
                emitted += 1
                _check_fail(self.name, self._fail_after, emitted)
                if emitted == 1:
                    trace.mark(FIRST_LLM_TOKEN)
                yield LLMDelta(text=token)

            for call in self._tool_calls:
                await self._clock.sleep(self._timing.per_unit_ms / 1000)
                emitted += 1
                _check_fail(self.name, self._fail_after, emitted)
                yield LLMDelta(tool_call=call)

            await self._clock.sleep(self._timing.per_unit_ms / 1000)
            yield LLMDelta(is_final=True)


class MockTTS:
    """Consumes the text iterator and emits one zeroed-PCM chunk per item."""

    name = "mock-tts"

    def __init__(
        self,
        timing: MockTiming,
        clock: Clock,
        sample_rate: int = 16000,
        chunk_ms: float = 20.0,
        fail_after: int | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self._timing = timing
        self._clock = clock
        self._chunk_ms = chunk_ms
        self._fail_after = fail_after

    async def stream(
        self, text: AsyncIterator[str], *, trace: TurnTrace
    ) -> AsyncIterator[AudioChunk]:
        n_samples = round(self.sample_rate * self._chunk_ms / 1000)
        pcm = b"\x00\x00" * n_samples

        async with trace.aspan(Stage.TTS, self.name):
            emitted = 0
            seq = 0
            async for _ in text:
                delay_ms = self._timing.ttfb_ms if emitted == 0 else self._timing.per_unit_ms
                await self._clock.sleep(delay_ms / 1000)
                emitted += 1
                _check_fail(self.name, self._fail_after, emitted)
                if emitted == 1:
                    trace.mark(FIRST_AUDIO_OUT)
                yield AudioChunk(pcm=pcm, sample_rate=self.sample_rate, seq=seq)
                seq += 1
