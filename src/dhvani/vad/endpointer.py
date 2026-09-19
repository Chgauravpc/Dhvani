"""End-of-utterance state machine, independent of any real VAD model.

Speech/not-speech decisions come from an injected `SpeechScorer`, so this
state machine is fully unit-testable against synthetic probability
sequences without loading a real model. See `dhvani.vad.silero.SileroVad`
for the real Silero-backed scorer.

Deviation from the phase-1 spec draft: `feed()` is synchronous (Silero's ONNX
inference on a 512-sample window is sub-millisecond CPU work, not I/O, so
there is no genuine suspension point -- see Phase 0's "everything async that
will eventually touch I/O" rule) and returns every transition the chunk
produced, in order, rather than a single optional one -- a chunk can span
more than one 512-sample window and therefore more than one transition.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from dhvani.types import AudioChunk

WINDOW_SAMPLES = 512
"""Silero's recommended analysis window at 16kHz (32ms)."""


class SpeechScorer(Protocol):
    def probability(self, window: NDArray[np.float32]) -> float:
        """Probability in [0, 1] that `window` (WINDOW_SAMPLES float32
        samples in [-1, 1]) contains speech."""
        ...


class EndpointEvent(StrEnum):
    SPEECH_STARTED = "speech_started"
    SPEECH_ENDED = "speech_ended"


class Endpointer:
    """Turns a stream of audio chunks into SPEECH_STARTED/SPEECH_ENDED events."""

    def __init__(
        self,
        scorer: SpeechScorer,
        sample_rate: int = 16000,
        threshold: float = 0.5,
        min_silence_ms: float = 500.0,
    ) -> None:
        self._scorer = scorer
        self._sample_rate = sample_rate
        self._threshold = threshold
        window_ms = WINDOW_SAMPLES / sample_rate * 1000
        self._min_silence_windows = max(round(min_silence_ms / window_ms), 1)
        self._buffer: NDArray[np.float32] = np.zeros(0, dtype=np.float32)
        self._in_speech = False
        self._silence_windows = 0

    def feed(self, chunk: AudioChunk) -> list[EndpointEvent]:
        """Process one chunk, returning every transition it produced, in order."""
        if chunk.sample_rate != self._sample_rate:
            raise ValueError(
                f"Endpointer configured for {self._sample_rate}Hz, got {chunk.sample_rate}Hz"
            )
        samples = np.frombuffer(chunk.pcm, dtype=np.int16).astype(np.float32) / 32768.0
        self._buffer = np.concatenate([self._buffer, samples])

        events: list[EndpointEvent] = []
        while len(self._buffer) >= WINDOW_SAMPLES:
            window = self._buffer[:WINDOW_SAMPLES]
            self._buffer = self._buffer[WINDOW_SAMPLES:]
            event = self._feed_window(window)
            if event is not None:
                events.append(event)
        return events

    def _feed_window(self, window: NDArray[np.float32]) -> EndpointEvent | None:
        is_speech = self._scorer.probability(window) >= self._threshold

        if not self._in_speech:
            if is_speech:
                self._in_speech = True
                self._silence_windows = 0
                return EndpointEvent.SPEECH_STARTED
            return None

        if is_speech:
            self._silence_windows = 0
            return None

        self._silence_windows += 1
        if self._silence_windows >= self._min_silence_windows:
            self._in_speech = False
            self._silence_windows = 0
            return EndpointEvent.SPEECH_ENDED
        return None
