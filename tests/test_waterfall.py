from __future__ import annotations

from dhvani.telemetry.span import FIRST_AUDIO_OUT, Mark, Span, TurnTrace
from dhvani.telemetry.waterfall import render
from dhvani.types import Stage


class _FixedClock:
    """Clock double for building a fully deterministic trace by hand."""

    def now_ns(self) -> int:
        return 0

    async def sleep(self, seconds: float) -> None:
        raise NotImplementedError


def _fixed_trace() -> TurnTrace:
    trace = TurnTrace(_FixedClock(), turn_id="abcd1234")
    trace.t0_ns = 0
    trace.spans = [
        Span(stage=Stage.STT, name="partial", start_ns=0, end_ns=150_000_000),
        Span(stage=Stage.LLM, name="generate", start_ns=100_000_000, end_ns=400_000_000),
        Span(stage=Stage.TTS, name="synth", start_ns=350_000_000, end_ns=600_000_000),
    ]
    trace.marks = [Mark(name=FIRST_AUDIO_OUT, at_ns=600_000_000)]
    return trace


def test_waterfall_snapshot_is_deterministic() -> None:
    output_a = render(_fixed_trace(), width=72)
    output_b = render(_fixed_trace(), width=72)

    assert output_a == output_b
    assert "turn abcd1234" in output_a
    assert "TTFA=600.0ms" in output_a
    assert "^ first_audio_out at 600.0ms" in output_a


def test_waterfall_overlap_visible() -> None:
    output = render(_fixed_trace(), width=72)
    lines = output.splitlines()

    stt_line = next(line for line in lines if "stt" in line and "partial" in line)
    llm_line = next(line for line in lines if "llm" in line and "generate" in line)

    def hash_columns(line: str) -> set[int]:
        bar_start = line.index("|") + 1
        bar_end = line.rindex("|")
        return {i for i, ch in enumerate(line[bar_start:bar_end]) if ch == "#"}

    # stt [0,150ms) and llm [100,400ms) overlap on [100,150ms) -- both spans
    # must light up some of the same bar columns.
    assert hash_columns(stt_line) & hash_columns(llm_line)
