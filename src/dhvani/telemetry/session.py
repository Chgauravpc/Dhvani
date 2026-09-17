"""Aggregation of turn traces into a session, and percentile reporting."""

from __future__ import annotations

import statistics
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from dhvani.telemetry.span import TurnTrace
from dhvani.types import Stage


@dataclass(frozen=True, slots=True)
class Percentiles:
    """Summary statistics over a set of millisecond durations."""

    n: int
    p50_ms: float
    p90_ms: float
    p99_ms: float
    max_ms: float


def _percentiles(values: Sequence[float]) -> Percentiles:
    n = len(values)
    if n == 0:
        return Percentiles(n=0, p50_ms=0.0, p90_ms=0.0, p99_ms=0.0, max_ms=0.0)
    if n == 1:
        (v,) = values
        return Percentiles(n=1, p50_ms=v, p90_ms=v, p99_ms=v, max_ms=v)

    ordered = sorted(values)
    cuts = statistics.quantiles(ordered, n=100, method="inclusive")
    return Percentiles(
        n=n,
        p50_ms=cuts[49],
        p90_ms=cuts[89],
        p99_ms=cuts[98],
        max_ms=ordered[-1],
    )


class SessionTrace:
    """A sequence of turn traces for one conversation session."""

    def __init__(self, session_id: str | None = None) -> None:
        self.session_id = session_id if session_id is not None else uuid.uuid4().hex[:8]
        self.turns: list[TurnTrace] = []

    def add(self, turn: TurnTrace) -> None:
        self.turns.append(turn)

    def percentiles(self, stage: Stage) -> Percentiles:
        """Percentiles of per-turn `stage_total_ms` for the given stage."""
        return _percentiles([t.stage_total_ms(stage) for t in self.turns])

    def ttfa_percentiles(self) -> Percentiles:
        """Percentiles of per-turn Time To First Audio, over turns that have one."""
        return _percentiles([t.ttfa_ms for t in self.turns if t.ttfa_ms is not None])

    def report(self) -> str:
        """Human-readable per-stage table: n, p50, p90, p99, max."""
        header = f"{'stage':<10}{'n':>5}{'p50_ms':>10}{'p90_ms':>10}{'p99_ms':>10}{'max_ms':>10}"
        lines = [header, "-" * len(header)]
        for stage in Stage:
            p = self.percentiles(stage)
            lines.append(
                f"{stage.value:<10}{p.n:>5}{p.p50_ms:>10.1f}{p.p90_ms:>10.1f}"
                f"{p.p99_ms:>10.1f}{p.max_ms:>10.1f}"
            )
        ttfa = self.ttfa_percentiles()
        lines.append("-" * len(header))
        lines.append(
            f"{'ttfa':<10}{ttfa.n:>5}{ttfa.p50_ms:>10.1f}{ttfa.p90_ms:>10.1f}"
            f"{ttfa.p99_ms:>10.1f}{ttfa.max_ms:>10.1f}"
        )
        return "\n".join(lines)
