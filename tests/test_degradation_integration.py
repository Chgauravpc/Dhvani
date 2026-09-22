"""Real degradation sweep against real Svarah/LAHAJA audio and a real STT --
phase-3 spec section 8's integration row, which the unit tests in
test_degradation.py deliberately don't cover (they use a synthetic draining
STT precisely so they need no real model or dataset).

Opt-in (`pytest.mark.integration`) and bounded deliberately small (`tiny`
Whisper, 3 examples, 2 channel configs): this repo's own host has twice
killed a larger real-model sweep under memory pressure (`docs/specs/
phase-2b.md` §12, `docs/specs/phase-3.md` §2.2) -- this test exists to
prove the sweep runs against real data and a real provider, not to
reproduce that larger sweep's statistical power. `scripts/
run_degradation_sweep.py` is the tool for a real, larger run.

Skips cleanly if Hugging Face access to the dataset isn't available, same
"real-dataset tests skip cleanly when the data is absent" rule phase-2b
spec section 3 states for real-API tests -- there is no static skipif
condition for gated dataset access (unlike an env-var API key), so the
skip happens at runtime around the actual load attempt.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from dhvani.audio.channel import ChannelConfig
from dhvani.clock import RealClock
from dhvani.entity.lexicon import DEFAULT_LEXICON, DomainLexicon
from dhvani.eval.datasets import (
    FilteredExamples,
    TranscriptExample,
    load_lahaja_filtered,
    load_svarah_filtered,
)
from dhvani.eval.degradation import run_degradation_sweep
from dhvani.providers.whisper_stt import WhisperSTT

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_CONFIGS = (
    ChannelConfig(narrowband_hz=16000, mulaw=False),  # wideband baseline
    ChannelConfig(narrowband_hz=8000, mulaw=True, packet_loss=0.03),  # a real impairment
)


_Loader = Callable[[DomainLexicon, int], FilteredExamples]


def _load_bounded(loader: _Loader, n: int) -> list[TranscriptExample]:
    try:
        filtered = loader(DEFAULT_LEXICON, n)
    except Exception as exc:  # noqa: BLE001 -- any failure here means "can't reach the data"
        pytest.skip(f"could not load dataset (no Hugging Face access?): {exc!r}")
    pool = list(filtered.entity_bearing) + list(filtered.clean_sample)
    if not pool:
        pytest.skip("dataset loaded but yielded no examples")
    return pool[:n]


async def test_real_degradation_sweep_against_svarah() -> None:
    examples = _load_bounded(load_svarah_filtered, n=3)
    clock = RealClock()
    stt = WhisperSTT("tiny", clock)

    points = await run_degradation_sweep(examples, _CONFIGS, stt, clock)

    assert len(points) == len(_CONFIGS)
    for point in points:
        assert 0.0 <= point.wer
        assert point.stt_p50_ms >= 0.0
        assert point.stt_p90_ms >= point.stt_p50_ms
        assert point.n_utterances == len(examples)
    # The narrowband+loss config should show *some* effect of degradation --
    # either on the accuracy axis, the latency axis, or in frames actually
    # lost, not silently identical to the clean baseline on every axis.
    baseline, degraded = points[0], points[1]
    assert degraded.frames_lost >= 0
    assert (baseline.wer, baseline.stt_p50_ms) != (degraded.wer, degraded.stt_p50_ms) or (
        degraded.frames_lost > 0
    )


async def test_real_degradation_sweep_against_lahaja() -> None:
    examples = _load_bounded(load_lahaja_filtered, n=3)
    clock = RealClock()
    stt = WhisperSTT("tiny", clock)

    points = await run_degradation_sweep(examples, _CONFIGS, stt, clock)

    assert len(points) == len(_CONFIGS)
    for point in points:
        assert 0.0 <= point.wer
        assert point.stt_p50_ms >= 0.0
        assert point.n_utterances == len(examples)
