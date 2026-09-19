"""Real faster-whisper round-trip. Downloads the "tiny" model on first run
(cached by huggingface_hub afterward) -- opt-in only, per phase-1 spec
section 7.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import numpy as np
import pytest

from dhvani.clock import RealClock
from dhvani.providers.whisper_stt import WhisperSTT
from dhvani.telemetry.span import FINAL_TRANSCRIPT, TurnTrace
from dhvani.types import AudioChunk

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _one_second_of_noise() -> AsyncIterator[AudioChunk]:
    rng = np.random.default_rng(0)
    samples = (rng.standard_normal(16000) * 1000).astype(np.int16)
    yield AudioChunk(pcm=samples.tobytes(), sample_rate=16000, seq=0, is_last=True)


async def test_whisper_stt_round_trip_shape() -> None:
    clock = RealClock()
    stt = WhisperSTT("tiny", clock)
    trace = TurnTrace(clock, turn_id="integration")

    transcripts = [t async for t in stt.stream(_one_second_of_noise(), trace=trace)]

    assert len(transcripts) == 1
    assert transcripts[0].is_final
    assert isinstance(transcripts[0].text, str)
    assert not trace.spans[0].is_open
    assert any(m.name == FINAL_TRANSCRIPT for m in trace.marks)


async def test_whisper_stt_rejects_wrong_sample_rate() -> None:
    clock = RealClock()
    stt = WhisperSTT("tiny", clock)
    trace = TurnTrace(clock, turn_id="integration")

    async def wrong_rate() -> AsyncIterator[AudioChunk]:
        yield AudioChunk(pcm=b"\x00\x00" * 100, sample_rate=8000, seq=0, is_last=True)

    with pytest.raises(ValueError, match="16000"):
        async for _ in stt.stream(wrong_rate(), trace=trace):
            pass
