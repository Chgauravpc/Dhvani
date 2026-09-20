"""F2 -- run the real entity-error-rate eval against Svarah or LAHAJA.

    uv run python scripts/run_f2_entity_eval.py --dataset svarah
    uv run python scripts/run_f2_entity_eval.py --dataset lahaja

Needs Hugging Face access to the chosen dataset (both are gated) -- see
`scripts/entity_density_gate.py`'s docstring for how to set that up, and
run that gate first (phase-2 spec section 2A: it's a go/no-go check, not
optional -- it decides whether an EER computed on this corpus means
anything). Downloads faster-whisper's model on first run; set
`DHVANI_WHISPER_MODEL` (default `small`) the same way `dhvani.live` does.

Only decodes/transcribes audio for entity-bearing rows plus a bounded
random sample of entity-free rows (`eval.datasets.load_*_filtered`) --
Svarah and LAHAJA are each 6,000+ rows, and transcribing all of them would
turn a few-minute eval into a multi-hour one for no signal this eval uses.

Implements the spec's "tune on dev, report on test" rule (section 6.7):
splits the entity-bearing examples 30/70 dev/test, transcribes dev and
test once each (not once per threshold), sweeps a fixed threshold grid on
dev, picks the threshold minimizing `eer_after + corruption_rate` (ties
broken toward the higher, more conservative threshold), then reports a
single test-split run at that threshold -- never re-running test to chase
a better number.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import random

from dhvani.clock import RealClock
from dhvani.config import load_dotenv
from dhvani.entity.corrector import EntityCorrector
from dhvani.entity.lexicon import DEFAULT_LEXICON
from dhvani.eval.datasets import FilteredExamples, load_lahaja_filtered, load_svarah_filtered
from dhvani.eval.entity_error_rate import (
    EerReport,
    TranscribedExample,
    score_transcripts,
    transcribe_examples,
)
from dhvani.providers.whisper_stt import WhisperSTT

_LOADERS = {"svarah": load_svarah_filtered, "lahaja": load_lahaja_filtered}
_THRESHOLD_GRID = (0.70, 0.75, 0.80, 0.82, 0.85, 0.90, 0.95)
_DEV_FRACTION = 0.3


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=sorted(_LOADERS), required=True)
    parser.add_argument("--n-clean-sample", type=int, default=150)
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def _split_dev_test(
    filtered: FilteredExamples, seed: int
) -> tuple[FilteredExamples, FilteredExamples]:
    rng = random.Random(seed)
    entity = list(filtered.entity_bearing)
    clean = list(filtered.clean_sample)
    rng.shuffle(entity)
    rng.shuffle(clean)
    entity_split = round(len(entity) * _DEV_FRACTION)
    clean_split = round(len(clean) * _DEV_FRACTION)
    dev = FilteredExamples(entity_bearing=entity[:entity_split], clean_sample=clean[:clean_split])
    test = FilteredExamples(entity_bearing=entity[entity_split:], clean_sample=clean[clean_split:])
    return dev, test


def _wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion -- no scipy
    dependency needed for one formula. Used to give LAHAJA's EER (spec's
    own 30-100 mention "report a confidence interval" bucket) an honest
    uncertainty range instead of a bare point estimate."""
    if n == 0:
        return (0.0, 0.0)
    phat = successes / n
    denom = 1 + z**2 / n
    center = (phat + z**2 / (2 * n)) / denom
    margin = z * math.sqrt(phat * (1 - phat) / n + z**2 / (4 * n**2)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def _print_report(label: str, report: EerReport) -> None:
    n_wrong_after = round(report.eer_after * report.n_entity_mentions)
    lo, hi = _wilson_interval(n_wrong_after, report.n_entity_mentions)
    print(
        f"{label}: threshold={report.threshold} n_mentions={report.n_entity_mentions} "
        f"eer_before={report.eer_before:.1%} eer_after={report.eer_after:.1%} "
        f"(95% CI [{lo:.1%}, {hi:.1%}]) "
        f"n_clean={report.n_clean_examples} corruption_rate={report.corruption_rate:.1%}"
    )


async def _sweep_dev(
    dev_transcribed: list[TranscribedExample],
) -> tuple[float, EerReport]:
    print("\nsweeping threshold on dev...")
    best_threshold = _THRESHOLD_GRID[0]
    best_report: EerReport | None = None
    best_cost = float("inf")
    for threshold in _THRESHOLD_GRID:
        corrector = EntityCorrector(DEFAULT_LEXICON, threshold=threshold)
        report = score_transcripts(dev_transcribed, DEFAULT_LEXICON, corrector, split="dev")
        _print_report("  dev", report)
        cost = report.eer_after + report.corruption_rate
        if cost <= best_cost:  # <= : ties prefer the later (higher) threshold
            best_cost = cost
            best_threshold = threshold
            best_report = report
    assert best_report is not None
    print(f"chosen threshold: {best_threshold} (minimizes eer_after + corruption_rate on dev)")
    return best_threshold, best_report


async def main() -> None:
    args = _parse_args()
    load_dotenv()

    print(f"loading {args.dataset} (entity-bearing rows + {args.n_clean_sample} clean sample)...")
    filtered = _LOADERS[args.dataset](DEFAULT_LEXICON, n_clean_sample=args.n_clean_sample)
    print(
        f"loaded {len(filtered.entity_bearing)} entity-bearing rows, "
        f"{len(filtered.clean_sample)} clean rows"
    )
    dev, test = _split_dev_test(filtered, seed=args.seed)
    print(
        f"dev: {len(dev.entity_bearing)} entity-bearing, {len(dev.clean_sample)} clean | "
        f"test: {len(test.entity_bearing)} entity-bearing, {len(test.clean_sample)} clean"
    )

    clock = RealClock()
    whisper_model_size = os.environ.get("DHVANI_WHISPER_MODEL", "small")
    stt = WhisperSTT(whisper_model_size, clock)

    print("\ntranscribing dev split (once)...")
    dev_transcribed = await transcribe_examples(
        list(dev.entity_bearing) + list(dev.clean_sample), stt, clock
    )
    chosen_threshold, _dev_report_at_chosen = await _sweep_dev(dev_transcribed)

    print("\ntranscribing test split (once)...")
    test_transcribed = await transcribe_examples(
        list(test.entity_bearing) + list(test.clean_sample), stt, clock
    )
    final_corrector = EntityCorrector(DEFAULT_LEXICON, threshold=chosen_threshold)
    test_report = score_transcripts(
        test_transcribed, DEFAULT_LEXICON, final_corrector, split="test"
    )

    print("\n--- final (test split, single run at the dev-chosen threshold) ---")
    _print_report("test", test_report)


if __name__ == "__main__":
    asyncio.run(main())
