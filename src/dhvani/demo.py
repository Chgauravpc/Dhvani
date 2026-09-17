"""`python -m dhvani.demo` -- runs one mock turn and prints a waterfall."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from dhvani.clock import RealClock
from dhvani.config import LatencyBudget
from dhvani.pipeline.sequential import SequentialRunner
from dhvani.providers.mock import MockLLM, MockSTT, MockTiming, MockTTS
from dhvani.telemetry.session import SessionTrace
from dhvani.telemetry.waterfall import render
from dhvani.types import AudioChunk


async def _one_chunk_of_silence() -> AsyncIterator[AudioChunk]:
    yield AudioChunk(pcm=b"\x00\x00" * 320, sample_rate=16000, seq=0, is_last=True)


async def main() -> None:
    clock = RealClock()
    stt = MockSTT(
        partials=["namaste", "namaste duniya"],
        final="namaste duniya",
        timing=MockTiming(ttfb_ms=120.0, per_unit_ms=60.0),
        clock=clock,
    )
    llm = MockLLM(
        response="Hello there, how can I help you today?",
        timing=MockTiming(ttfb_ms=150.0, per_unit_ms=40.0),
        clock=clock,
    )
    tts = MockTTS(timing=MockTiming(ttfb_ms=100.0, per_unit_ms=20.0), clock=clock)
    budget = LatencyBudget()
    runner = SequentialRunner(stt, llm, tts, clock, budget)

    session = SessionTrace()
    result = await runner.run_turn(_one_chunk_of_silence())
    session.add(result.trace)

    print(render(result.trace))
    print()
    print(session.report())

    violations = budget.violations(result.trace)
    if violations:
        print()
        print("Budget violations:")
        for v in violations:
            stage_name = v.stage.value if v.stage is not None else "ttfa"
            print(
                f"  {stage_name}: {v.actual_ms:.1f}ms over budget "
                f"{v.budget_ms:.1f}ms (+{v.over_by_ms:.1f}ms)"
            )


if __name__ == "__main__":
    asyncio.run(main())
