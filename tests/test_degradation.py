"""`run_degradation_sweep` over synthetic examples and a draining test
double -- no real dataset or model needed (the real sweep against
Svarah/LAHAJA audio and a real STT is `scripts/run_degradation_sweep.py`,
opt-in, per phase-3 spec section 8's testing table).

Uses a small local `_DrainingSTT` rather than `providers.mock.MockSTT`:
`MockSTT` never reads its `audio` argument at all, so the channel
simulator's `degrade()` would never actually run and `frames_lost` would
always read zero regardless of `packet_loss` -- this double actually
consumes every chunk, the way a real STT provider does."""

from __future__ import annotations

from array import array
from collections.abc import AsyncIterator

import pytest

from dhvani.audio.channel import ChannelConfig, LossFill
from dhvani.clock import FakeClock
from dhvani.eval.datasets import TranscriptExample
from dhvani.eval.degradation import run_degradation_sweep
from dhvani.telemetry.span import FINAL_TRANSCRIPT, TurnTrace
from dhvani.types import AudioChunk, Stage, Transcript

pytestmark = pytest.mark.asyncio


class _DrainingSTT:
    """Reads every chunk (so channel degradation actually applies), then
    emits one fixed final transcript regardless of audio content."""

    name = "draining-stt"

    def __init__(self, final: str, clock: FakeClock) -> None:
        self._final = final
        self._clock = clock

    async def stream(
        self, audio: AsyncIterator[AudioChunk], *, trace: TurnTrace
    ) -> AsyncIterator[Transcript]:
        async with trace.aspan(Stage.STT, self.name):
            async for _chunk in audio:
                pass
            await self._clock.sleep(0.01)
            trace.mark(FINAL_TRANSCRIPT)
            yield Transcript(text=self._final, is_final=True)


def _example(text: str, n_chunks: int = 5, sample_rate: int = 16000) -> TranscriptExample:
    samples = [int(4000 * ((-1) ** i)) for i in range(160)]  # 10ms @ 16kHz per chunk
    pcm = array("h", samples).tobytes()
    chunks = [
        AudioChunk(pcm=pcm, sample_rate=sample_rate, seq=i, is_last=(i == n_chunks - 1))
        for i in range(n_chunks)
    ]
    return TranscriptExample(audio_chunks=chunks, ground_truth_text=text)


async def test_perfect_channel_gives_zero_wer_when_hypothesis_matches_reference() -> None:
    clock = FakeClock()
    stt = _DrainingSTT(final="hello world", clock=clock)
    examples = [_example("hello world")]
    configs = [ChannelConfig(narrowband_hz=16000, mulaw=False)]

    points = await run_degradation_sweep(examples, configs, stt, clock)

    assert len(points) == 1
    assert points[0].wer == 0.0
    assert points[0].n_utterances == 1


async def test_wrong_hypothesis_gives_nonzero_wer() -> None:
    clock = FakeClock()
    stt = _DrainingSTT(final="goodbye", clock=clock)
    examples = [_example("hello world")]
    configs = [ChannelConfig(narrowband_hz=16000, mulaw=False)]

    points = await run_degradation_sweep(examples, configs, stt, clock)

    assert points[0].wer > 0.0


async def test_reports_both_wer_and_latency_at_every_point() -> None:
    """Section 3's requirement: a curve with only WER hides the finding."""
    clock = FakeClock()
    stt = _DrainingSTT(final="hi", clock=clock)
    examples = [_example("hi"), _example("hi")]
    configs = [
        ChannelConfig(narrowband_hz=16000, mulaw=False),
        ChannelConfig(narrowband_hz=8000, mulaw=True),
    ]

    points = await run_degradation_sweep(examples, configs, stt, clock)

    assert len(points) == 2
    for point in points:
        assert point.stt_p50_ms >= 0.0
        assert point.stt_p90_ms >= point.stt_p50_ms


async def test_total_packet_loss_reports_every_frame_lost() -> None:
    clock = FakeClock()
    stt = _DrainingSTT(final="hi", clock=clock)
    examples = [_example("hi", n_chunks=4)]
    configs = [ChannelConfig(packet_loss=1.0, loss_fill=LossFill.SILENCE)]

    points = await run_degradation_sweep(examples, configs, stt, clock)

    assert points[0].frames_lost == 4


async def test_zero_packet_loss_reports_no_frames_lost() -> None:
    clock = FakeClock()
    stt = _DrainingSTT(final="hi", clock=clock)
    examples = [_example("hi", n_chunks=4)]
    configs = [ChannelConfig(packet_loss=0.0)]

    points = await run_degradation_sweep(examples, configs, stt, clock)

    assert points[0].frames_lost == 0


async def test_render_table_lists_one_row_per_point() -> None:
    clock = FakeClock()
    stt = _DrainingSTT(final="hi", clock=clock)
    examples = [_example("hi")]
    configs = list(ChannelConfig(narrowband_hz=hz) for hz in (16000, 8000))

    from dhvani.eval.degradation import render_table

    points = await run_degradation_sweep(examples, configs, stt, clock)
    table = render_table(points)
    lines = table.splitlines()

    assert lines[0].startswith("| config")
    assert len(lines) == 2 + len(configs)
