"""Streaming resampler -- phase-3 spec section 8: 8k<->16k length ratios, no
discontinuity across frame boundaries, `reset` clears state."""

from __future__ import annotations

import math
from array import array

from dhvani.audio.resample import Resampler, resample


def _sine_pcm(n_samples: int, sample_rate: int, freq_hz: float = 220.0) -> bytes:
    samples = [
        int(8000 * math.sin(2 * math.pi * freq_hz * i / sample_rate)) for i in range(n_samples)
    ]
    return array("h", samples).tobytes()


def test_downsample_16k_to_8k_length_ratio() -> None:
    pcm = _sine_pcm(1600, 16000)  # 100ms at 16kHz
    out = resample(pcm, 16000, 8000)
    n_out = len(out) // 2
    assert abs(n_out - 800) <= 2  # ~100ms at 8kHz


def test_upsample_8k_to_16k_length_ratio() -> None:
    pcm = _sine_pcm(800, 8000)  # 100ms at 8kHz
    out = resample(pcm, 8000, 16000)
    n_out = len(out) // 2
    assert abs(n_out - 1600) <= 2


def test_noop_when_rates_match() -> None:
    pcm = _sine_pcm(320, 16000)
    r = Resampler(16000, 16000)
    assert r.is_noop
    assert r.process(pcm) == pcm


def test_reset_clears_interpolation_and_filter_state() -> None:
    pcm = _sine_pcm(320, 16000)
    r = Resampler(16000, 8000)
    r.process(pcm)
    r.reset()

    fresh = Resampler(16000, 8000)
    assert r.process(pcm) == fresh.process(pcm)


def test_streaming_frames_match_one_shot_processing_downsample() -> None:
    """The whole point of statefulness: processing a signal split across
    many small frames must produce the same samples as processing it whole,
    including at every frame boundary -- no discontinuity, no click."""
    frame_samples = 160  # 20ms at 8kHz-equivalent framing on a 16kHz source... any small size
    total_samples = frame_samples * 10
    pcm = _sine_pcm(total_samples, 16000)

    whole = resample(pcm, 16000, 8000)

    streaming = Resampler(16000, 8000)
    chunks: list[bytes] = []
    frame_bytes = frame_samples * 2
    for i in range(0, len(pcm), frame_bytes):
        chunks.append(streaming.process(pcm[i : i + frame_bytes]))
    streamed = b"".join(chunks)

    assert streamed == whole


def test_streaming_frames_match_one_shot_processing_upsample() -> None:
    frame_samples = 80
    total_samples = frame_samples * 10
    pcm = _sine_pcm(total_samples, 8000)

    whole = resample(pcm, 8000, 16000)

    streaming = Resampler(8000, 16000)
    chunks: list[bytes] = []
    frame_bytes = frame_samples * 2
    for i in range(0, len(pcm), frame_bytes):
        chunks.append(streaming.process(pcm[i : i + frame_bytes]))
    streamed = b"".join(chunks)

    assert streamed == whole


def test_negative_rate_raises() -> None:
    import pytest

    with pytest.raises(ValueError):
        Resampler(-16000, 8000)


def test_odd_length_input_raises() -> None:
    import pytest

    with pytest.raises(ValueError, match="whole number of int16 samples"):
        Resampler(16000, 8000).process(b"\x01\x00\x02")
