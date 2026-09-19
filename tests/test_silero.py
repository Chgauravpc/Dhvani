from __future__ import annotations

import numpy as np
import pytest

from dhvani.vad.endpointer import WINDOW_SAMPLES
from dhvani.vad.silero import SileroVad


def test_silero_probability_is_a_valid_probability() -> None:
    # No network access and no separate download: the ONNX model ships as
    # package data inside silero-vad-notorch, so this is safe to run in CI.
    vad = SileroVad()
    silence = np.zeros(WINDOW_SAMPLES, dtype=np.float32)

    p = vad.probability(silence)

    assert 0.0 <= p <= 1.0


def test_silero_rejects_wrong_window_size() -> None:
    vad = SileroVad()

    with pytest.raises(ValueError, match=str(WINDOW_SAMPLES)):
        vad.probability(np.zeros(100, dtype=np.float32))
