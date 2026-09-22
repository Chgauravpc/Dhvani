"""Sample-rate conversion between the three rates this pipeline touches.

Twilio delivers 8 kHz, faster-whisper wants 16 kHz, and Piper emits at its
voice model's own rate (commonly 22.05 kHz). Conversion happens at the
transport boundary and nowhere else.

The resampler is stateful on purpose. A stateless per-call converter restarts
interpolation at every frame, and at 50 frames per second that discontinuity
is an audible click on every single one. Holding the previous tail sample and
the fractional read position across calls removes it for the interpolation
step; the downsampling pre-filter (see `_box_filter`) carries its own trailing
history across calls for the same reason -- an earlier version of this filter
recomputed its moving average from a zero-divisor ramp-up at the start of
every frame, which reproduced the exact frame-boundary discontinuity this
module exists to avoid, just in the pre-filter instead of the interpolator.

This is linear interpolation with a box pre-filter on downsampling -- honest
but not high-fidelity. It is adequate for speech at these rates and keeps the
module dependency-free; a polyphase FIR would be the upgrade if measurement
ever shows resampling hurting recognition accuracy.
"""

from __future__ import annotations

from array import array

_BIG_ENDIAN = array("h", [1]).tobytes()[0] == 0


def _to_samples(pcm: bytes) -> array[int]:
    if len(pcm) % 2:
        raise ValueError(f"pcm must be a whole number of int16 samples, got {len(pcm)} bytes")
    samples = array("h")
    samples.frombytes(pcm)
    if _BIG_ENDIAN:
        samples.byteswap()
    return samples


def _to_bytes(samples: array[int]) -> bytes:
    if _BIG_ENDIAN:
        samples = samples[:]
        samples.byteswap()
    return samples.tobytes()


class Resampler:
    """Streaming linear resampler for 16-bit signed mono PCM.

    Feed it successive frames with `process`; it carries interpolation state
    (and, when downsampling, pre-filter state) between calls so frame
    boundaries stay continuous. Call `reset` when starting a new, unrelated
    stream.
    """

    def __init__(self, src_rate_hz: int, dst_rate_hz: int) -> None:
        if src_rate_hz <= 0 or dst_rate_hz <= 0:
            raise ValueError(f"rates must be positive, got {src_rate_hz} -> {dst_rate_hz}")
        self.src_rate_hz = src_rate_hz
        self.dst_rate_hz = dst_rate_hz
        self._ratio = src_rate_hz / dst_rate_hz
        # Box filter width for downsampling. Averaging this many input samples
        # before picking one suppresses the aliasing that plain decimation
        # folds back into the speech band.
        self._box = max(1, round(self._ratio)) if dst_rate_hz < src_rate_hz else 1
        self._prev = 0
        self._pos = 0.0
        self._box_tail: array[int] = array("h")

    @property
    def is_noop(self) -> bool:
        return self.src_rate_hz == self.dst_rate_hz

    def reset(self) -> None:
        """Drop carried state. Use between unrelated streams."""
        self._prev = 0
        self._pos = 0.0
        self._box_tail = array("h")

    def process(self, pcm: bytes) -> bytes:
        """Convert one frame, carrying interpolation state to the next call."""
        if self.is_noop:
            return pcm

        samples = _to_samples(pcm)
        if not samples:
            return b""

        if self._box > 1:
            samples = self._box_filter(samples)

        out = array("h")
        n = len(samples)
        pos = self._pos
        prev = self._prev

        while pos < n:
            index = int(pos)
            frac = pos - index
            left = prev if index == 0 else samples[index - 1]
            right = samples[index]
            value = left + (right - left) * frac
            out.append(max(-32768, min(32767, int(value))))
            pos += self._ratio

        # Carry the tail: the next frame's sample 0 interpolates against this
        # frame's last sample, and the read position rolls over.
        self._prev = samples[n - 1]
        self._pos = pos - n
        return _to_bytes(out)

    def _box_filter(self, samples: array[int]) -> array[int]:
        """Causal moving average of width `self._box`, anti-aliasing before
        decimation.

        Carries the last `width - 1` raw samples from the previous call as
        `self._box_tail`, so every output sample in a non-initial frame sees
        a full window instead of ramping the divisor back up at position 0.
        Only the very first frame of a stream (empty tail) sees the
        ramp-up, which is the correct edge behaviour for genuine stream
        start rather than a frame-boundary artifact.
        """
        width = self._box
        combined = self._box_tail + samples
        tail_len = len(self._box_tail)
        out = array("h", bytes(len(samples) * 2))
        running = 0
        for i in range(len(combined)):
            running += combined[i]
            if i >= width:
                running -= combined[i - width]
            if i >= tail_len:
                divisor = min(i + 1, width)
                out[i - tail_len] = running // divisor
        self._box_tail = combined[-(width - 1) :] if width > 1 else array("h")
        return out


def resample(pcm: bytes, src_rate_hz: int, dst_rate_hz: int) -> bytes:
    """One-shot conversion for a complete buffer.

    Only correct for audio that is whole in itself -- a fixture WAV, say.
    For a live stream use `Resampler`, which keeps state across frames.
    """
    return Resampler(src_rate_hz, dst_rate_hz).process(pcm)
