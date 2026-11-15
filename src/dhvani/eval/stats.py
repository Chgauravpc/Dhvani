"""Small, dependency-free statistics for the eval reports (phase-3b 3B-4)."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion (0, 0 for n=0)."""
    if n == 0:
        return (0.0, 0.0)
    phat = successes / n
    denom = 1 + z**2 / n
    center = (phat + z**2 / (2 * n)) / denom
    margin = z * math.sqrt(phat * (1 - phat) / n + z**2 / (4 * n**2)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def mcnemar_exact_p(fixed: int, broken: int) -> float:
    """Two-sided exact McNemar p-value on paired binary outcomes: a
    binomial(fixed + broken, 0.5) test on the discordant pairs only.
    1.0 when there are no discordant pairs."""
    n = fixed + broken
    if n == 0:
        return 1.0
    k = min(fixed, broken)
    tail: float = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2.0 * tail)


def paired_bootstrap_ci(
    values: Sequence[float],
    *,
    n_resamples: int = 10_000,
    seed: int = 0,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """Percentile bootstrap CI for the mean of per-example paired differences
    (3B-5). Resamples examples with replacement; deterministic for a seed.
    (0, 0) for no values."""
    n = len(values)
    if n == 0:
        return (0.0, 0.0)
    rng = random.Random(seed)
    means = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_resamples))
    lo = means[int((alpha / 2) * n_resamples)]
    hi = means[min(n_resamples - 1, int((1 - alpha / 2) * n_resamples))]
    return (lo, hi)
