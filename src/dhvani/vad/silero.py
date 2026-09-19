"""Real Silero VAD speech-probability scorer.

Uses `silero-vad-notorch` (not `silero-vad`) specifically to avoid pulling in
a multi-GB PyTorch dependency for a small detector -- see phase-1 spec
section 2. The package bundles its ONNX model as package data, so
`load_silero_vad(onnx=True)` needs no runtime download.
"""

from __future__ import annotations

import numpy as np
import silero_vad_notorch as _svn
from numpy.typing import NDArray

from dhvani.vad.endpointer import WINDOW_SAMPLES


class SileroVad:
    """Wraps silero-vad-notorch's ONNX model as a `SpeechScorer`.

    Silero's model is stateful across calls (it carries recurrent state
    between consecutive windows of the same stream), so one instance should
    back exactly one audio stream. Call `reset()` before reusing an instance
    for a new, unrelated stream.
    """

    def __init__(self, sampling_rate: int = 16000) -> None:
        self._model = _svn.load_silero_vad(onnx=True)
        self._sampling_rate = sampling_rate

    def probability(self, window: NDArray[np.float32]) -> float:
        if window.shape[0] != WINDOW_SAMPLES:
            raise ValueError(f"expected {WINDOW_SAMPLES} samples, got {window.shape[0]}")
        result = self._model(window, self._sampling_rate)
        return float(result[0, 0])

    def reset(self) -> None:
        self._model.reset_states()
