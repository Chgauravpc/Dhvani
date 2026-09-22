"""`pareto_front` on synthetic points -- phase-2b spec section 7: ties and
full domination, no real Whisper model needed (`run_sweep` itself needs a
real model download and is exercised by `scripts/run_model_sweep.py`, not
unit-tested here)."""

from __future__ import annotations

from dhvani.eval.model_sweep import SweepPoint, pareto_front, render_table


def _point(
    model_size: str, compute_type: str, wer: float, p50_ms: float, n: int = 10
) -> SweepPoint:
    return SweepPoint(
        model_size=model_size,
        compute_type=compute_type,
        wer=wer,
        stt_p50_ms=p50_ms,
        stt_p90_ms=p50_ms * 1.5,
        realtime_factor=p50_ms / 1000,
        n_utterances=n,
    )


def test_full_domination_removes_the_dominated_point() -> None:
    fast_accurate = _point("small", "int8", wer=0.10, p50_ms=100)
    slow_same_accuracy = _point("small", "float32", wer=0.10, p50_ms=200)

    front = pareto_front([fast_accurate, slow_same_accuracy])

    assert front == [fast_accurate]


def test_classic_tradeoff_keeps_both_points() -> None:
    fast_worse = _point("tiny", "int8", wer=0.30, p50_ms=50)
    slow_better = _point("small", "float32", wer=0.10, p50_ms=300)

    front = pareto_front([fast_worse, slow_better])

    assert front == [fast_worse, slow_better]


def test_ties_are_not_dominated_and_both_survive() -> None:
    a = _point("tiny", "int8", wer=0.15, p50_ms=120)
    b = _point("base", "int8", wer=0.15, p50_ms=120)

    front = pareto_front([a, b])

    assert front == [a, b]


def test_mixed_set_drops_only_the_dominated_point() -> None:
    best = _point("small", "int8", wer=0.10, p50_ms=100)
    dominated_by_best = _point("small", "float32", wer=0.15, p50_ms=150)
    fast_tradeoff = _point("tiny", "int8", wer=0.30, p50_ms=20)

    front = pareto_front([best, dominated_by_best, fast_tradeoff])

    assert front == [best, fast_tradeoff]


def test_pareto_front_of_empty_points_is_empty() -> None:
    assert pareto_front([]) == []


def test_pareto_front_of_single_point_is_that_point() -> None:
    only = _point("small", "int8", wer=0.10, p50_ms=100)
    assert pareto_front([only]) == [only]


def test_render_table_marks_only_pareto_optimal_rows() -> None:
    best = _point("small", "int8", wer=0.10, p50_ms=100)
    dominated_by_best = _point("small", "float32", wer=0.15, p50_ms=150)
    fast_tradeoff = _point("tiny", "int8", wer=0.30, p50_ms=20)

    table = render_table([best, dominated_by_best, fast_tradeoff])
    lines = table.splitlines()

    assert lines[0].startswith("| model_size")
    assert len(lines) == 2 + 3  # header + separator + one row per point
    assert "| small | int8 |" in lines[2] and lines[2].rstrip().endswith("yes |")
    assert "| small | float32 |" in lines[3] and "yes" not in lines[3]
    assert "| tiny | int8 |" in lines[4] and lines[4].rstrip().endswith("yes |")
