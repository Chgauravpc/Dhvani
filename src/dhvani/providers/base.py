"""Provider protocols for STT, LLM, and TTS.

Every implementation must honor three contracts:

1. Emit telemetry — open an `aspan` for the provider's stage, and record
   the relevant first-output mark (`FIRST_PARTIAL`, `FIRST_LLM_TOKEN`,
   `FIRST_AUDIO_OUT`).
2. Be cancellable — a live stream must handle `asyncio.CancelledError`,
   close its span, release resources, and re-raise. Never swallow it.
3. `TTSProvider.stream` takes an async iterator of text, never a string.
   That is what lets Phase 1 start synthesis on the first sentence while
   the LLM is still generating; no string convenience overload is added,
   because it would get used and would silently destroy that overlap.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Protocol

from dhvani.telemetry.span import TurnTrace
from dhvani.types import AudioChunk, LLMDelta, Message, Transcript


class ProviderError(Exception):
    """Raised by a provider that fails mid-stream."""


class STTProvider(Protocol):
    name: str

    def stream(
        self, audio: AsyncIterator[AudioChunk], *, trace: TurnTrace
    ) -> AsyncIterator[Transcript]: ...


class LLMProvider(Protocol):
    name: str

    def stream(
        self,
        messages: Sequence[Message],
        *,
        trace: TurnTrace,
        tools: Sequence[Mapping[str, object]] = (),
    ) -> AsyncIterator[LLMDelta]: ...


class TTSProvider(Protocol):
    name: str
    sample_rate: int

    def stream(
        self, text: AsyncIterator[str], *, trace: TurnTrace
    ) -> AsyncIterator[AudioChunk]: ...
