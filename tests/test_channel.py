"""Simulated telephony channel -- phase-3 spec section 8: same seed gives
byte-identical output; packet_loss=0 drops nothing; 1.0 loses every frame;
SILENCE preserves duration, DROP shortens."""

from __future__ import annotations

from array import array
from collections.abc import AsyncIterator

import pytest

from dhvani.audio.channel import ChannelConfig, LossFill, TelephonyChannel
from dhvani.clock import FakeClock
from dhvani.types import AudioChunk


def _sine_chunk(seq: int, n_samples: int = 320, sample_rate: int = 16000) -> AudioChunk:
    samples = [int(5000 * ((-1) ** i)) for i in range(n_samples)]
    return AudioChunk(pcm=array("h", samples).tobytes(), sample_rate=sample_rate, seq=seq)


async def _chunks(n: int) -> AsyncIterator[AudioChunk]:
    for i in range(n):
        yield _sine_chunk(i)


def test_same_seed_gives_byte_identical_output() -> None:
    config = ChannelConfig(packet_loss=0.3, jitter_ms=0.0, seed=42)

    a = TelephonyChannel(config, source_rate_hz=16000, clock=FakeClock())
    b = TelephonyChannel(config, source_rate_hz=16000, clock=FakeClock())

    out_a = [a.degrade(_sine_chunk(i)) for i in range(20)]
    out_b = [b.degrade(_sine_chunk(i)) for i in range(20)]

    assert [c.pcm if c else None for c in out_a] == [c.pcm if c else None for c in out_b]


def test_zero_packet_loss_drops_nothing() -> None:
    config = ChannelConfig(packet_loss=0.0)
    channel = TelephonyChannel(config, source_rate_hz=16000, clock=FakeClock())

    for i in range(50):
        result = channel.degrade(_sine_chunk(i))
        assert result is not None

    assert channel.stats.frames_lost == 0


def test_total_packet_loss_loses_every_frame() -> None:
    config = ChannelConfig(packet_loss=1.0, loss_fill=LossFill.DROP)
    channel = TelephonyChannel(config, source_rate_hz=16000, clock=FakeClock())

    for i in range(20):
        result = channel.degrade(_sine_chunk(i))
        assert result is None

    assert channel.stats.frames_lost == 20
    assert channel.stats.loss_rate == 1.0


def test_silence_fill_preserves_chunk_count_and_duration() -> None:
    config = ChannelConfig(packet_loss=1.0, loss_fill=LossFill.SILENCE)
    channel = TelephonyChannel(config, source_rate_hz=16000, clock=FakeClock())

    chunk = _sine_chunk(0)
    result = channel.degrade(chunk)

    assert result is not None
    assert result.n_samples == chunk.n_samples
    assert array("h", result.pcm).tolist() == [0] * chunk.n_samples


def test_drop_fill_shortens_the_stream() -> None:
    config = ChannelConfig(packet_loss=1.0, loss_fill=LossFill.DROP)
    channel = TelephonyChannel(config, source_rate_hz=16000, clock=FakeClock())

    assert channel.degrade(_sine_chunk(0)) is None


@pytest.mark.asyncio
async def test_stream_applies_degrade_to_every_chunk() -> None:
    config = ChannelConfig(packet_loss=0.0)
    channel = TelephonyChannel(config, source_rate_hz=16000, clock=FakeClock())

    out = [c async for c in channel.stream(_chunks(5))]

    assert len(out) == 5
    assert channel.stats.frames_in == 5


@pytest.mark.asyncio
async def test_stream_drop_fill_yields_fewer_chunks_than_input() -> None:
    config = ChannelConfig(packet_loss=1.0, loss_fill=LossFill.DROP)
    channel = TelephonyChannel(config, source_rate_hz=16000, clock=FakeClock())

    out = [c async for c in channel.stream(_chunks(5))]

    assert out == []


def test_reset_reproduces_the_original_run_exactly() -> None:
    config = ChannelConfig(packet_loss=0.3, jitter_ms=10.0, seed=7)
    channel = TelephonyChannel(config, source_rate_hz=16000, clock=FakeClock())

    first = [channel.degrade(_sine_chunk(i)) for i in range(10)]
    channel.reset()
    second = [channel.degrade(_sine_chunk(i)) for i in range(10)]

    assert [c.pcm if c else None for c in first] == [c.pcm if c else None for c in second]


def test_invalid_packet_loss_raises() -> None:
    with pytest.raises(ValueError, match="packet_loss"):
        ChannelConfig(packet_loss=1.5)


def test_negative_jitter_raises() -> None:
    with pytest.raises(ValueError):
        ChannelConfig(jitter_ms=-1.0)
