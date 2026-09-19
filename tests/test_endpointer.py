from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray

from dhvani.types import AudioChunk
from dhvani.vad.endpointer import WINDOW_SAMPLES, Endpointer, EndpointEvent


class _ScriptedScorer:
    """Returns one probability per call, taken from a fixed script."""

    def __init__(self, probabilities: list[float]) -> None:
        self._probabilities = probabilities
        self._calls = 0

    def probability(self, window: NDArray[np.float32]) -> float:
        p = self._probabilities[self._calls]
        self._calls += 1
        return p


def _chunk_of_windows(n_windows: int, sample_rate: int = 16000) -> AudioChunk:
    n_samples = n_windows * WINDOW_SAMPLES
    pcm = b"\x00\x00" * n_samples
    return AudioChunk(pcm=pcm, sample_rate=sample_rate, seq=0)


def test_silence_produces_no_events() -> None:
    scorer = _ScriptedScorer([0.0] * 10)
    endpointer = Endpointer(scorer, min_silence_ms=500.0)

    events = endpointer.feed(_chunk_of_windows(10))

    assert events == []


def test_speech_start_fires_immediately() -> None:
    scorer = _ScriptedScorer([0.0, 0.9, 0.9])
    endpointer = Endpointer(scorer, min_silence_ms=500.0)

    events = endpointer.feed(_chunk_of_windows(3))

    assert events == [EndpointEvent.SPEECH_STARTED]


def test_speech_end_requires_min_silence_duration() -> None:
    # 32ms/window; min_silence_ms=100 -> needs ceil(100/32)=4 silent windows.
    scorer = _ScriptedScorer([0.9] + [0.0] * 3 + [0.0])
    endpointer = Endpointer(scorer, min_silence_ms=100.0)

    events = endpointer.feed(_chunk_of_windows(5))

    assert events == [EndpointEvent.SPEECH_STARTED, EndpointEvent.SPEECH_ENDED]


def test_brief_dip_below_threshold_does_not_end_utterance() -> None:
    # Only 2 silent windows before speech resumes -- below the 4-window
    # threshold for min_silence_ms=100, so no SPEECH_ENDED should fire.
    scorer = _ScriptedScorer([0.9, 0.0, 0.0, 0.9, 0.9])
    endpointer = Endpointer(scorer, min_silence_ms=100.0)

    events = endpointer.feed(_chunk_of_windows(5))

    assert events == [EndpointEvent.SPEECH_STARTED]


def test_feed_buffers_partial_windows_across_calls() -> None:
    scorer = _ScriptedScorer([0.9])
    endpointer = Endpointer(scorer, min_silence_ms=500.0)

    half = WINDOW_SAMPLES // 2
    first = AudioChunk(pcm=b"\x00\x00" * half, sample_rate=16000, seq=0)
    second = AudioChunk(pcm=b"\x00\x00" * half, sample_rate=16000, seq=1)

    assert endpointer.feed(first) == []
    assert endpointer.feed(second) == [EndpointEvent.SPEECH_STARTED]


def test_feed_rejects_mismatched_sample_rate() -> None:
    endpointer = Endpointer(_ScriptedScorer([]), sample_rate=16000)

    with pytest.raises(ValueError, match="16000"):
        endpointer.feed(_chunk_of_windows(1, sample_rate=8000))
