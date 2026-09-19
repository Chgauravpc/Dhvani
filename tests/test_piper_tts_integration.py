"""Real Piper round-trip. Downloads the pinned hi_IN voice on first run
(cached by huggingface_hub afterward) -- opt-in only, per phase-1 spec
section 7.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from dhvani.clock import RealClock
from dhvani.providers.piper_tts import DEFAULT_VOICE, PiperTTS, ensure_voice_downloaded
from dhvani.telemetry.span import FIRST_AUDIO_OUT, TurnTrace
from dhvani.types import Stage

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _two_sentences() -> AsyncIterator[str]:
    yield "Namaste duniya."
    yield "Yeh ek parikshan hai."


async def test_piper_tts_round_trip_shape() -> None:
    model_path, config_path = ensure_voice_downloaded(DEFAULT_VOICE)
    clock = RealClock()
    tts = PiperTTS(model_path, clock, voice_config_path=config_path)
    trace = TurnTrace(clock, turn_id="integration")

    chunks = [c async for c in tts.stream(_two_sentences(), trace=trace)]

    assert len(chunks) > 0
    assert all(c.sample_rate == tts.sample_rate for c in chunks)
    assert all(len(c.pcm) > 0 for c in chunks)
    tts_span = next(s for s in trace.spans if s.stage == Stage.TTS)
    assert not tts_span.is_open
    assert any(m.name == FIRST_AUDIO_OUT for m in trace.marks)
