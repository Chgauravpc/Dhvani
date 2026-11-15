from __future__ import annotations

import pytest

from dhvani.eval.stats import mcnemar_exact_p, wilson_interval


def test_mcnemar_no_discordant_pairs_is_not_significant() -> None:
    assert mcnemar_exact_p(0, 0) == 1.0


def test_mcnemar_symmetric_discordance_is_not_significant() -> None:
    assert mcnemar_exact_p(5, 5) == pytest.approx(1.0)


def test_mcnemar_matches_exact_binomial() -> None:
    # 10 fixed, 0 broken: two-sided p = 2 * 0.5**10
    assert mcnemar_exact_p(10, 0) == pytest.approx(2 / 1024)
    assert mcnemar_exact_p(0, 10) == pytest.approx(2 / 1024)
    # 8 vs 2: 2 * P(X <= 2 | n=10) = 2 * 56/1024
    assert mcnemar_exact_p(8, 2) == pytest.approx(112 / 1024)


def test_wilson_interval_brackets_the_estimate() -> None:
    lo, hi = wilson_interval(30, 100)
    assert lo < 0.30 < hi
    assert wilson_interval(0, 0) == (0.0, 0.0)
    lo0, hi0 = wilson_interval(0, 50)
    assert lo0 == 0.0 and 0.0 < hi0 < 0.1
