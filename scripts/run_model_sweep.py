"""Workstream B -- run the real WER-against-latency sweep over Whisper model
size and quantization, against a bounded Svarah/LAHAJA sample (phase-2b spec
section B.2/open question 2: the same corpora F2 already uses, so the WER
numbers sit in the same frame as the EER numbers).

    uv run python scripts/run_model_sweep.py --dataset svarah --n-examples 30
    uv run python scripts/run_model_sweep.py --dataset lahaja --n-examples 30
    uv run python scripts/run_model_sweep.py --dataset svarah --model-sizes tiny,small \
        --compute-types int8

Needs Hugging Face access to the chosen dataset, same as
`scripts/run_f2_entity_eval.py` (both are gated). Downloads whichever
faster-whisper model sizes aren't already cached.

`float32` is the slow corner of the grid on a CPU-only machine (phase-2b
spec open question 3) -- pass `--compute-types int8` alone to skip it if a
quick check shows it isn't worth the wait.

Samples via `eval.datasets.load_*_filtered` (the same streaming loader F2
uses), never the plain `load_svarah`/`load_lahaja` -- those decode *every*
row's embedded audio up front before any sampling happens, which is the
exact memory-pressure bug phase-2 spec section 14 hit and fixed for the EER
eval. Filtering on the same `DEFAULT_LEXICON` incidentally means this
script only ever decodes the bounded pool it needs, entity-bearing or not
-- the sweep itself is entity-agnostic, so entity-bearing and clean rows
are pooled together and re-sampled down to `--n-examples`.
"""

from __future__ import annotations

import argparse
import asyncio
import random

from dhvani.clock import RealClock
from dhvani.entity.lexicon import DEFAULT_LEXICON
from dhvani.eval.datasets import TranscriptExample, load_lahaja_filtered, load_svarah_filtered
from dhvani.eval.model_sweep import render_table, run_sweep

_LOADERS = {"svarah": load_svarah_filtered, "lahaja": load_lahaja_filtered}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=sorted(_LOADERS), required=True)
    parser.add_argument("--n-examples", type=int, default=30)
    parser.add_argument("--model-sizes", default="tiny,small")
    parser.add_argument("--compute-types", default="int8")
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def _bounded_sample(
    examples: list[TranscriptExample], n: int, seed: int
) -> list[TranscriptExample]:
    rng = random.Random(seed)
    if len(examples) <= n:
        return examples
    return rng.sample(examples, n)


async def main() -> None:
    args = _parse_args()
    model_sizes = [s.strip() for s in args.model_sizes.split(",") if s.strip()]
    compute_types = [c.strip() for c in args.compute_types.split(",") if c.strip()]

    print(f"loading {args.dataset} (streamed, bounded pool)...")
    filtered = _LOADERS[args.dataset](DEFAULT_LEXICON, n_clean_sample=args.n_examples)
    pool = list(filtered.entity_bearing) + list(filtered.clean_sample)
    examples = _bounded_sample(pool, args.n_examples, args.seed)
    print(f"pooled {len(pool)} rows, sweeping a bounded sample of {len(examples)}")

    clock = RealClock()
    print(f"sweeping model_sizes={model_sizes} x compute_types={compute_types}...")
    points = await run_sweep(examples, model_sizes, compute_types, clock)

    print()
    print(render_table(points))


if __name__ == "__main__":
    asyncio.run(main())
