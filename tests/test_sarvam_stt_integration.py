"""Real Sarvam speech-to-text round trip. Requires SARVAM_API_KEY -- opt-in
only (marker) and skipped even under `-m integration` if no key is
configured, matching `test_groq_llm_integration.py`'s pattern (phase-1 spec
section 7 / phase-2b spec section 3: real-API tests skip cleanly without a
key, so `uv run pytest` stays network-free by default).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import numpy as np
import pytest

from dhvani.clock import RealClock
from dhvani.config import load_dotenv
from dhvani.providers.sarvam_stt import DEFAULT_MODEL, SarvamSTT
from dhvani.telemetry.span import FINAL_TRANSCRIPT, TurnTrace
from dhvani.types import AudioChunk

load_dotenv()  # picks up SARVAM_API_KEY from a local .env, same as GROQ_API_KEY

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.real_time_loop,  # real network I/O -- see tests/conftest.py
    pytest.mark.skipif(not os.environ.get("SARVAM_API_KEY"), reason="SARVAM_API_KEY not set"),
]


def _one_second_tone_pcm() -> bytes:
    """A short pure tone -- real, non-silent audio, so the request isn't
    trivially rejected. This test only checks the round-trip shape (a
    string comes back, the span closes), not transcription accuracy."""
    sample_rate = 16000
    t = np.linspace(0, 1.0, sample_rate, endpoint=False)
    samples = (np.sin(2 * np.pi * 440 * t) * 3000).astype(np.int16)
    return samples.tobytes()


async def _one_second_tone() -> AsyncIterator[AudioChunk]:
    yield AudioChunk(pcm=_one_second_tone_pcm(), sample_rate=16000, seq=0, is_last=True)


async def test_sarvam_stt_real_round_trip_shape() -> None:
    clock = RealClock()
    stt = SarvamSTT(DEFAULT_MODEL, clock)
    trace = TurnTrace(clock, turn_id="integration")

    transcripts = [t async for t in stt.stream(_one_second_tone(), trace=trace)]

    assert len(transcripts) == 1
    assert transcripts[0].is_final
    assert isinstance(transcripts[0].text, str)
    assert not trace.spans[0].is_open
    assert any(m.name == FINAL_TRANSCRIPT for m in trace.marks)
