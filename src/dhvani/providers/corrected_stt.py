"""Wraps any STTProvider, applying `EntityCorrector` to its output.

Satisfies `STTProvider` exactly -- phase 0's contract, unchanged.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from dhvani.entity.corrector import EntityCorrector
from dhvani.providers.base import STTProvider
from dhvani.telemetry.span import TurnTrace
from dhvani.types import AudioChunk, Stage, Transcript


class CorrectedSTT:
    """Wraps `inner`, running each of its transcripts through `corrector`.

    Opens its own span, nested inside the inner provider's -- correction is
    O(windows x lexicon) under rapidfuzz, which is cheap but not free on a
    long transcript, and a project whose whole argument is per-stage
    measurement should not have an unmeasured stage. The span also makes it
    possible to say later whether correction is worth its own latency
    (phase-2 spec section 6.4).
    """

    def __init__(self, inner: STTProvider, corrector: EntityCorrector) -> None:
        self._inner = inner
        self._corrector = corrector
        # A plain attribute, not a property -- STTProvider.name is a plain
        # `str` attribute in the Protocol (matching every other provider:
        # WhisperSTT/GroqLLM/MockSTT all assign `name` directly), and mypy
        # --strict correctly rejects a read-only property there structurally.
        self.name = f"{inner.name}+dhvani-entity"

    async def stream(
        self, audio: AsyncIterator[AudioChunk], *, trace: TurnTrace
    ) -> AsyncIterator[Transcript]:
        async for transcript in self._inner.stream(audio, trace=trace):
            async with trace.aspan(Stage.STT, "dhvani-entity"):
                result = self._corrector.correct(transcript.text)
            yield Transcript(
                text=result.text,
                is_final=transcript.is_final,
                language=transcript.language,
                confidence=transcript.confidence,
                stability=transcript.stability,
            )
