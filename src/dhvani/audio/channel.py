"""A simulated telephony channel: narrowband, mu-law, lossy, jittery.

This stands in for a real PSTN call, and not only because a phone number
costs money. Impairment on a real line is uncontrolled -- you get one sample
of whatever the carrier did that afternoon. A simulator is parameterised, so
you can sweep packet loss from 0 to 5 percent and plot the curve. One
uncontrolled sample is an anecdote; the curve is a result.

What it models, in the order a real call applies them:

1. Downsample to narrowband (8 kHz), losing everything above 4 kHz
2. G.711 mu-law encode and decode, the lossy 8-bit companding step
3. Packet loss, at 20 ms frame granularity
4. Jitter and fixed delay

It does not model codec transcoding chains, echo, or comfort noise. Those
would be the next things to add if measurement justified them.
"""

from __future__ import annotations

import random
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from enum import StrEnum

from dhvani.audio import mulaw
from dhvani.audio.resample import Resampler
from dhvani.clock import Clock
from dhvani.types import AudioChunk


class LossFill(StrEnum):
    """What the receiver hears in place of a lost packet."""

    SILENCE = "silence"
    """Substitute an equal span of silence. Preserves stream duration, so
    transcripts stay time-aligned -- the right default when measuring WER."""

    DROP = "drop"
    """Emit nothing. Shortens the stream, as a receiver with no concealment
    would experience it."""


@dataclass(frozen=True, slots=True)
class ChannelConfig:
    """One point in the impairment space. Sweep these to get a curve."""

    narrowband_hz: int = 8_000
    mulaw: bool = True
    packet_loss: float = 0.0
    """Fraction of frames lost, 0.0 to 1.0."""
    loss_fill: LossFill = LossFill.SILENCE
    jitter_ms: float = 0.0
    """Maximum extra delay per frame, uniformly distributed over [0, jitter_ms]."""
    delay_ms: float = 0.0
    """Fixed one-way delay added to every frame."""
    seed: int = 0
    """Fixes the loss and jitter draw, so a sweep is reproducible."""

    def __post_init__(self) -> None:
        if not 0.0 <= self.packet_loss <= 1.0:
            raise ValueError(f"packet_loss must be in [0, 1], got {self.packet_loss}")
        if self.narrowband_hz <= 0:
            raise ValueError(f"narrowband_hz must be positive, got {self.narrowband_hz}")
        if self.jitter_ms < 0 or self.delay_ms < 0:
            raise ValueError("jitter_ms and delay_ms must be non-negative")

    @property
    def label(self) -> str:
        """Short identifier for a sweep row or chart axis."""
        parts = [f"{self.narrowband_hz // 1000}k"]
        if self.mulaw:
            parts.append("ulaw")
        if self.packet_loss:
            parts.append(f"loss{self.packet_loss:.0%}")
        if self.jitter_ms:
            parts.append(f"jit{self.jitter_ms:.0f}ms")
        return "-".join(parts)


CLEAN = ChannelConfig(narrowband_hz=8_000, mulaw=False)
"""Narrowband but otherwise undamaged -- isolates the 8 kHz cost alone."""


def default_sweep(source_rate_hz: int = 16_000) -> tuple[ChannelConfig, ...]:
    """A reasonable first impairment sweep, mildest to worst.

    Starts with a wideband passthrough so the curve has a true baseline, then
    walks narrowband, companding, and loss in that order -- each step isolating
    one cost.
    """
    return (
        ChannelConfig(narrowband_hz=source_rate_hz, mulaw=False),
        ChannelConfig(narrowband_hz=8_000, mulaw=False),
        ChannelConfig(narrowband_hz=8_000, mulaw=True),
        ChannelConfig(narrowband_hz=8_000, mulaw=True, packet_loss=0.01),
        ChannelConfig(narrowband_hz=8_000, mulaw=True, packet_loss=0.03),
        ChannelConfig(narrowband_hz=8_000, mulaw=True, packet_loss=0.05),
        ChannelConfig(narrowband_hz=8_000, mulaw=True, packet_loss=0.03, jitter_ms=40.0),
    )


@dataclass(frozen=True, slots=True)
class ChannelStats:
    """What the channel actually did, for reporting alongside a measurement."""

    frames_in: int
    frames_lost: int

    @property
    def loss_rate(self) -> float:
        return self.frames_lost / self.frames_in if self.frames_in else 0.0


class TelephonyChannel:
    """Degrades an audio stream the way a phone network would.

    Deterministic for a given `ChannelConfig.seed`: the same input and the
    same config always produce the same output, which is what makes a sweep
    comparable across runs.
    """

    def __init__(self, config: ChannelConfig, source_rate_hz: int, clock: Clock) -> None:
        self._config = config
        self._clock = clock
        self._source_rate_hz = source_rate_hz
        self._down = Resampler(source_rate_hz, config.narrowband_hz)
        self._up = Resampler(config.narrowband_hz, source_rate_hz)
        self._rng = random.Random(config.seed)
        self._frames_in = 0
        self._frames_lost = 0

    @property
    def stats(self) -> ChannelStats:
        return ChannelStats(frames_in=self._frames_in, frames_lost=self._frames_lost)

    def reset(self) -> None:
        """Restart, including the random draw, so a rerun reproduces exactly."""
        self._down.reset()
        self._up.reset()
        self._rng = random.Random(self._config.seed)
        self._frames_in = 0
        self._frames_lost = 0

    def degrade(self, chunk: AudioChunk) -> AudioChunk | None:
        """Apply band limiting, companding and loss to one frame.

        Returns None when the frame was lost and the fill mode is DROP.
        The returned chunk is back at the source sample rate: the damage is
        baked into the samples, not left as a rate change for callers to
        handle.
        """
        self._frames_in += 1

        narrow = self._down.process(chunk.pcm)

        if self._config.mulaw:
            narrow = mulaw.decode(mulaw.encode(narrow))

        if self._config.packet_loss and self._rng.random() < self._config.packet_loss:
            self._frames_lost += 1
            if self._config.loss_fill is LossFill.DROP:
                return None
            narrow = bytes(len(narrow))

        wide = self._up.process(narrow)
        return AudioChunk(
            pcm=wide,
            sample_rate=self._source_rate_hz,
            seq=chunk.seq,
            is_last=chunk.is_last,
        )

    async def stream(self, audio: AsyncIterator[AudioChunk]) -> AsyncIterator[AudioChunk]:
        """Degrade a live stream, including timing effects.

        Fixed delay is applied once, before the first frame; jitter is drawn
        per frame. Both go through the injected `Clock`, so this is instant
        under virtual time in tests and real under `RealClock`.
        """
        if self._config.delay_ms:
            await self._clock.sleep(self._config.delay_ms / 1000.0)

        async for chunk in audio:
            if self._config.jitter_ms:
                await self._clock.sleep(self._rng.uniform(0.0, self._config.jitter_ms) / 1000.0)
            degraded = self.degrade(chunk)
            if degraded is not None:
                yield degraded


def sweep_labels(configs: Sequence[ChannelConfig]) -> tuple[str, ...]:
    """Axis labels for a sweep, in order."""
    return tuple(config.label for config in configs)
