from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from dhvani.clock import FakeClock
from dhvani.entity.corrector import EntityCorrector
from dhvani.entity.lexicon import LATIN, DomainLexicon, LexiconEntry
from dhvani.providers.corrected_stt import CorrectedSTT
from dhvani.providers.mock import MockSTT, MockTiming
from dhvani.telemetry.span import TurnTrace
from dhvani.types import AudioChunk, Stage

pytestmark = pytest.mark.asyncio

_LEXICON = DomainLexicon(
    [LexiconEntry(canonical="Aadhaar", variants={LATIN: ("aadhaar", "aadhar", "adhaar")})]
)


async def _one_audio_chunk() -> AsyncIterator[AudioChunk]:
    yield AudioChunk(pcm=b"\x00\x00" * 160, sample_rate=16000, seq=0, is_last=True)


async def test_corrected_stt_applies_correction_to_final_transcript() -> None:
    clock = FakeClock()
    trace = TurnTrace(clock, turn_id="t1")
    timing = MockTiming(ttfb_ms=10.0, per_unit_ms=10.0)
    inner = MockSTT(partials=[], final="please check my adhar status", timing=timing, clock=clock)
    corrected = CorrectedSTT(inner, EntityCorrector(_LEXICON, threshold=0.82))

    transcripts = [t async for t in corrected.stream(_one_audio_chunk(), trace=trace)]

    assert len(transcripts) == 1
    assert "Aadhaar" in transcripts[0].text
    assert transcripts[0].is_final


async def test_corrected_stt_leaves_transcript_without_entities_unchanged() -> None:
    clock = FakeClock()
    trace = TurnTrace(clock, turn_id="t1")
    timing = MockTiming(ttfb_ms=10.0, per_unit_ms=10.0)
    inner = MockSTT(partials=[], final="the weather is nice today", timing=timing, clock=clock)
    corrected = CorrectedSTT(inner, EntityCorrector(_LEXICON, threshold=0.82))

    (transcript,) = [t async for t in corrected.stream(_one_audio_chunk(), trace=trace)]

    assert transcript.text == "the weather is nice today"


async def test_corrected_stt_preserves_other_transcript_fields() -> None:
    clock = FakeClock()
    trace = TurnTrace(clock, turn_id="t1")
    timing = MockTiming(ttfb_ms=10.0, per_unit_ms=10.0)
    inner = MockSTT(partials=["adhar"], final="my adhar", timing=timing, clock=clock)
    corrected = CorrectedSTT(inner, EntityCorrector(_LEXICON, threshold=0.82))

    transcripts = [t async for t in corrected.stream(_one_audio_chunk(), trace=trace)]

    assert transcripts[0].is_final is False
    assert transcripts[1].is_final is True


async def test_corrected_stt_name_reports_the_wrapped_provider() -> None:
    clock = FakeClock()
    timing = MockTiming(ttfb_ms=10.0, per_unit_ms=10.0)
    inner = MockSTT(partials=[], final="x", timing=timing, clock=clock)
    corrected = CorrectedSTT(inner, EntityCorrector(_LEXICON, threshold=0.82))

    assert corrected.name == "mock-stt+dhvani-entity"


async def test_corrected_stt_opens_a_nested_stt_span() -> None:
    clock = FakeClock()
    trace = TurnTrace(clock, turn_id="t1")
    timing = MockTiming(ttfb_ms=10.0, per_unit_ms=10.0)
    inner = MockSTT(partials=[], final="my adhar", timing=timing, clock=clock)
    corrected = CorrectedSTT(inner, EntityCorrector(_LEXICON, threshold=0.82))

    async for _ in corrected.stream(_one_audio_chunk(), trace=trace):
        pass

    stt_spans = [s for s in trace.spans if s.stage == Stage.STT]
    assert any(s.name == "dhvani-entity" for s in stt_spans)
    assert any(s.name == "mock-stt" for s in stt_spans)
