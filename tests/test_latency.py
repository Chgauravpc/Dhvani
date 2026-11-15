from __future__ import annotations

import pytest

from dhvani.eval.latency import percentile, stage_split, summarise


def test_percentile_interpolates() -> None:
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([5], 90) == 5
    assert percentile([1, 2, 3, 4, 5], 90) == pytest.approx(4.6)


def test_stage_split_sums_to_total() -> None:
    ms = 1_000_000
    s = stage_split(0, 500 * ms, 800 * ms, 1_100 * ms, 1_400 * ms)
    assert [s[k] for k in ("endpoint_ms", "stt_ms", "llm_ms", "tts_ms")] == [500, 300, 300, 300]
    assert s["total_ms"] == 1_400 and s["clamped"] == 0


def test_stage_split_clamps_out_of_order_instants() -> None:
    ms = 1_000_000
    s = stage_split(0, 600 * ms, 500 * ms, 900 * ms, 1_000 * ms)
    assert s["stt_ms"] == 0 and s["clamped"] == 1 and s["total_ms"] == 1_000


def test_summarise_skips_failures() -> None:
    rows = [
        {"endpoint_ms": 1, "stt_ms": 1, "llm_ms": 1, "tts_ms": 1, "total_ms": 4},
        {"error": "empty_transcript"},
    ]
    out = summarise(rows)
    assert out["n_completed"] == 1 and out["n_failed"] == 1 and out["total_ms"]["p50"] == 4
